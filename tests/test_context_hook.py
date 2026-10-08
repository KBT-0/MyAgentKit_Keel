"""The context hook must speak once per 50k step past 200k, choose nothing itself, and never block."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'overlays/claude-code/files'
HOOK = OVERLAY / '.claude/hooks/context_size.py'


def prompt(text='go'):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def request(ctx, read=None):
    return {'type': 'assistant', 'message': {'model': 'claude-x', 'usage': {
        'input_tokens': 10, 'cache_read_input_tokens': ctx - 1010 if read is None else read,
        'cache_creation_input_tokens': 1000}}}


class ContextHookTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.transcript = self.tmp / 'session-1.jsonl'
        self.env = dict(os.environ)

    def run_hook(self, records, raw=None, command=None, env=None):
        self.transcript.write_text(raw if raw is not None else ''.join(json.dumps(r) + '\n' for r in records))
        result = subprocess.run(command or [sys.executable, str(HOOK)],
                                input=json.dumps({'transcript_path': str(self.transcript)}),
                                text=True, capture_output=True, timeout=30, env=env or self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_once_per_step_past_the_line(self):
        turns = [prompt(), request(150_000), prompt(), request(190_000), prompt(), request(210_000)]
        said = self.run_hook(turns + [prompt()])
        self.assertIn('Context is 210k tokens', said)
        self.assertIn('/compact', said)
        self.assertIn('hand-off', said)
        self.assertIn("closing summary", said)  # when AGENTS.md's MENTION ONCE list says
        self.assertEqual(self.run_hook(turns + [prompt(), prompt()]), '')  # a retry with no request
        turns += [prompt(), request(240_000)]
        self.assertEqual(self.run_hook(turns + [prompt()]), '')  # same step: said already
        turns += [prompt(), request(255_000)]
        self.assertIn('Context is 255k tokens', self.run_hook(turns + [prompt()]))
        # /compact: the boundary comes before any new request, and the old size is gone.
        turns += [prompt('/compact'), {'type': 'system', 'subtype': 'compact_boundary'},
                  {'type': 'user', 'isCompactSummary': True, 'message': {'content': 'summary'}}]
        self.assertEqual(self.run_hook(turns + [prompt()]), '')
        turns += [request(60_000), prompt(), request(205_000)]
        self.assertIn('Context is 205k tokens', self.run_hook(turns + [prompt()]))  # armed again

    def test_a_null_counter_is_zero(self):
        self.assertIn('Context is 210k tokens', self.run_hook([prompt(), {'type': 'assistant', 'message': {
            'model': 'claude-x', 'usage': {'input_tokens': 210_000, 'cache_read_input_tokens': None,
                                           'cache_creation_input_tokens': None}}}]))

    def test_silent_below_the_line_and_on_a_broken_transcript(self):
        self.assertEqual(self.run_hook([prompt(), request(199_000)]), '')
        self.assertEqual(self.run_hook([], raw='not json\n5\n{"type": "assistant", "message": 5}\n'), '')
        result = subprocess.run([sys.executable, str(HOOK)], input='{}', text=True, capture_output=True,
                                timeout=30, env=self.env)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_same_named_transcripts_keep_their_own_step(self):
        # Projects' transcripts share file names; the step one named must not silence another.
        other = self.tmp / 'other'
        other.mkdir()
        turns = [prompt(), request(210_000)]
        self.assertIn('Context is 210k tokens', self.run_hook(turns))
        self.transcript = other / self.transcript.name
        self.assertIn('Context is 210k tokens', self.run_hook(turns))

    def test_every_python_hook_runs_where_python3_does_not(self):
        # Windows installs Python as `python`, and its `python3` may be a Store alias that is on
        # PATH but does not run (9009, or 126 where it is not accessible). A hook command that
        # named python3, or only checked that it exists, then failed and Claude Code went on
        # without the hook. Each registered command runs here with such a python3 first on PATH.
        hooks = json.loads((OVERLAY / '.claude/settings.json').read_text())['hooks']
        commands = [h['command'] for entries in hooks.values() for e in entries for h in e['hooks']]
        python_hooks = {Path(c.split('"')[-2]).name: c for c in commands if '.py"' in c}
        self.assertEqual(sorted(python_hooks), ['context_size.py', 'guard_boundaries.py',
                                                'guard_destructive_git.py'], commands)
        for command in python_hooks.values():
            self.assertTrue(command.startswith('sh "$CLAUDE_PROJECT_DIR/.claude/hooks/py.sh" '), command)
        bin_dir = self.tmp / 'bin'
        bin_dir.mkdir()
        for name, body in (('python3', 'exit 126'), ('python', 'exec "%s" "$@"' % Path(sys.executable).as_posix())):
            (bin_dir / name).write_text('#!/bin/sh\n%s\n' % body)
            (bin_dir / name).chmod(0o755)
        project = self.tmp / 'project'
        shutil.copytree(OVERLAY / '.claude/hooks', project / '.claude/hooks')
        # The broken python3 comes first; sh's own folder follows (on Linux it holds a working
        # python3 too, which the launcher must not need to reach).
        # A dirty repository, so the guard blocks whether or not git is on that PATH (with no
        # git it assumes uncommitted work). GIT_* from a calling hook would route git elsewhere.
        clean = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        subprocess.run(['git', 'init', '-q', str(project)], check=True, env=clean)
        (project / 'notes.txt').write_text('uncommitted\n')
        env = dict(clean, PATH=os.pathsep.join([str(bin_dir), os.path.dirname(shutil.which('sh'))]),
                   CLAUDE_PROJECT_DIR=project.as_posix())

        def run(name, payload):
            return subprocess.run([shutil.which('sh'), '-c', python_hooks[name]], input=json.dumps(payload),
                                  text=True, capture_output=True, timeout=30, env=env, cwd=project)

        blocked = run('guard_destructive_git.py', {'tool_name': 'Bash', 'tool_input': {'command': 'git reset --hard'}})
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertIn('BLOCKED', blocked.stderr)
        # The overlay's boundary list is the setup placeholder, which the hook must report.
        unconfigured = run('guard_boundaries.py', {'tool_input': {'file_path': 'a.py', 'content': 'import b'}})
        self.assertEqual(unconfigured.returncode, 0, unconfigured.stderr)
        self.assertIn('UNCONFIGURED', unconfigured.stdout)
        self.transcript.write_text(''.join(json.dumps(r) + '\n' for r in [prompt(), request(210_000)]))
        said = run('context_size.py', {'transcript_path': str(self.transcript)})
        self.assertEqual((said.returncode, said.stderr), (0, ''))
        self.assertIn('Context is 210k tokens', said.stdout)

if __name__ == '__main__':
    unittest.main()

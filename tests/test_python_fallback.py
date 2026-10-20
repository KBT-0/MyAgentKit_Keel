"""Hooks and scripts must run where `python3` is on PATH but does not run (issue #67)."""
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
# Run inside a worker, the suite inherits the caller's brief: review.sh then checked the
# fixture's diff against the caller's Owns: line. A case that needs one sets it explicitly.
os.environ.pop('REVIEW_TASK_FILE', None)


class PythonFallbackTests(unittest.TestCase):
    def test_hooks_and_scripts_run_where_python3_does_not(self):
        # Windows installs Python as `python`, and its `python3` may be a Store alias that is on
        # PATH but exits 9009. A hook command naming python3 then failed, Claude Code went on
        # without the hook, and a script that checked `command -v python3` picked it all the same.
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        hooks = json.loads((OVERLAY / '.claude/settings.json').read_text(encoding='utf-8'))['hooks']
        commands = [h['command'] for entries in hooks.values() for e in entries for h in e['hooks']]
        python_hooks = {Path(c.split('"')[-2]).name: c for c in commands if '.py"' in c}
        self.assertEqual(sorted(python_hooks), ['context_size.py', 'guard_boundaries.py', 'guard_destructive_git.py',
                                                'guard_private_email.py', 'guard_root_scan.py', 'guard_worker_route.py', 'plain_report.py',
                                                'progress_reminder.py'], commands)
        for command in python_hooks.values():
            self.assertTrue(command.startswith('sh "$CLAUDE_PROJECT_DIR/.claude/hooks/py.sh" '), command)
        bin_dir = tmp / 'bin'
        bin_dir.mkdir()
        for name, body in (('python3', 'exit 9009'), ('python', 'exec "%s" "$@"' % Path(sys.executable).as_posix())):
            (bin_dir / name).write_text('#!/bin/sh\n%s\n' % body, encoding='utf-8', newline='\n')
            (bin_dir / name).chmod(0o755)
        project = tmp / 'project'
        shutil.copytree(OVERLAY / '.claude/hooks', project / '.claude/hooks')
        # A dirty repository, so the guard has work to lose. GIT_* from a calling hook would
        # route git elsewhere. Exercise owner-facing hooks even when the caller is a worker.
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k != 'MYAGENTKIT_ROLE'}
        subprocess.run(['git', 'init', '-q', str(project)], check=True, env=env)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty',
                        '-m', 'x'], cwd=project, check=True, env=env)
        (project / 'notes.txt').write_text('uncommitted\n', encoding='utf-8')
        env.update(PATH=os.pathsep.join([str(bin_dir), env['PATH']]), CLAUDE_PROJECT_DIR=project.as_posix(),
                   XDG_CACHE_HOME=(tmp / 'cache').as_posix())  # never the developer's interpreter cache

        def run(args, payload=''):
            # A hook writes in the locale's code page under some runners: decoded leniently.
            return subprocess.run(args, input=payload, encoding='utf-8', errors='replace',
                                  capture_output=True, timeout=60, env=env, cwd=project)

        self.assertNotEqual(run(['sh', '-c', 'python3 -c ""']).returncode, 0)  # the alias stands first
        blocked = run(['sh', '-c', python_hooks['guard_destructive_git.py']],
                      json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git reset --hard'}}))
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertIn('BLOCKED', blocked.stderr)
        subprocess.run(['git', 'config', 'user.email', 'owner@example.com'], cwd=project, check=True, env=env)
        mailed = run(['sh', '-c', python_hooks['guard_private_email.py']],
                     json.dumps({'tool_name': 'WebFetch', 'tool_input': {'url': 'https://x.example/?m=owner@example.com'}}))
        self.assertEqual(mailed.returncode, 2, mailed.stderr)
        rooted = run(['sh', '-c', python_hooks['guard_root_scan.py']],
                     json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'find / -name x.h'}}))
        self.assertEqual(rooted.returncode, 2, rooted.stderr)
        # A subagent names its model and effort, or it inherits the lead's; a fork cannot.
        route = python_hooks['guard_worker_route.py']
        for call, code in (({'prompt': 'x'}, 2), ({'model': 'sonnet'}, 2), ({'effort': 'medium'}, 2),
                           ({'model': 'sonnet', 'effort': 'medium'}, 0), ({'subagent_type': 'fork'}, 0)):
            with self.subTest(call=call):
                result = run(['sh', '-c', route], json.dumps({'tool_name': 'Agent', 'tool_input': call}))
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual('BLOCKED' in result.stderr, code == 2, result.stderr)
        self.assertEqual(run(['sh', '-c', route], json.dumps({'tool_name': 'Bash', 'tool_input': {}})).returncode, 0)
        # The overlay's boundary list is the setup placeholder, which the hook must report.
        unconfigured = run(['sh', '-c', python_hooks['guard_boundaries.py']],
                           json.dumps({'tool_input': {'file_path': 'a.py', 'content': 'import b'}}))
        self.assertEqual(unconfigured.returncode, 0, unconfigured.stderr)
        self.assertIn('UNCONFIGURED', unconfigured.stdout)
        transcript = tmp / 'session.jsonl'
        transcript.write_text(json.dumps({'type': 'assistant', 'message': {'usage': {
            'input_tokens': 210_000, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}}}) + '\n', encoding='utf-8')
        said = run(['sh', '-c', python_hooks['context_size.py']], json.dumps({'transcript_path': str(transcript)}))
        self.assertEqual((said.returncode, said.stderr), (0, ''))
        self.assertIn('Context is 210k tokens', said.stdout)
        report = json.dumps({'last_assistant_message': 'D-5 is done.'})
        # Missing canonical grammar fails open; an installed project supplies commit-msg.
        unconfigured = run(['sh', '-c', python_hooks['plain_report.py']], report)
        self.assertEqual((unconfigured.returncode, unconfigured.stderr), (0, ''))
        (project / '.githooks').mkdir()
        shutil.copyfile(ROOT / 'core/.githooks/commit-msg', project / '.githooks/commit-msg')
        bounced = run(['sh', '-c', python_hooks['plain_report.py']], report)
        self.assertEqual(bounced.returncode, 2, bounced.stderr)
        self.assertIn('BLOCKED', bounced.stderr)
        transcript.write_text(''.join(json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Read'}]}}) + '\n' for _ in range(5)), encoding='utf-8')
        nudged = run(['sh', '-c', python_hooks['progress_reminder.py']], json.dumps({'transcript_path': str(transcript)}))
        self.assertEqual((nudged.returncode, nudged.stderr), (0, ''))
        self.assertIn('additionalContext', nudged.stdout)
        # No interpreter runs at all: a guard blocks (exit 2) and says why; any other hook only
        # reports, since exit 2 from UserPromptSubmit or Stop would block every prompt or refuse
        # every stop. The root-scan guard fails open: it must not refuse every shell call (#298).
        (bin_dir / 'python').write_text('#!/bin/sh\nexit 9009\n', encoding='utf-8', newline='\n')
        (bin_dir / 'py').write_text('#!/bin/sh\nexit 1\n', encoding='utf-8', newline='\n')
        (bin_dir / 'py').chmod(0o755)
        sh = shutil.which('sh')
        # The hook's file name decides, never a folder above it (Codex review of f68a68d).
        for hook, code in (('guard_destructive_git.py', 2), ('guard_root_scan.py', 1), ('context_size.py', 1),
                           ('guard_x/context_size.py', 1),
                           ('guard_x\\context_size.py', 1), ('a\\guard_y.py', 2)):
            with self.subTest(no_python=hook):
                script = Path(str(project / '.claude/hooks') + '/' + hook)  # py.sh refuses a missing file first
                script.parent.mkdir(parents=True, exist_ok=True)
                script.touch()
                bare =subprocess.run([sh, str(project / '.claude/hooks/py.sh'), str(project / '.claude/hooks') + '/' + hook],
                                      input='{}', encoding='utf-8', errors='replace', capture_output=True,
                                      timeout=60, env=dict(env, PATH=str(bin_dir)), cwd=project)
                self.assertEqual(bare.returncode, code, bare.stderr)
                self.assertIn('no Python found; install it or run doctor', bare.stderr)
        (bin_dir / 'python').write_text('#!/bin/sh\nexec "%s" "$@"\n' % Path(sys.executable).as_posix(), encoding='utf-8', newline='\n')
        # A gate script that execs its resolved Python.
        cleaned = run(['sh', str(OVERLAY / 'scripts/clean_worktrees.sh')])
        self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
        self.assertIn('dry run', cleaned.stdout)
        # The gate, doctor and review entry points, each beside stand-ins for what they start.
        scripts = project / 'scripts'
        scripts.mkdir()
        for name in ('check.sh', 'doctor.sh', 'review.sh'):
            shutil.copy(ROOT / 'core/scripts' / name, scripts / name)
        (scripts / 'review_dispatch.py').write_text('import sys; print("dispatched", sys.argv[1])\n', encoding='utf-8')
        (scripts / 'test_claude_bridge.py').write_text('print("REVIEW SELF-TEST: PASS")\n', encoding='utf-8')
        gate = run(['sh', 'scripts/check.sh'])  # unconfigured: it fails, but past the lock's exec
        self.assertIn('CHECK: FAIL', gate.stdout + gate.stderr)
        self.assertNotIn('FAIL [lock]', gate.stdout + gate.stderr)
        doctor = run(['sh', 'scripts/doctor.sh'])
        self.assertIn('DOCTOR:', doctor.stdout)
        self.assertNotIn('MISSING: Python', doctor.stdout)
        review = run(['sh', 'scripts/review.sh', '--self-test'])  # the python3 function
        self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
        review = run(['sh', 'scripts/review.sh', '--reviewer', 'codex'])  # the exec of $kit_python
        self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
        self.assertIn('dispatched --repo', review.stdout)
        # Every script chooses the same way: by running the candidate, never by `command -v`.
        shipped = [*ROOT.glob('core/scripts/*.sh'), *ROOT.glob('overlays/*/files/**/*.sh')]
        chosen = [line.strip() for p in shipped for line in p.read_text(encoding='utf-8').splitlines()
                  if 'then kit_python=' in line]
        self.assertGreaterEqual(len(chosen), 12, chosen)
        self.assertEqual([line for line in chosen if 'command -v' in line], [])

    def test_py_sh_probes_once_and_never_blocks_on_a_missing_hook(self):
        # #83: the probe is a second Python start per hook; the interpreter that passed it is cached.
        # #139: CPython exits 2 on a missing script, which from UserPromptSubmit blocks every prompt.
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        bin_dir, hooks, log = tmp / 'bin', tmp / 'hooks', tmp / 'starts.log'
        bin_dir.mkdir()
        hooks.mkdir()
        shutil.copy(OVERLAY / '.claude/hooks/py.sh', hooks)
        (hooks / 'guard_x.py').write_text('import sys; sys.stdin.read(); sys.exit(2)\n', encoding='utf-8')
        marker = tmp / 'foreign-ran'
        for name, body in (('python3', 'exit 9009'), ('py', 'exit 1'), ('evil', 'touch "%s"' % marker.as_posix()),
                           ('python', 'printf "%%s\\n" "$*" >>"%s"\nexec "%s" "$@"' % (log.as_posix(), Path(sys.executable).as_posix()))):
            (bin_dir / name).write_text('#!/bin/sh\n%s\n' % body, encoding='utf-8', newline='\n')
            (bin_dir / name).chmod(0o755)
        cache = tmp / 'cache/myagentkit-python'
        env = dict(os.environ, PATH=os.pathsep.join([str(bin_dir), os.environ['PATH']]),
                   XDG_CACHE_HOME=(tmp / 'cache').as_posix())
        sh = shutil.which('sh')

        def hook(name):
            log.write_text('', encoding='utf-8')
            result = subprocess.run([sh, str(hooks / 'py.sh'), (hooks / name).as_posix()], input='{}', env=env,
                                    encoding='utf-8', errors='replace', capture_output=True, timeout=60)
            return result, sum(1 for line in log.read_text(encoding='utf-8').splitlines() if line.startswith('-I -c'))

        # stale: a Store alias that stopped running; failing: `py` with no Python exits 1 before the
        # hook (round-1 review); foreign: a name outside the three never runs from the cache.
        for state, cached in (('empty', None), ('cached', None), ('stale', 'python3'), ('failing', 'py -3'),
                              ('foreign', 'evil')):
            with self.subTest(cache=state):
                if cached:
                    cache.write_text(cached + '\n', encoding='utf-8', newline='\n')  # py.sh writes LF
                result, probes = hook('guard_x.py')
                self.assertEqual(result.returncode, 2, result.stderr)  # the guard ran and blocked
                self.assertEqual(probes, 0 if state == 'cached' else 1)
                self.assertEqual(cache.read_text(encoding='utf-8'), 'python\n')
                self.assertFalse(marker.exists())
        # No interpreter runs at all and the cached `py -3` exits 1: the guard still fails closed.
        alone = tmp / 'alone'
        alone.mkdir()
        for name, body in (('python3', 'exit 9009'), ('python', 'exit 9009'), ('py', 'exit 1')):
            (alone / name).write_text('#!/bin/sh\n%s\n' % body, encoding='utf-8', newline='\n')
            (alone / name).chmod(0o755)
        cache.write_text('py -3\n', encoding='utf-8', newline='\n')
        bare = subprocess.run([sh, str(hooks / 'py.sh'), (hooks / 'guard_x.py').as_posix()], input='{}',
                              env=dict(env, PATH=str(alone)), encoding='utf-8', errors='replace',
                              capture_output=True, timeout=60)
        self.assertEqual(bare.returncode, 2, bare.stderr)
        self.assertIn('no Python found', bare.stderr)
        for name, code in (('context_size.py', 1), ('plain_report.py', 1), ('guard_gone.py', 2),
                           ('guard_root_scan.py', 1)):
            with self.subTest(missing=name):
                result, _ = hook(name)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn('hook file missing or unreadable', result.stderr)

    def test_py_sh_passes_the_kit_shell_lint(self):
        # The kit check refused py.sh's `echo` of an expansion (Codex review of f68a68d).
        probe = ('import sys; sys.path.insert(0, "scripts"); import check_kit, pathlib; '
                 'print(check_kit.shell_lint(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")))')
        result = subprocess.run([sys.executable, '-c', probe, str(OVERLAY / '.claude/hooks/py.sh')], cwd=ROOT,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '[]'), result.stderr)


if __name__ == '__main__':
    unittest.main()

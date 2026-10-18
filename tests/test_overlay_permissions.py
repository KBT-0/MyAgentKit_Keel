"""The overlay's permission allowlist lets routine reads run unasked and nothing that destroys.

A rule's `*` admits any further argument: `Bash(git branch -v*)` admitted `git branch -vD x`,
and `Bash(git diff*)` admitted `git diff --output=owner.txt`, which overwrites the file. Checked
in Claude Code (default mode, 2026-10-09): a rule without `*` is matched exactly, a deny rule
outranks an allow rule, and a redirect (`cat a > b`) or a chained command (`ls && rm x`) is
not admitted by `Bash(cat *)` or `Bash(ls*)`.
"""
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SETTINGS = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/settings.json'
DESTROYS = ('rm', 'mv', 'cp', 'kill', 'taskkill', 'pkill', 'git reset', 'git clean', 'git push', 'git checkout',
            'git restore', 'git stash', 'git rebase', 'git merge', 'git commit', 'git worktree remove',
            'Remove-Item', 'Stop-Process', 'Set-Content', 'Move-Item')
SHELL_TOOLS = ('Bash', 'PowerShell', 'Monitor')  # every Claude Code tool that runs a command


class OverlayPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.permissions = json.loads(SETTINGS.read_text(encoding='utf-8'))['permissions']

    def test_no_allowed_rule_names_a_command_that_destroys(self):
        for rule in self.permissions['allow']:
            command = rule[rule.index('(') + 1:-1].lstrip('./')
            with self.subTest(rule=rule):
                self.assertFalse(any(command == d or command.startswith(d + ' ') or command.startswith(d + '*')
                                     for d in DESTROYS), rule)

    def test_a_wildcard_ends_a_rule_after_a_whole_word(self):
        # `Bash(git -C * diff*)` admitted `git -C . branch -D diff-victim`: a `*` before the
        # subcommand stands for any subcommand. `Bash(git diff*)` admitted `git difftool
        # --extcmd=...`, and `Bash(date*)` admitted `date -s`: a `*` glued to a word extends it.
        for rule in self.permissions['allow']:
            with self.subTest(rule=rule):
                self.assertNotIn('*', rule[:-2], rule)
                self.assertTrue('*' not in rule or rule.endswith(' *)'), rule)

    def test_diff_driver_arguments_are_denied(self):
        self.assertIn('Bash(git *--ext*)', self.permissions['deny'])
        self.assertIn('Bash(git *--sub*)', self.permissions['deny'])
        for cmd in ('log', 'diff', 'show'):
            for mode in ('diff', 'log'):
                command = 'git %s --no-textconv --no-ext-diff --submodule=%s' % (cmd, mode)
                with self.subTest(command=command):
                    self.assertFalse(self.allowed(command), command)

    def test_git_textconv_commands_are_not_allowed(self):
        # Git's display commands can execute a repository-configured converter without
        # --ext-diff. Prove it runs, then check the shipped rules would still require a prompt.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_PAGER='cat')
            def git(*args, check=True):
                return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                                       '-c', 'core.hooksPath=.git/hooks', *args], cwd=root, env=env,
                                      capture_output=True, text=True, encoding='utf-8', check=check, timeout=30)
            git('init', '-q')
            (root / '.gitattributes').write_bytes(b'data.dat diff=probe\n')
            (root / 'data.dat').write_bytes(b'before\n')
            git('add', '.gitattributes', 'data.dat')
            git('commit', '-q', '-m', 'base')
            (root / 'textconv.sh').write_bytes(b': > textconv-ran\ncat "$1"\n')
            git('config', 'diff.probe.textconv', 'sh textconv.sh')
            (root / 'data.dat').write_bytes(b'after\n')
            marker = root / 'textconv-ran'
            for args in (('diff',), ('diff', '-p'), ('show', 'HEAD'), ('log', '-p'),
                         ('show', 'HEAD', '--', 'data.dat'),
                         ('log', '-p', '--textconv', 'HEAD', '--', 'data.dat')):
                with self.subTest(args=args):
                    git(*args)
                    self.assertTrue(marker.exists(), 'Git did not execute the textconv fixture')
                    marker.unlink()
                    for command in ('git ' + args[0], 'git ' + ' '.join(args),
                                    'git %s --no-textconv --no-ext-diff %s --textconv' % (args[0], ' '.join(args[1:]))):
                        self.assertFalse(self.allowed(command), command)
            # Prove abbreviated overrides are denied even on older Git that rejects them.
            (root / 'external.sh').write_bytes(b': > external-ran\n')
            git('config', 'diff.probe.command', 'sh external.sh')
            for cmd in ('diff', 'log', 'show'):
                for prefixes, suffix, effect in ((('out', 'output'), '=written.diff', 'written.diff'),
                                                 (('ext', 'ext-d', 'ext-diff'), '', 'external-ran'),
                                                 (('textc', 'textcon', 'textconv'), '', 'textconv-ran'),
                                                 (('sub', 'submod', 'submodule'), '=diff', None)):
                    for prefix in prefixes:
                        flag = '--' + prefix + suffix
                        command = ('git', cmd, '--no-textconv', '--no-ext-diff', '-p', flag)
                        with self.subTest(command=command):
                            result = git(*command[1:], check=prefix == prefixes[-1])
                            self.assertFalse(self.allowed(' '.join(command)), command)
                            if result.returncode:
                                self.assertRegex(result.stderr, r'(invalid option|unrecognized argument):')
                                self.assertIn(flag, result.stderr)
                            if effect:
                                marker = root / effect
                                self.assertEqual(marker.exists(), result.returncode == 0, result.stderr)
                                marker.unlink(missing_ok=True)
            # The allowed form runs neither driver; later overrides above are denied.
            for args in (('diff',), ('show', 'HEAD', '--', 'data.dat'), ('log', '-p', 'HEAD', '--', 'data.dat')):
                with self.subTest(safe=args):
                    command = ('git', args[0], '--no-textconv', '--no-ext-diff', *args[1:])
                    self.assertTrue(self.allowed(' '.join(command)), command)
                    git(*command[1:])
                    self.assertFalse((root / 'textconv-ran').exists(), command)
                    self.assertFalse((root / 'external-ran').exists(), command)

    def allowed(self, command):
        matches = lambda kind: any(fnmatch.fnmatchcase('Bash(' + command + ')', rule)
                                   for rule in self.permissions[kind])
        return matches('allow') and not matches('deny')

    def test_git_branch_is_allowed_only_in_exact_listing_forms(self):
        branch = [r for r in self.permissions['allow'] if r.startswith('Bash(git branch')]
        self.assertTrue(branch)
        for rule in branch:
            with self.subTest(rule=rule):
                self.assertNotIn('*', rule)
                self.assertNotIn('-d', rule.lower().replace('--merged', '').replace('--show-current', ''))

    def test_an_output_file_option_is_denied_to_every_git_command(self):
        self.assertIn('Bash(git *--out*)', self.permissions['deny'])


class OverlaySettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads(SETTINGS.read_text(encoding='utf-8'))

    def test_every_guard_blocks_when_it_fails(self):
        # Any exit but 2 (a crash, no interpreter, a timeout) lets the call through unless the hook
        # says `onFailure: block` (Claude Code v2.1.295+, https://code.claude.com/docs/en/hooks).
        guards = [h for e in self.settings['hooks']['PreToolUse'] for h in e['hooks']]
        self.assertEqual(sorted(h['command'].split('/')[-1].rstrip('"') for h in guards),
                         ['guard_destructive_git.py', 'guard_private_email.py', 'guard_worker_route.py'])
        for hook in guards:
            with self.subTest(hook=hook['command']):
                self.assertEqual(hook.get('onFailure'), 'block')
        matchers = {e['matcher'] for e in self.settings['hooks']['PreToolUse']}
        self.assertIn('WebFetch|WebSearch|' + '|'.join(SHELL_TOOLS), matchers)

    def test_every_command_guard_covers_every_shell_tool(self):
        # #93, #213: a guard wired to "Bash" alone let PowerShell and Monitor calls through. The
        # hooks read tool_input.command from any tool, so the matcher is the one list to extend.
        for path in (SETTINGS, SETTINGS.parents[4] / '.claude/settings.json'):  # overlay, kit's own
            for entry in json.loads(path.read_text(encoding='utf-8'))['hooks']['PreToolUse']:
                command = entry['hooks'][0]['command']
                if 'guard_destructive_git' in command or 'guard_private_email' in command:
                    with self.subTest(path=str(path), hook=command):
                        self.assertLessEqual(set(SHELL_TOOLS), set(entry['matcher'].split('|')))

    def test_an_agent_whose_definition_pins_model_and_effort_needs_neither_on_the_call(self):
        # #137: diff-reviewer and worker pin both; forcing call-site values could only downgrade them.
        hook = SETTINGS.parent / 'hooks/guard_worker_route.py'
        with tempfile.TemporaryDirectory() as project:
            agents = Path(project) / '.claude/agents'
            agents.mkdir(parents=True)
            (agents / 'pinned.md').write_text('---\nname: pinned\nmodel: claude-opus-5-5\neffort: high\n---\nx\n')
            (agents / 'half.md').write_text('---\nname: half\nmodel: claude-opus-5-5\n---\nx\n')
            (agents / 'unset.md').write_text('---\nname: unset\nmodel: {{WORKER_MODEL}}\neffort: high\n---\nx\n')
            env = {k: v for k, v in os.environ.items() if k not in ('HOME', 'USERPROFILE')}
            env.update(CLAUDE_PROJECT_DIR=project, HOME=project, USERPROFILE=project)
            for kind, code in [('pinned', 0), ('half', 2), ('unset', 2), ('general-purpose', 2), ('fork', 0)]:
                payload = json.dumps({'tool_name': 'Agent', 'tool_input': {'subagent_type': kind, 'prompt': 'p'}})
                with self.subTest(kind=kind):
                    result = subprocess.run([sys.executable, str(hook)], input=payload.encode(), env=env,
                                            capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, code, result.stderr)

    def test_the_tool_adds_no_attribution(self):
        # The trailer is turned off at its source; .githooks/commit-msg stays the backstop.
        self.assertEqual(self.settings['attribution'], {'commit': '', 'pr': ''})


if __name__ == '__main__':
    unittest.main()

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
import tempfile
import unittest

SETTINGS = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/settings.json'
DESTROYS = ('rm', 'mv', 'cp', 'kill', 'taskkill', 'pkill', 'git reset', 'git clean', 'git push', 'git checkout',
            'git restore', 'git stash', 'git rebase', 'git merge', 'git commit', 'git worktree remove',
            'Remove-Item', 'Stop-Process', 'Set-Content', 'Move-Item')


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


if __name__ == '__main__':
    unittest.main()

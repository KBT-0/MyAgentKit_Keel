"""The overlay's permission allowlist lets routine reads run unasked and nothing that destroys.

A rule's `*` admits any further argument: `Bash(git branch -v*)` admitted `git branch -vD x`,
and `Bash(git diff*)` admitted `git diff --output=owner.txt`, which overwrites the file. Checked
in Claude Code (default mode, 2026-10-09): a rule without `*` is matched exactly, a deny rule
outranks an allow rule, and a redirect (`cat a > b`) or a chained command (`ls && rm x`) is
not admitted by `Bash(cat *)` or `Bash(ls*)`.
"""
import json
from pathlib import Path
import unittest

SETTINGS = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/settings.json'
DESTROYS = ('rm', 'mv', 'cp', 'kill', 'taskkill', 'pkill', 'git reset', 'git clean', 'git push', 'git checkout',
            'git restore', 'git stash', 'git rebase', 'git merge', 'git commit', 'git worktree remove',
            'Remove-Item', 'Stop-Process', 'Set-Content', 'Move-Item')


class OverlayPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.permissions = json.loads(SETTINGS.read_text())['permissions']

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

    def test_an_external_diff_driver_is_denied(self):
        self.assertIn('Bash(git *--ext-diff*)', self.permissions['deny'])

    def test_git_branch_is_allowed_only_in_exact_listing_forms(self):
        branch = [r for r in self.permissions['allow'] if r.startswith('Bash(git branch')]
        self.assertTrue(branch)
        for rule in branch:
            with self.subTest(rule=rule):
                self.assertNotIn('*', rule)
                self.assertNotIn('-d', rule.lower().replace('--merged', '').replace('--show-current', ''))

    def test_an_output_file_option_is_denied_to_every_git_command(self):
        self.assertIn('Bash(git *--output*)', self.permissions['deny'])


if __name__ == '__main__':
    unittest.main()

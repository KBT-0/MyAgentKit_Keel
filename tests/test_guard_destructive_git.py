"""guard_destructive_git.py: which git commands an agent's Bash call may run.

A command that discards work in the tree is refused while the tree is dirty; one that loses work
whatever the tree's state (a dropped stash, a rewritten remote, a skipped gate) is always refused.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_destructive_git.py'
ENV = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')


def git(cwd, *args):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args], cwd=cwd,
                          env=ENV, capture_output=True, encoding='utf-8', errors='replace', check=True, timeout=60)


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q', '-b', 'main')
        (self.repo / 'f.txt').write_text('one\n', encoding='utf-8')
        git(self.repo, 'add', 'f.txt')
        git(self.repo, 'commit', '-q', '-m', 'base')

    def run_hook(self, command, cwd=None, payload=None, python_args=()):
        payload = payload if payload is not None else json.dumps({'tool_name': 'Bash', 'tool_input': {'command': command}})
        return subprocess.run([sys.executable, *python_args, str(HOOK)], input=payload.encode('utf-8'),
                              cwd=cwd or self.repo, env=ENV, capture_output=True, timeout=60)

    def assertVerdict(self, commands, code, **kw):
        for command in commands:
            with self.subTest(command=command):
                result = self.run_hook(command, **kw)
                self.assertEqual(result.returncode, code, result.stderr.decode('utf-8', 'replace'))

    def dirty(self):
        (self.repo / 'f.txt').write_text('two\n', encoding='utf-8')


class GuardDestructiveGitTests(GuardCase):
    def test_loss_certain_commands_are_refused_on_a_clean_tree(self):
        self.assertVerdict([
            'git stash drop', 'git stash clear', 'git -C . stash drop',
            'git push --force', 'git push -f origin main', 'git push origin +main', 'git push --mirror',
            'git push --delete origin x', 'git push origin :x', 'git push --force-with-lease',
            'git push --force-with-lease=main', 'git push --force-with-lease=main:abc --force',
            'git remote set-url origin x', 'git remote add up x', 'git -C . remote add up x',
            'echo ok && git push -f', "sh -c 'git push --force'",
        ], 2)

    def test_gate_bypasses_are_refused(self):
        self.assertVerdict([
            'git commit --no-verify -m x', 'git commit -n -m x', 'git commit -nm x', 'git commit -anm x',
            'git -c core.hooksPath=/dev/null commit -m x', 'git -c core.hookspath= commit -m x',
            'git commit --no-gpg-sign -m x', 'git push --no-verify', 'git merge --no-verify x',
        ], 2)
        result = self.run_hook('git commit --no-verify -m x')
        self.assertIn('Only the owner bypasses this gate', result.stderr.decode('utf-8'))

    def test_safe_forms_pass_on_a_clean_tree(self):
        self.assertVerdict([
            'git status', 'git log --oneline -n 5', 'git push origin main', 'git push -n origin main',
            'git push --force-with-lease=main:abc123 origin main', 'git push --force-with-lease --force-if-includes',
            'git commit -m x', 'git commit -mn', "git commit -m 'do not use --no-verify'", 'git commit -m "refuse git push --force"','git stash list',
            'git remote -v', 'git reset --hard', 'git -c color.ui=never status', 'ls -n',
        ], 0)

    def test_work_discarding_commands_are_refused_on_a_dirty_tree(self):
        self.dirty()
        self.assertVerdict([
            'git reset --hard', 'git -C . reset --hard', 'git -c x.y=1 reset --hard HEAD',
            'git checkout -- f.txt', 'git checkout -f', 'git restore f.txt', 'git restore --staged --worktree f.txt',
            'git restore -SW f.txt', 'git clean -fd', 'git clean -x -f', 'git clean --force',
        ], 2)

    def test_index_only_and_dry_run_forms_pass_on_a_dirty_tree(self):
        self.dirty()
        self.assertVerdict([
            'git clean -nd', 'git clean --dry-run -fd', 'git clean -n', 'git restore --staged f.txt',
            'git restore -S f.txt', 'git checkout main', 'git status',
        ], 0)

    def test_the_dirty_check_reads_the_tree_git_dash_C_names(self):
        self.dirty()
        self.assertVerdict(['git -C repo reset --hard'], 2, cwd=self.tmp)

    def test_amending_a_pushed_commit_is_refused(self):
        remote = self.tmp / 'remote.git'
        git(self.tmp, 'init', '-q', '--bare', str(remote))
        git(self.repo, 'remote', 'add', 'origin', str(remote))
        git(self.repo, 'push', '-q', 'origin', 'main')
        self.assertVerdict(['git commit --amend --no-edit'], 2)
        git(self.repo, 'commit', '-q', '--allow-empty', '-m', 'local')
        self.assertVerdict(['git commit --amend --no-edit'], 0)

    def test_an_unreadable_payload_blocks(self):
        result = self.run_hook(None, payload='not json')
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_git_status_is_read_as_utf8(self):
        # A text subprocess without an encoding raised EncodingWarning inside `except Exception`,
        # so a clean tree was taken for a dirty one (BACKLOG, D-1 r2).
        result = self.run_hook('git reset --hard', python_args=('-X', 'warn_default_encoding', '-W', 'error::EncodingWarning'))
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))


class ReviewRoundOneTests(GuardCase):
    """Codex review of f68a68d: what the hook can parse it reads as git and the shell would;
    what it cannot parse it refuses."""

    def side_repo(self, name='b'):
        side = self.tmp / name
        side.mkdir()
        git(side, 'init', '-q', '-b', 'main')
        (side / 'w.txt').write_text('one\n', encoding='utf-8')
        git(side, 'add', 'w.txt')
        git(side, 'commit', '-q', '-m', 'base')
        (side / 'w.txt').write_text('owner edit\n', encoding='utf-8')
        return side

    def test_constructs_it_cannot_read_are_refused(self):
        self.dirty()
        self.assertVerdict([
            'echo `git reset --hard`', 'echo $(git reset --hard)', "sh -lc 'git reset --hard'",
            "bash -ec 'git stash drop'", 'eval "git reset --hard"', 'git \\\nreset --hard',
            "bash <<'EOF'\ngit reset --hard\nEOF", 'echo "git reset --hard" | sh',
            'sudo git reset --hard', 'xargs git reset --hard',
        ], 2)
        result = self.run_hook("sh -lc 'git status'")
        self.assertIn('run the git command directly', result.stderr.decode('utf-8'))

    def test_option_values_and_literals_are_read_as_git_reads_them(self):
        (self.repo / 'owner-notes.txt').write_text('only copy\n', encoding='utf-8')
        self.assertVerdict(['git clean -e -n -f', 'git clean --exclude -n -f'], 2)
        git(self.repo, 'add', 'owner-notes.txt')
        git(self.repo, 'commit', '-q', '-m', 'notes')
        self.assertVerdict([
            'git log -- --no-verify', 'git commit --allow-empty -m --no-verify', 'echo git push --force',
            'git commit -F msg.txt', 'git log --grep --no-verify', 'printf "%s" "git stash drop"',
            "git commit -F - <<'EOF'\ndon't git push --force\nEOF",
            'git commit -m "$(cat <<\'EOF\'\nrefuse git push --force\nEOF\n)"',
        ], 0)

    def test_last_option_wins_and_abbreviations_count(self):
        self.assertVerdict([
            'git push --force-with-lease --force-if-includes --no-force-if-includes origin main',
            'git push --force-with-lease=main:abc --no-force-with-lease --force origin main',
            'git commit --no-veri -m x', 'git commit --no-gpg -m x', 'git push --forc origin main',
            'git push --mirr', 'git commit --verify --no-verify -m x',
        ], 2)
        self.assertVerdict(['git commit --no-verify --verify -m x', 'git push --no-force origin main',
                            'git push --force --no-force origin main'], 0)

    def test_the_target_repository_is_the_one_checked(self):
        # The caller's own repository is clean; the command reaches the dirty one beside it.
        self.side_repo()
        self.assertVerdict([
            'git --git-dir=../b/.git --work-tree=../b reset --hard', 'git --git-dir ../b/.git --work-tree ../b reset --hard',
            'cd ../b && git reset --hard', 'cd ../b; git reset --hard', 'GIT_DIR=../b/.git GIT_WORK_TREE=../b git reset --hard',
            'git -C ../b reset --hard',
        ], 2)
        self.assertVerdict(['cd ../repo && git reset --hard', 'cd ../b && git status'], 0)

    def test_an_alias_is_resolved_before_matching(self):
        git(self.repo, 'config', 'alias.wipe', 'reset --hard')
        git(self.repo, 'config', 'alias.shout', '!git reset --hard')
        self.assertVerdict(['git wipe', 'git shout', 'git -c alias.zap="reset --hard" zap'], 0)
        self.dirty()
        self.assertVerdict(['git wipe', 'git shout', 'git -c alias.zap="reset --hard" zap'], 2)
        self.assertVerdict(['git lol'], 0)

    def test_windows_spelling_of_git_is_matched(self):
        self.dirty()
        self.assertVerdict(['GIT.EXE reset --hard', 'Git reset --hard', "'C:\\Git\\cmd\\git.exe' reset --hard", '"C:/Program Files/Git/cmd/git.exe" reset --hard'], 2)

    def test_a_command_after_a_state_change_is_judged_dirty(self):
        self.assertVerdict(['git stash pop && git reset --hard', 'git checkout other; git clean -fd',
                            'touch x && git reset --hard'], 2)
        self.assertVerdict(['git status && git reset --hard', 'cd . && git reset --hard'], 0)

    def test_ignored_files_count_for_clean_x(self):
        (self.repo / '.gitignore').write_text('.env\n', encoding='utf-8')
        git(self.repo, 'add', '.gitignore')
        git(self.repo, 'commit', '-q', '-m', 'ignore')
        (self.repo / '.env').write_text('SECRET=only copy\n', encoding='utf-8')
        self.assertVerdict(['git clean -fdx', 'git clean -fX', 'git clean -f -x -d'], 2)
        self.assertVerdict(['git clean -fd'], 0)

    def test_gate_routes_around_the_hook_are_refused(self):
        self.assertVerdict([
            'git config core.hooksPath /dev/null', 'git config --local core.hookspath x',
            'git config set core.hooksPath x', 'git config --unset core.hooksPath',
            'HUSKY=0 git commit -m x', 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=x git commit -m x',
            'export GIT_CONFIG_PARAMETERS="\'core.hooksPath\'=\'x\'"; git commit -m x', 'SKIP=check git push origin main',
            'git --config-env=core.hooksPath=V commit -m x',
        ], 2)
        self.assertVerdict(['git config --get core.hooksPath', 'git config core.hooksPath', 'HUSKY=0 git status'], 0)

    def test_checkout_of_a_path_without_dashes_is_dirty_sensitive(self):
        self.dirty()
        self.assertVerdict(['git checkout f.txt', 'git checkout .'], 2)
        self.assertVerdict(['git checkout main', 'git checkout -b feature'], 0)


class ReviewRoundTwoTests(GuardCase):
    """Opus review round 2: a here-document a shell reads, and a cd that does not leak out."""

    def test_a_here_document_any_shell_reads_is_refused(self):
        self.dirty()
        self.assertVerdict([
            "cat <<'EOF' | sh\ngit reset --hard\nEOF", "cat <<EOF | bash -s\ngit reset --hard\nEOF",
            "tee x.sh <<'EOF'\ngit reset --hard\nEOF\nsh x.sh",
        ], 2)
        git(self.repo, 'checkout', '--', 'f.txt')
        self.assertVerdict(["cat <<'EOF' | sh\ngit push --force\nEOF", "cat <<'EOF' | sh\ngit commit --no-verify -m x\nEOF"], 2)
        self.assertVerdict(["cat <<'EOF' > notes.md\ngit push --force is refused\nEOF"], 0)

    def test_a_cd_inside_a_subshell_or_pipeline_does_not_leak(self):
        side = self.tmp / 'b'
        side.mkdir()
        git(side, 'init', '-q', '-b', 'main')
        self.dirty()
        self.assertVerdict([
            '(cd ../b && git status) && git reset --hard', '(cd ../b) ; git reset --hard',
            'cd ../b | true; git reset --hard', 'true | cd ../b && git reset --hard',
        ], 2)
        self.assertVerdict(['(cd ../b && git reset --hard)'], 2)


if __name__ == '__main__':
    unittest.main()

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
        result = self.run_hook('git \\\nreset --hard')
        self.assertIn('run the git command directly', result.stderr.decode('utf-8'))
        # #77: shell text inside shell text is parsed as shell, so a safe command in it passes.
        self.assertVerdict(["sh -lc 'git status'", 'echo $(git status --short)', 'eval "git log -1"'], 0)

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


class ReviewRoundThreeTests(GuardCase):
    """Opus review round 3: the base floor (a destructive pattern anywhere in the text, on a dirty
    tree) runs first, and the caller's folder is always checked."""

    def test_a_script_the_current_shell_sources_is_refused(self):
        self.dirty()
        self.assertVerdict([
            "cat <<'EOF' > x.sh\ngit reset --hard\nEOF\n. ./x.sh", "cat <<'EOF' > x.sh\ngit reset --hard\nEOF\nsource x.sh",
            "cat <<'EOF' | source /dev/stdin\ngit reset --hard\nEOF",
        ], 2)

    def test_a_shell_with_a_file_operand_is_covered_by_the_floor(self):
        self.dirty()
        self.assertVerdict(['echo "git reset --hard" > x.sh; sh x.sh', "printf 'git reset --hard' > x.sh; bash x.sh",
                            'echo "git stash drop" > x.sh; sh x.sh',
                            # the floor's accepted cost: a mention is refused while the tree is dirty
                            'git commit -m "undo git reset --hard"'], 2)

    def test_the_floor_reads_restore_and_clean_as_git_does(self):
        # Lead on c3f8427: --staged with --worktree overwrites the working copy, and an -n that
        # -e/--exclude consumes is a pattern, not a dry run.
        (self.repo / 'notes.txt').write_text('only copy\n', encoding='utf-8')
        self.dirty()
        self.assertVerdict([
            'echo "git restore --staged --worktree ." > x.sh; sh x.sh', 'echo "git restore -S -W ." > x.sh; sh x.sh',
            'echo "git restore -SW ." > x.sh; sh x.sh', 'echo "git clean -e -n -f" > x.sh; sh x.sh',
            'echo "git clean --exclude -n -f" > x.sh; sh x.sh', 'echo "git clean -fen" > x.sh; sh x.sh',
        ], 2)
        self.assertVerdict(['echo "git restore --staged f.txt" > x.sh; sh x.sh', 'echo "git clean -nd" > x.sh; sh x.sh',
                            'echo "git clean -e x -n -f" > x.sh; sh x.sh'], 0)

    def test_a_conditional_or_background_cd_never_hides_the_caller(self):
        side = self.tmp / 'b'
        side.mkdir()
        git(side, 'init', '-q', '-b', 'main')
        self.dirty()
        self.assertVerdict(['true || cd ../b && git reset --hard', 'cd ../b & git reset --hard',
                            'false && cd ../b; git -C . checkout -- f.txt'], 2)

    def test_everyday_commands_still_pass_on_a_dirty_tree(self):
        self.dirty()
        self.assertVerdict(['git status', 'git diff', 'git log --oneline -n 3', 'git clean -n', 'git clean -nd',
                            'git restore --staged f.txt', 'git add . && git status',
                            "git add . && git commit -F - <<'EOF'\nmention git in a message\nEOF"], 0)


class CloseReviewTests(GuardCase):
    def test_project_gate_can_be_wired(self):
        self.assertVerdict([
            'git config core.hooksPath .githooks',
            'git config --local core.hooksPath .githooks',
            'git config set core.hooksPath .githooks',
            'git config --local --replace-all core.hooksPath .githooks',
        ], 0)
        self.assertVerdict([
            "git config core.hooksPath ''", 'git config core.hooksPath /dev/null',
            'git config --unset core.hooksPath', 'git config unset core.hooksPath',
            'git config --unset core.hooksPath .githooks',
            'git config core.hooksPath other/.githooks',
            'git -c core.hooksPath=.githooks commit -m x',
        ], 2)

    def test_redirections_are_not_git_arguments(self):
        self.dirty()
        self.assertVerdict([
            'git checkout main 2>&1', 'git checkout main >/dev/null',
            'git checkout main 2> errors.log', 'git checkout main >>out 2>&1',
            '2>/dev/null git checkout main', 'git checkout 2>/dev/null main',
            'git checkout main &>/dev/null', 'git checkout main < input.txt',
            'git checkout main >|out', 'git checkout main 2>"errors log"',
            'git config core.hooksPath 2>/dev/null',
            'git config core.hooksPath >&2', 'git config core.hooksPath 2>&-',
        ], 0)
        self.assertVerdict([
            'git commit 2>/dev/null --no-verify -m x',
            'git stash 2>&1 drop', 'git checkout -- f.txt >/dev/null',
            'git checkout main 2 >/dev/null', 'git checkout main "2">/dev/null',
        ], 2)

    def test_quoted_redirect_characters_remain_arguments(self):
        self.dirty()
        self.assertVerdict([
            "git checkout '>'", 'git checkout "2>&1"', r'git checkout \>',
            "git config core.hooksPath '>/dev/null'",
        ], 2)
        self.assertVerdict(["git commit -m '2>&1'", 'git commit -m ">"'], 0)

    def test_wrapper_value_tokens_cannot_hide_git(self):
        for command in [
            'env -u FOO git commit --no-verify -m x',
            'env -u A -u B git push --mirror', 'env -C . git stash drop',
            "env -S 'git push --mirror'", 'env --unset FOO git push --delete origin x',
            'exec -a NAME git push --force',
            'command env -u FOO git remote add up x',
            'env -u git git commit --no-verify -m x',
            'env -Cgit git push --mirror', 'exec -a git git push --mirror',
        ]:
            with self.subTest(command=command):
                result = self.run_hook(command)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'cannot read', result.stderr)

    def test_unlisted_wrappers_cannot_hide_git(self):
        self.assertVerdict([
            'ionice -c3 git push --mirror', 'flock L git stash drop',
            'chrt -i 0 git commit --no-verify -m x', 'chronic git remote add up x',
        ], 2)
        self.assertVerdict([
            'env FOO=bar git status', 'command git status', 'nohup git status',
            'echo git status', 'printf "%s" "git push --mirror"',
            'env -- git status',
        ], 0)

    def test_checkout_previous_branch_is_safe_with_edits(self):
        git(self.repo, 'checkout', '-q', '-b', 'other')
        git(self.repo, 'checkout', '-q', 'main')
        self.dirty()
        self.assertVerdict(['git checkout -', 'git checkout @{-1}', 'git checkout @{-2}'], 0)
        self.assertVerdict(['git checkout -f -', 'git checkout -- -', 'git checkout - f.txt'], 2)

    def test_interpreter_heredocs_holding_git_are_unreadable(self):
        for interpreter in ['python', 'python3', 'python3.13', 'node', 'perl', 'ruby']:
            with self.subTest(interpreter=interpreter):
                command = f"{interpreter} - <<'EOF'\nsubprocess.run(['git', 'push', '--mirror'])\nEOF"
                result = self.run_hook(command)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'force push', result.stderr)  # #77: judged as the git command it holds
        self.assertVerdict([
            "python -I - <<'EOF'\nsubprocess.run(['git', 'push', '--mirror'])\nEOF",
            "env FOO=bar python3 - <<'EOF'\nsubprocess.run(['git', 'stash', 'drop'])\nEOF",
        ], 2)
        self.assertVerdict([
            "python -I - <<'EOF'\nprint('hello')\nEOF",
            "cat <<'EOF' > notes.md\ngit push --mirror is refused\nEOF",
        ], 0)

    def test_interpreter_inline_and_piped_git_are_unreadable(self):
        self.assertVerdict([
            "python -c \"subprocess.run(['git', 'push', '--mirror'])\"",
            "python3 -Ic \"subprocess.run(['git', 'stash', 'drop'])\"",
            "node -e \"spawnSync('git', ['push', '--mirror'])\"",
            "perl -e \"system('git push --mirror')\"",
            "ruby -e \"system('git push --mirror')\"",
            "echo \"subprocess.run(['git', 'push', '--mirror'])\" | python -I -",
            "printf \"system('git push --mirror')\" | ruby",
        ], 2)
        self.assertVerdict(["python -c \"print('hello')\"", "node -e \"console.log('hello')\""], 0)


class RoundOneFixTests(GuardCase):
    def test_hookspath_writes_have_exactly_one_value(self):
        self.assertVerdict([
            'git config core.hooksPath .githooks',
            'git config --local core.hooksPath .githooks',
            'git config set core.hooksPath .githooks',
            'git config --local --replace-all core.hooksPath .githooks',
            'git config --worktree core.hooksPath .githooks',
            'git config set --local core.hooksPath .githooks',
            'git config --get core.hooksPath', 'git config get --local core.hooksPath',
            'git config --global --get core.hooksPath', 'git config --system --get core.hooksPath',
        ], 0)
        self.assertVerdict([
            'git config core.hooksPath set .githooks',
            'git config --local core.hooksPath set .githooks',
            'git config --replace-all core.hooksPath set .githooks',
            'git config core.hooksPath .githooks set',
            'git config set core.hooksPath .githooks extra',
            'git config core.hooksPath get', 'git config core.hooksPath list',
            'git config --unknown core.hooksPath .githooks',
            'git config set --value=set core.hooksPath .githooks',
            'git config --global core.hooksPath .githooks',
        ], 2)
        # Demonstrate Git's actual legacy value/value-pattern grammar in a disposable repo.
        git(self.repo, 'config', 'core.hooksPath', '.githooks')
        git(self.repo, 'config', 'core.hooksPath', 'set', '.githooks')
        self.assertEqual(git(self.repo, 'config', '--get', 'core.hooksPath').stdout.strip(), 'set')

    def link_hooks(self, target):
        link = self.repo / '.githooks'
        if os.name == 'nt':
            result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                                    capture_output=True, encoding='utf-8', errors='replace', timeout=60)
            if result.returncode:
                self.skipTest(f'Windows junction unavailable: {result.stdout} {result.stderr}')
            self.addCleanup(os.rmdir, link)  # Remove the junction itself, never its target.
        else:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f'Directory symlink unavailable: {exc}')
            self.addCleanup(link.unlink)
        self.assertEqual(link.resolve(), target.resolve())

    def test_external_hookspath_junction_is_refused(self):
        outside = self.tmp / 'outside-hooks'
        outside.mkdir()
        self.link_hooks(outside)
        self.assertVerdict([
            'git config core.hooksPath .githooks',
            'git config --local core.hooksPath .githooks',
            'git config set core.hooksPath .githooks',
            'git config --local --replace-all core.hooksPath .githooks',
            'git -C . config core.hooksPath .githooks',
        ], 2)

    def test_internal_hookspath_junction_is_allowed(self):
        inside = self.repo / 'project-hooks'
        inside.mkdir()
        self.link_hooks(inside)
        self.assertVerdict(['git config core.hooksPath .githooks'], 0)

    def test_unrelated_git_does_not_taint_interpreter_inline_text(self):
        self.assertVerdict([
            'git status && python -c "print(\'hello\')"',
            'python -c "print(\'hello\')"; git status',
            'git status && node -e "console.log(\'hello\')"',
            'git status && perl -e "print q(hello)"',
            'git status && ruby -e "puts \'hello\'"',
            'git status && python -W ignore -c "print(\'hello\')"',
            'git status && node --eval="console.log(\'hello\')"',
            'python -c "print(\'hello\')" git',  # #77: a bare git word names no command
        ], 0)
        self.assertVerdict([
            'git status && python -c "subprocess.run([\'git\', \'push\', \'--mirror\'])"',
            'python -c "print(\'hello\')"; ruby -e "system(\'git push --mirror\')"',
            'python -Ic"subprocess.run([\'git\', \'push\', \'--mirror\'])"',
            'node --eval="spawnSync(\'git\', [\'push\', \'--mirror\'])"',
            'perl -e "print q(hello)" -e "system(\'git push --mirror\')"',
        ], 2)

    def test_unrelated_git_does_not_taint_interpreter_heredoc(self):
        self.assertVerdict([
            "git status && python -I - <<'EOF'\nprint('hello')\nEOF",
            "python -I - <<'EOF'\nprint('hello')\nEOF\ngit status",
            "cat <<'EOF' > notes.md\ngit push --mirror is refused\nEOF\npython -c \"print('hello')\"",
            "cat <<'EOF'; python -I -\ngit push --mirror is refused\nEOF",
            "git commit -m \"$(cat <<'EOF'\nmention git push --mirror\nEOF\n)\"",
        ], 0)
        self.assertVerdict([
            "git status && python -I - <<'EOF'\nsubprocess.run(['git', 'push', '--mirror'])\nEOF",
            "cat <<'EOF' | python -I -\nsubprocess.run(['git', 'push', '--mirror'])\nEOF",
            "echo \"$(python -I - <<'EOF'\nsubprocess.run(['git', 'push', '--mirror'])\nEOF\n)\"",
        ], 2)

    def test_only_interpreter_stdin_pipeline_is_inspected(self):
        self.assertVerdict([
            "git status && printf hello | python -I -",
            "printf hello | python -I -; git status",
            "echo git | cat; printf hello | python -I -",
            "git status && python -I -",
            'echo git | git log --grep python',
        ], 0)
        self.assertVerdict([
            'echo "subprocess.run([\'git\', \'push\', \'--mirror\'])" | python -I -',
            'printf "system(\'git push --mirror\')" | cat | ruby',
            'git status && echo "system(\'git push --mirror\')" | ruby',
            'printf "system(\'git push --mirror\')" | env -u FOO ruby',
        ], 2)


class RoundTwoFixTests(GuardCase):
    link_hooks = RoundOneFixTests.link_hooks

    def test_all_interpreter_arguments_are_opaque_regardless_of_flags(self):
        commands = [
            "node -p \"require('child_process').execSync('git config core.hooksPath disabled')\"",
            "node --print \"require('child_process').execSync('git config core.hooksPath disabled')\"",
            "perl -E \"system('git','config','core.hooksPath','disabled')\"",
            "ruby -e \"system('git config core.hooksPath disabled')\"",
            'pwsh -Command "git config core.hooksPath disabled"',
            'powershell -Command "git config core.hooksPath disabled"',
        ]
        for executable in ['deno', 'bun', 'php', 'osascript', 'lua', 'julia', 'Rscript', 'tclsh', 'awk', 'php8.3']:
            commands.append(f'{executable} --some-future-option "git config core.hooksPath disabled"')
        for command in commands:
            with self.subTest(command=command):
                result = self.run_hook(command)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'core.hooksPath', result.stderr)
        self.assertVerdict(['python script.py git', 'python3 -X git -c "print(1)"'], 0)  # #77: no command named

    def test_interpreter_heredocs_and_pipes_are_flag_independent(self):
        for executable in ['python', 'node', 'deno', 'bun', 'perl', 'ruby', 'php', 'pwsh', 'powershell', 'osascript']:
            self.assertVerdict([
                f"{executable} --future-option <<'EOF'\ngit config core.hooksPath disabled\nEOF",
                f'printf "git config core.hooksPath disabled" | {executable} --future-option script.arg',
            ], 2)

    def test_unrelated_git_segments_still_allow_git_free_interpreters(self):
        for executable in ['python', 'node', 'deno', 'bun', 'perl', 'ruby', 'php', 'pwsh', 'powershell', 'osascript']:
            self.assertVerdict([
                f'git status && {executable} --some-option "print(1)"',
                f"git status; {executable} <<'EOF'\nprint(1)\nEOF",
                f'git status && printf hello | {executable} --some-option script.arg',
            ], 0)

    def prepare_gate(self):
        active = self.repo / '.active-hooks'
        active.mkdir(exist_ok=True)
        hook = active / 'pre-commit'
        hook.write_text('#!/bin/sh\necho guard-test-gate-rejected >&2\nexit 1\n', encoding='utf-8', newline='\n')
        hook.chmod(0o755)
        git(self.repo, 'config', 'core.hooksPath', '.active-hooks')

    def commit_status(self):
        result = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                                 'commit', '--allow-empty', '-qm', 'gate probe'], cwd=self.repo, env=ENV,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=60)
        self.commit_error = result.stderr
        return result.returncode

    def assert_gate_preserved(self, command, argv):
        self.prepare_gate()
        before = self.commit_status()
        self.assertEqual(before, 1, 'Fixture gate must reject a real commit before the hook call')
        self.assertIn('guard-test-gate-rejected', self.commit_error)
        verdict = self.run_hook(command)
        if verdict.returncode == 0:  # Execute only what the old guard actually lets through.
            subprocess.run(argv, cwd=self.repo, env=ENV, capture_output=True, check=True, timeout=60)
        after = self.commit_status()
        if after == 1:
            self.assertIn('guard-test-gate-rejected', self.commit_error)
        print(f'{command}: gate_before={before}, guard={verdict.returncode}, commit_after={after}', flush=True)
        self.assertEqual((before, verdict.returncode, after), (1, 2, 1), verdict.stderr)

    def test_real_node_print_cannot_disable_commit_gate(self):
        executable = shutil.which('node')
        if not executable:
            self.skipTest('Node unavailable for executable gate proof; payload variants covered separately')
        code = "require('child_process').execFileSync('git', ['config', 'core.hooksPath', 'disabled'])"
        for flag in ['-p', '--print']:
            with self.subTest(flag=flag):
                self.assert_gate_preserved(f'node {flag} "{code}"', [executable, flag, code])

    def test_real_perl_extended_eval_cannot_disable_commit_gate(self):
        executable = shutil.which('perl')
        if not executable:
            self.skipTest('Perl unavailable for executable gate proof; payload variant covered separately')
        code = "system('git','config','core.hooksPath','disabled') == 0 or die 'git failed'"
        self.assert_gate_preserved(f'perl -E "{code}"', [executable, '-E', code])

    def test_real_subshell_cannot_redirect_hookspath_containment(self):
        outside = self.tmp / 'outside-hooks'
        outside.mkdir()
        self.link_hooks(outside)
        side = self.tmp / 'b'
        side.mkdir()
        git(side, 'init', '-q', '-b', 'main')
        shell = shutil.which('sh')
        if not shell:
            self.skipTest('POSIX shell unavailable for executable subshell proof')
        command = '(cd ../b && git status --short); git config core.hooksPath .githooks'
        self.assert_gate_preserved(command, [shell, '-c', command])

    def test_hookspath_writes_with_directory_routing_are_judged_in_every_folder(self):
        # #77: doctor prints `cd <repo> && git config core.hooksPath .githooks`; with .githooks
        # inside every folder the command may stand in, a routed write wires the project's gate.
        self.assertVerdict(['popd; git config core.hooksPath .githooks'], 2)  # a folder it cannot name
        self.assertVerdict([
            '(cd . && git status); git config core.hooksPath .githooks',
            'cd . && git config core.hooksPath .githooks',
            'pushd .; git config core.hooksPath .githooks',
            '(git config core.hooksPath .githooks)',
            'git -C . config core.hooksPath .githooks',
            'git -C. config core.hooksPath .githooks',
            'git --git-dir=.git config core.hooksPath .githooks',
            'git --git-dir .git config core.hooksPath .githooks',
            'git --work-tree=. config core.hooksPath .githooks',
            'git --work-tree . config core.hooksPath .githooks',
            'GIT_DIR=.git git config core.hooksPath .githooks',
            'GIT_WORK_TREE=. git config core.hooksPath .githooks',
            'git config core.hooksPath .githooks; cd .',
            'git status && git config core.hooksPath .githooks',
            'git config core.hooksPath .githooks',
            'git config --local --replace-all core.hooksPath .githooks',
            'git config set core.hooksPath .githooks',
            'cd . && git config --get core.hooksPath',
        ], 0)
        outside = self.tmp / 'outside-hooks'
        outside.mkdir()
        self.link_hooks(outside)
        self.assertVerdict(['cd . && git config core.hooksPath .githooks',
                            'GIT_DIR=.git git config core.hooksPath .githooks'], 2)


class V012GuardTests(GuardCase):
    """v0.12: every shell tool (#93, #213), ref and object loss (#127), a dirty worktree's
    force remove (#108), and git that appears only in data or code (#77)."""

    def tool(self, tool, commands, code):
        for command in commands:
            with self.subTest(tool=tool, command=command):
                payload = json.dumps({'tool_name': tool, 'tool_input': {'command': command}})
                result = self.run_hook(command, payload=payload)
                self.assertEqual(result.returncode, code, result.stderr.decode('utf-8', 'replace'))

    def test_powershell_and_monitor_commands_are_judged(self):
        self.tool('PowerShell', ['git commit --no-verify -m x', '$env:HUSKY = "0"; git commit -m x',
                                 'git --% commit --no-verify -m x', 'git commit -m x `\n  --no-verify'], 2)
        self.tool('Monitor', ['until false; do sleep 1; done; git commit --no-verify -m x'], 2)
        self.tool('PowerShell', ['git status; git log --oneline -3', 'Set-Location sub\\dir; git status',
                                 '& git diff --stat'], 0)
        self.tool('Monitor', ['tail -f build.log | grep --line-buffered error'], 0)
        self.dirty()
        self.tool('PowerShell', ['git reset --hard', 'Set-Location .; git checkout -- f.txt'], 2)
        self.tool('Monitor', ['sleep 5; git reset --hard'], 2)

    def test_ref_and_object_loss_is_refused(self):
        git(self.repo, 'branch', 'merged')
        git(self.repo, 'checkout', '-q', '-b', 'feat')
        git(self.repo, 'commit', '-q', '--allow-empty', '-m', 'only on feat')
        git(self.repo, 'checkout', '-q', 'main')
        main = git(self.repo, 'rev-parse', 'HEAD').stdout.strip()
        lone = git(self.repo, 'commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'only on t1').stdout.strip()
        git(self.repo, 'tag', 't1', lone)
        git(self.repo, 'tag', 't2')
        self.assertVerdict([
            'git branch -D feat', 'git branch -d -f feat', 'git branch --delete --force feat',
            'git branch -f feat main', 'git branch -M merged feat', 'git update-ref -d refs/heads/feat',
            'git update-ref refs/heads/feat ' + main, 'git update-ref --stdin', 'git tag -d t1',
            'git tag -f -m moved t1 main', 'git reflog expire --expire=now --all',
            'git reflog delete HEAD@{0}', 'git gc --prune=now', 'git prune',
        ], 2)
        self.assertVerdict([
            'git branch -D merged', 'git branch -d feat', 'git branch -f merged main', 'git tag -d t2',
            'git update-ref -d refs/heads/merged ' + main, 'git branch -D no-such-branch',
            'git gc', 'git gc --prune=never', 'git prune -n', 'git branch -m merged renamed',
        ], 0)

    def test_index_commands_that_overwrite_are_dirty_sensitive(self):
        commands = ['git rm -f f.txt', 'git rm -r -f .', 'git mv -f f.txt g.txt', 'git checkout-index -f -a',
                    'git read-tree -u --reset HEAD']
        self.assertVerdict(commands, 0)
        self.dirty()
        self.assertVerdict(commands, 2)
        self.assertVerdict(['git rm --cached f.txt', 'git rm -f --cached f.txt'], 0)

    def test_force_removing_a_worktree_that_holds_work_is_refused(self):
        git(self.repo, 'worktree', 'add', '-q', '-b', 'wtb', str(self.tmp / 'wt'))
        git(self.repo, 'worktree', 'add', '-q', '-b', 'wtc', str(self.tmp / 'clean'))
        self.assertVerdict(['git worktree remove --force ../wt', 'git worktree remove -f -f ../clean'], 0)
        (self.tmp / 'wt' / 'f.txt').write_text('worker output\n', encoding='utf-8')
        self.assertVerdict(['git worktree remove --force ../wt', 'git worktree remove -f -f ../wt',
                            'git -C .. worktree remove --force wt', 'cd .. && git worktree remove --force wt'], 2)
        (self.tmp / 'wt' / 'f.txt').write_text('one\n', encoding='utf-8')
        (self.tmp / 'wt' / 'new.txt').write_text('untracked\n', encoding='utf-8')
        self.assertVerdict(['git worktree remove --force ../wt'], 2)
        self.assertVerdict(['git worktree remove ../wt', 'git worktree list'], 0)  # git refuses itself

    def test_git_in_data_or_code_is_judged_as_the_command_it_names(self):
        (self.repo / 'note.md').write_text('x\n', encoding='utf-8')
        self.assertVerdict([
            "python - <<'EOF'\nopen('note.txt', 'w').write('see the git docs')\nEOF",
            "python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['git', 'status'])\nEOF",
            'gh issue create --title "the git hook refuses a title" --body-file note.md',
            'grep -c x $(git ls-files)', 'left=$(git ls-files --others --exclude-standard | wc -l)',
            'for f in $(git ls-files); do wc -l "$f"; done', 'cd . && git config core.hooksPath .githooks',
            'timeout 30 git fetch', 'xargs -n1 git log -1 --oneline',
        ], 0)
        self.assertVerdict([
            "python - <<'EOF'\nsubprocess.run(['git', 'push', '--force'])\nEOF",
            'gh issue create --title t --body "$(git push --force)"', 'sudo git push --force',
            'nice git commit --no-verify -m x', 'gh api x -f note="git stash drop"',
        ], 2)

    def test_project_review_refusals_of_read_only_git_now_pass(self):
        # #77: the leeway review's real refusals of 2026-10-18 — a read-only git log inside a
        # here-document, and an issue body that names git commands in prose.
        self.assertVerdict([
            "python - <<'EOF'\nimport subprocess\nsubprocess.run(['git','log','--oneline','-5'])\nEOF",
            "cat <<'EOF'\nrun git log --oneline -5 to see the base\nEOF",
            'gh issue create --title "guard refuses read-only git" --body "the hook refused `git log`'
            ' inside a heredoc; git status and git diff were refused too"',
        ], 0)


class V012RoundOneReviewTests(GuardCase):
    """v0.12 guards, round-1 reviews of d991909: the guard fails closed on what it cannot read."""

    def side_repo(self, dirty):
        side = self.tmp / 'b'
        side.mkdir()
        git(side, 'init', '-q', '-b', 'main')
        (side / 'w.txt').write_text('one\n', encoding='utf-8')
        git(side, 'add', 'w.txt')
        git(side, 'commit', '-q', '-m', 'base')
        if dirty:
            (side / 'w.txt').write_text('owner edit\n', encoding='utf-8')
        return side

    def lone_commit(self, message):
        return git(self.repo, 'commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', message).stdout.strip()

    def test_operands_and_folders_it_cannot_know_are_refused(self):
        self.assertVerdict(['cd "$OTHER" && git branch -D feat'], 2)  # no feat here; $OTHER may hold one
        git(self.repo, 'branch', 'merged')
        git(self.repo, 'update-ref', 'refs/heads/feat', self.lone_commit('only on feat'))
        self.side_repo(dirty=True)
        self.assertVerdict([
            'git branch --no-merged | xargs git branch -D', 'git branch | grep -v main | xargs git branch -D',
            'git branch --no-merged | xargs -I{} git branch -D {}', 'git branch --no-merged | xargs -I % git branch -D %',
            'for b in $(git branch --no-merged); do git branch -D "$b"; done', 'git branch -D $(git branch --no-merged)',
            'git $sub feat', 'git stash "$action"', 'ls -d ../b/ | xargs -I{} git -C {} reset --hard',
        ], 2)
        self.assertVerdict(['git branch -D merged', 'xargs -n1 git log -1 --oneline', 'git log -1 "$rev"',
                            'git push -u origin "$(git branch --show-current)"'], 0)

    def test_an_argv_list_laid_out_one_item_per_line_is_read(self):
        argv = "python - <<'EOF'\nimport subprocess\nsubprocess.run([\n    \"git\",\n    {},\n    {},\n])\nEOF"
        self.assertVerdict([argv.format('"push"', '"--force"'), argv.format('"branch"', '"-D",\n    name'),
                            "node -e \"spawn('git', ['push',\n '--force'])\""], 2)
        self.assertVerdict([argv.format('"log"', '"--oneline"'), argv.format('"status"', '"--short"')], 0)

    def test_a_branch_checked_out_somewhere_is_not_reached_by_its_own_head(self):
        git(self.repo, 'checkout', '-q', '-b', 'feat')
        git(self.repo, 'commit', '-q', '--allow-empty', '-m', 'only on feat')
        self.assertVerdict(['git switch main && git branch -D feat'], 2)
        git(self.repo, 'checkout', '-q', 'main')
        git(self.repo, 'commit', '-q', '--allow-empty', '-m', 'only on main')
        self.assertVerdict(['git update-ref refs/heads/main HEAD~1', 'git update-ref HEAD HEAD~1'], 2)
        git(self.repo, 'worktree', 'add', '-q', '-b', 'wtb', str(self.tmp / 'wt'))
        git(self.tmp / 'wt', 'commit', '-q', '--allow-empty', '-m', 'only on wtb')
        self.assertVerdict(['git worktree remove ../wt && git branch -D wtb'], 2)
        git(self.repo, 'branch', 'same')
        self.assertVerdict(['git branch -D same', 'git update-ref refs/heads/main HEAD'], 0)

    def test_remote_tracking_ref_loss_is_refused(self):
        git(self.repo, 'remote', 'add', 'origin', str(self.tmp / 'nowhere.git'))
        git(self.repo, 'remote', 'add', 'up', str(self.tmp / 'nowhere.git'))
        git(self.repo, 'update-ref', 'refs/remotes/origin/x', self.lone_commit('only on origin/x'))
        git(self.repo, 'update-ref', 'refs/remotes/up/main', 'HEAD')
        self.assertVerdict(['git remote remove origin', 'git remote rm origin', 'git branch -r -D origin/x',
                            'git branch --remotes -D origin/x', 'git -C nowhere remote remove up',
                            'git remote remove "$name"'], 2)
        self.assertVerdict(['git remote remove up', 'git branch -r -D up/main', 'git remote -v'], 0)

    def test_a_powershell_backslash_path_is_a_path(self):
        side = self.side_repo(dirty=False)
        command = 'git -C ..\\b reset --hard'
        payload = json.dumps({'tool_name': 'PowerShell', 'tool_input': {'command': command}})
        self.assertEqual(self.run_hook(command, payload=payload).returncode, 0)  # ..\b is clean
        (side / 'w.txt').write_text('owner edit\n', encoding='utf-8')
        self.assertEqual(self.run_hook(command, payload=payload).returncode, 2)

    def test_a_comment_ends_at_its_line(self):
        self.assertVerdict(['git status  # look first\ngit stash drop', 'curl -s https://example.com/page#top; git push --force',
                            'echo a#b; git push --force'], 2)
        self.assertVerdict(["git status  # don't worry", 'git log --oneline -3 # the last ones\ngit status'], 0)

    def test_nested_shell_text_is_judged_where_the_line_has_moved(self):
        self.side_repo(dirty=True)  # the caller's tree is clean
        self.assertVerdict([
            'cd ../b && out="$(git reset --hard)"', "cd ../b && bash <<'EOF'\ngit checkout -- .\nEOF",
            'cd ../b && echo "$(git checkout -- .)"', 'GIT_DIR=../b/.git GIT_WORK_TREE=../b timeout 60 git reset --hard',
            'export GIT_DIR=../b/.git GIT_WORK_TREE=../b; timeout 60 git reset --hard',
        ], 2)
        self.assertVerdict(['timeout 60 git reset --hard', 'echo "$(git reset --hard)"'], 0)

    def test_abbreviations_and_config_that_prune_now_are_read(self):
        git(self.repo, 'update-ref', 'refs/heads/feat', self.lone_commit('only on feat'))
        git(self.repo, 'tag', 't1', self.lone_commit('only on t1'))
        self.assertVerdict(['git tag --del t1', 'git branch --delete --forc feat', 'git branch --de -f feat',
                            'git -c gc.pruneExpire=now gc', 'git -c gc.reflogExpireUnreachable=now gc'], 2)
        self.assertVerdict(['git -c gc.pruneExpire=never gc', 'git branch --list', 'git tag --list'], 0)

    def test_shell_run_by_git_or_from_input_is_judged(self):
        git(self.repo, 'update-ref', 'refs/heads/feat', self.lone_commit('only on feat'))
        self.assertVerdict(["git -c alias.x='!git push --force' x", "git -c alias.x='!git branch -D' x feat",
                            "echo 'git push --force' | bash -s x", "git submodule foreach 'git clean -fdx'",
                            'git submodule foreach --recursive git reset --hard'], 2)
        self.assertVerdict(["git -c alias.st='!git status' st", 'git submodule foreach git status'], 0)


class V012RoundTwoReviewTests(GuardCase):
    """v0.12 guards, round-2 reviews of 8b3ecaf: folders, splats and operands it cannot read."""
    side_repo = V012RoundOneReviewTests.side_repo
    lone_commit = V012RoundOneReviewTests.lone_commit

    def test_a_folder_changed_inside_nested_shell_or_code_is_judged(self):
        self.side_repo(dirty=True)  # the caller's tree is clean
        self.assertVerdict([
            "timeout 60 sh -c 'cd ../b && git reset --hard'",
            "ls -d ../*/ | xargs -I{} sh -c 'cd {} && git checkout -- .'",
            "python -c \"import subprocess; subprocess.run(['git', 'reset', '--hard'], cwd='../b')\"",
            "python -c \"import os; os.chdir('../b'); os.system('git checkout -- .')\"",
        ], 2)
        self.assertVerdict(["timeout 60 sh -c 'git reset --hard'", "timeout 60 sh -c 'cd ../b && git status'",
                            "python -c \"import subprocess; subprocess.run(['git', 'status'], cwd='../b')\""], 0)

    def test_a_powershell_splat_is_unknowable(self):
        def tool(name, commands, code):
            for command in commands:
                with self.subTest(tool=name, command=command):
                    payload = json.dumps({'tool_name': name, 'tool_input': {'command': command}})
                    self.assertEqual(self.run_hook(command, payload=payload).returncode, code)
        tool('PowerShell', ["$a = @('push','--force'); git @a", "$a = 'push', '--force'; git @a", 'git @args',
                            'git push @a'], 2)
        tool('PowerShell', ["git log -1 '@{u}'", 'git log --oneline -3'], 0)
        tool('Bash', ['git log --oneline -1 @'], 0)  # in Bash `@` is HEAD

    def test_an_interpolated_operand_in_code_is_unknown(self):
        git(self.repo, 'branch', 'merged')
        git(self.repo, 'update-ref', 'refs/heads/feat', self.lone_commit('only on feat'))
        self.assertVerdict([
            "python -c 'import subprocess; subprocess.run(f\"git branch -D {b}\", shell=True)'",
            "ruby -e 'system(\"git branch -D #{b}\")'",
            "python -c 'import os; os.system(\"git branch -D %s\" % b)'",
            "python -c 'import os; os.system(\"git branch -D {0}\".format(b))'",
        ], 2)
        self.assertVerdict(["python -c 'import os; os.system(\"git branch -D merged\")'",
                            "python -c 'import subprocess; subprocess.run(f\"git log -1 {rev}\", shell=True)'",
                            "python -c 'import os; os.system(\"git rev-parse HEAD^{tree}\")'"], 0)


if __name__ == '__main__':
    unittest.main()

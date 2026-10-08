"""The running-work hook must put every call that ends running work to the owner, and only those."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'overlays/claude-code/files'
HOOK = OVERLAY / '.claude/hooks/guard_running_work.py'


def run(payload):
    result = subprocess.run([sys.executable, str(HOOK)], input=payload, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'] if result.stdout else None


def call(tool, command=None):
    return run(json.dumps({'tool_name': tool, 'tool_input': {} if command is None else {'command': command}}))


class RunningWorkHookTests(unittest.TestCase):
    def test_ending_running_work_is_asked(self):
        for tool, command in (('Bash', 'taskkill /PID 8884 /T /F'), ('Bash', 'MSYS_NO_PATHCONV=1 taskkill /PID 1 /F'),
                              ('PowerShell', 'Stop-Process -Id 25588,37860'), ('PowerShell', 'stop-process -name claude'),
                              ('Bash', 'kill -9 4242'), ('Bash', 'pkill -f check.sh'), ('Bash', 'killall codex'),
                              ('Bash', 'tmux kill-session -t =w1'), ('Bash', 'sh scripts/close_worker.sh w1; taskkill /PID 5 /F'), ('PowerShell', '(Get-Process codex).Kill()'),
                              ('TaskStop', None)):
            with self.subTest(command=command or tool):
                self.assertEqual(call(tool, command), 'ask')

    def test_other_calls_and_the_audited_close_pass(self):
        for tool, command in (('Bash', 'git status'), ('Bash', 'echo skill'), ('Bash', 'grep -n killer notes.md'),
                              ('Bash', 'sh scripts/close_worker.sh w1'), ('Edit', None), ('Read', None)):
            with self.subTest(command=command or tool):
                self.assertIsNone(call(tool, command))

    def test_the_overlay_registers_it_for_bash_powershell_and_taskstop(self):
        settings = json.loads((OVERLAY / '.claude/settings.json').read_text())
        entries = [e for e in settings['hooks']['PreToolUse']
                   if any('guard_running_work.py' in h['command'] for h in e['hooks'])]
        self.assertEqual([e['matcher'] for e in entries], ['Bash|PowerShell|TaskStop'])

    def test_unreadable_input_never_blocks(self):
        self.assertIsNone(run('not json'))


if __name__ == '__main__':
    unittest.main()

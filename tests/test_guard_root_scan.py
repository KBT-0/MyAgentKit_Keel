"""guard_root_scan.py: a search or walk from a filesystem or drive root is refused before it starts (#298)."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_root_scan.py'

REFUSED = [
    ('Bash', 'find / -name nothing.h'),
    ('Bash', 'find C:/ -name x.h'),
    ('Bash', 'find /c/ -name x.h 2>/dev/null | head'),
    ('Bash', 'find /c -iname "*.h"'),
    ('Bash', 'find -L / -name x'),
    ('Bash', 'find / -maxdepth 9 -name x'),
    ('Bash', 'find /mnt/c -name x'),
    ('Bash', 'cd / && find . -name x'),
    ('Bash', 'cd / && find -name x'),
    ('Bash', 'grep -r foo /'),
    ('Bash', 'grep -rn --include=*.h foo /c/'),
    ('Bash', 'grep -R -e foo /'),
    ('Bash', 'rg foo /'),
    ('Bash', 'rg -i foo C:/'),
    ('Bash', 'ag foo /'),
    ('Bash', 'fd x.h /'),
    ('Bash', 'ls -R /'),
    ('Bash', 'ls -laR /c'),
    ('Bash', 'du -sh /'),
    ('Bash', 'du -sh /*'),
    ('Bash', 'du -d 1 /'),
    ('Bash', 'tree /'),
    ('Bash', 'sudo find / -name x'),
    ('Bash', 'timeout 60 find / -name x'),
    ('Bash', 'X=1 find / -name x'),
    ('Bash', 'echo start; find / -name x &'),
    ('Bash', 'files=$(find / -name x)'),
    ('Bash', 'bash -c "find / -name x"'),
    ('Monitor', 'find / -name x'),
    ('PowerShell', r'Get-ChildItem -Path C:\ -Recurse -Filter x.h'),
    ('PowerShell', r'gci C:\ -r -Include *.h'),
    ('PowerShell', 'ls -Recurse C:\\'),
    ('PowerShell', r'dir \ -Rec'),
    ('PowerShell', r'Get-ChildItem C:\ -Recurse -Depth 8'),
    ('PowerShell', r'where.exe /r C:\ cl.exe'),
    ('PowerShell', r'Set-Location C:\; Get-ChildItem . -Recurse'),
    ('Bash', 'powershell.exe -NoProfile -Command "Get-ChildItem C:\\ -Recurse"'),
]
ALLOWED = [
    ('Bash', 'find . -name x.h'),
    ('Bash', 'find src -name x.h'),
    ('Bash', 'find / -maxdepth 2 -name x.h'),
    ('Bash', 'find /c/Users/me/project -name x'),
    ('Bash', 'find /usr/include -name x.h'),
    ('Bash', 'find . -name "/"'),
    ('Bash', 'rg foo src/'),
    ('Bash', 'rg / src/'),
    ('Bash', 'rg --max-depth 2 foo /'),
    ('Bash', 'grep -r "/" src'),
    ('Bash', 'grep foo /etc/hosts'),
    ('Bash', 'grep -e / -r src'),
    ('Bash', 'ls /'),
    ('Bash', 'ls -la /c/'),
    ('Bash', 'du -sh .'),
    ('Bash', 'du -sh /tmp/build'),
    ('Bash', 'tree -L 2 /'),
    ('Bash', 'tree src'),
    ('Bash', 'cd / && ls'),
    ('Bash', 'cd /tmp && find . -name x'),
    ('Bash', 'echo "find / -name x"'),
    ('Bash', 'git log --oneline -- a/b'),
    ('Bash', 'sed -n 1,5p /etc/hosts'),
    ('Bash', 'python3 -c "print(1)"'),
    ('PowerShell', 'Get-ChildItem C:\\'),
    ('PowerShell', r'Get-ChildItem -Path C:\ -Recurse -Depth 2'),
    ('PowerShell', r'Get-ChildItem D:\work\project -Recurse'),
    ('PowerShell', r'gci . -r'),
    ('PowerShell', r'Get-ChildItem /c -Recurse'),
    ('PowerShell', r'Get-Content C:\notes.txt'),
]
TOOLS_REFUSED = [
    ('Glob', {'pattern': '**/*.h', 'path': '/'}),
    ('Glob', {'pattern': '**/*.h', 'path': 'C:\\'}),
    ('Glob', {'pattern': '/**/x.h'}),
    ('Glob', {'pattern': 'C:/**/x.h'}),
    ('Grep', {'pattern': 'foo', 'path': '/'}),
    ('Grep', {'pattern': 'foo', 'path': 'C:/'}),
    ('Grep', {'pattern': 'foo', 'path': '/c/'}),
]
TOOLS_ALLOWED = [
    ('Glob', {'pattern': '**/*.h'}),
    ('Glob', {'pattern': 'src/**/*.h', 'path': 'D:/work/project'}),
    ('Glob', {'pattern': '/usr/include/**/*.h'}),
    ('Grep', {'pattern': '/', 'path': 'src'}),
    ('Grep', {'pattern': 'foo'}),
    ('Read', {'file_path': '/'}),
]


def run(tool, tool_input):
    payload = json.dumps({'tool_name': tool, 'tool_input': tool_input}).encode('utf-8')
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, timeout=60)


class GuardRootScanTests(unittest.TestCase):
    def check(self, cases, code):
        for tool, tool_input in cases:
            tool_input = {'command': tool_input} if isinstance(tool_input, str) else tool_input
            with self.subTest(tool=tool, tool_input=tool_input):
                result = run(tool, tool_input)
                err = result.stderr.decode('utf-8', 'replace')
                self.assertEqual(result.returncode, code, err)
                if code == 2:
                    self.assertIn('BLOCKED', err)
                    self.assertIn('-maxdepth', err)  # says what to do instead
                    self.assertIn('inside the project', err)

    def test_a_walk_from_a_root_is_refused(self):
        self.check(REFUSED, 2)

    def test_a_bounded_walk_or_one_inside_a_folder_passes(self):
        self.check(ALLOWED, 0)

    def test_a_glob_or_grep_call_from_a_root_is_refused(self):
        self.check(TOOLS_REFUSED, 2)

    def test_a_glob_or_grep_call_inside_a_folder_passes(self):
        self.check(TOOLS_ALLOWED, 0)

    def test_unreadable_input_is_refused(self):
        result = subprocess.run([sys.executable, str(HOOK)], input=b'{not json', capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn('could not read the hook input', result.stderr.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main()

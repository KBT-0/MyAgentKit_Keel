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
    # orph round 1. A `#` comment ends at its line; inside a word it is no comment.
    ('Bash', '# look for the header\nfind / -name x.h'),
    ('Bash', 'curl http://h/#a; find / -name x'),
    ('Bash', 'n=${#files[@]}; find / -name x'),
    ('Bash', "cat > n.md <<'EOF'\nfind / is data\nEOF\nfind / -name x"),  # the walk after the heredoc
    ('Bash', 'cat <<< "x"\nfind / -name x'),
    # rg's -S, -o, -x and ag's or ack's -r are switches; rg --files takes no pattern.
    ('Bash', 'rg -S foo /'),
    ('Bash', 'rg -o foo C:/'),
    ('Bash', 'rg -x foo /'),
    ('Bash', 'rg --files /'),
    ('Bash', 'ag -r foo /'),
    ('Bash', 'ag -S foo /'),
    ('Bash', 'ack -r foo /'),
    ('PowerShell', r'Get-ChildItem C:\ -Depth 50'),
    ('PowerShell', r'dir C:\ -s'),
    ('PowerShell', r'& { gci C:\ -r }'),
    ('Bash', 'bash -lc "find / -name x"'),
    ('Bash', 'sh -ec "find / -name x"'),
    ('Bash', 'nice -n 19 find / -name x'),
    ('Bash', 'env -i find /'),
    ('Bash', 'sudo -u x find / -name y'),
    ('Bash', 'find -O3 / -name x'),
    ('Bash', 'find -D tree / -name x'),
    # After a cd to a root, a walk with no path walks it; popd goes back.
    ('Bash', 'cd / && rg foo'),
    ('Bash', 'cd / && grep -r foo'),
    ('Bash', 'cd / && du -sh'),
    ('Bash', 'cd / && ls -R'),
    ('Bash', 'cd / && tree'),
    ('PowerShell', r'Set-Location C:\; gci -r'),
    ('PowerShell', r'Set-Location C:\; Get-ChildItem -Recurse -Filter x.h'),
    ('Bash', 'pushd /; pushd /tmp; popd; rg foo'),
    ('Bash', 'cmd //c "dir C:\\x.h /s"'),
    ('PowerShell', r'cmd /c "dir C:\ /s"'),
    ('PowerShell', r'cmd /c dir \*.h /s/b'),
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
    # orph round 1. An escape is the shell's: `\(` is find's paren, `\` + newline joins the lines.
    ('Bash', 'find . \\( -name a -o -name b \\) -print'),
    ('Bash', 'grep -rn "foo" \\\n  src/'),
    ('Bash', "rg foo src/ \\\n  -g '*.py'"),
    ('Bash', 'grep -r foo src \\'),
    # A heredoc's body is data.
    ('Bash', "cat > notes.md <<'EOF'\nfind / -name x.h ran for seven hours\nEOF"),
    ('Bash', "git commit -F - <<-EOF\n\tfind / -name x is refused\n\tEOF\necho done"),
    ('Bash', 'echo a # find / -name x'),
    # Depth 0 is a bound.
    ('Bash', 'find / -maxdepth 0'),
    ('Bash', 'rg --max-depth 0 foo /'),
    ('PowerShell', r'Get-ChildItem C:\ -Recurse -Depth 0'),
    ('PowerShell', r'Get-ChildItem C:\work -Depth 50'),
    ('Bash', 'pushd /; popd; find .'),
    ('Bash', 'cd / && rg foo src'),
    ('PowerShell', r'cmd /c "dir C:\work /s"'),
    ('PowerShell', r'cmd /c "dir C:\ /b"'),
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

    def test_unreadable_input_lets_the_call_through(self):
        # The guard fails open (lead decision D1): a stalled or broken guard must not refuse every call.
        result = subprocess.run([sys.executable, str(HOOK)], input=b'{not json', capture_output=True, timeout=60)
        err = result.stderr.decode('utf-8', 'replace')
        self.assertEqual(result.returncode, 1, err)
        self.assertIn('could not read the hook input', err)
        self.assertIn('the call goes on', err)


if __name__ == '__main__':
    unittest.main()

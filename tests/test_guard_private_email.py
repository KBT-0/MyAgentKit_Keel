"""guard_private_email.py: the owner's e-mail address never leaves in a web request."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_private_email.py'
ENV = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k != 'MYAGENTKIT_PRIVATE_EMAILS'}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')


class GuardPrivateEmailTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, True)
        subprocess.run(['git', 'init', '-q', str(self.repo)], env=ENV, check=True, timeout=60)
        subprocess.run(['git', 'config', 'user.email', 'Owner@Example.com'], cwd=self.repo, env=ENV, check=True, timeout=60)

    def run_hook(self, tool, tool_input, env=None, payload=None):
        payload = payload if payload is not None else json.dumps({'tool_name': tool, 'tool_input': tool_input})
        return subprocess.run([sys.executable, str(HOOK)], input=payload.encode('utf-8'), cwd=self.repo,
                              env=env or ENV, capture_output=True, timeout=60)

    def assertCode(self, cases, code, env=None):
        for tool, tool_input in cases:
            with self.subTest(tool=tool, tool_input=tool_input):
                result = self.run_hook(tool, tool_input, env)
                self.assertEqual(result.returncode, code, result.stderr.decode('utf-8', 'replace'))
                if code == 2:
                    self.assertNotIn('owner@example.com', result.stderr.decode('utf-8').lower())

    def test_a_web_request_carrying_the_address_is_refused(self):
        self.assertCode([
            ('WebFetch', {'url': 'https://api.example.org/?contact=owner@example.com', 'prompt': 'x'}),
            ('WebFetch', {'url': 'https://api.example.org/?contact=OWNER%40example.com', 'prompt': 'x'}),
            ('WebSearch', {'query': 'owner@example.com'}),
            ('Bash', {'command': 'curl -A "bot (owner@example.com)" https://api.example.org'}),
            ('Bash', {'command': 'gh issue create --body "mail owner@example.com"'}),
        ], 2)

    def test_other_calls_pass(self):
        self.assertCode([
            ('WebFetch', {'url': 'https://api.example.org/', 'prompt': 'x'}),
            ('Bash', {'command': 'curl -A "kit-bot (https://example.org/project)" https://api.example.org'}),
            ('Bash', {'command': 'git log --author=owner@example.com'}),
            ('Read', {'file_path': 'owner@example.com'}),
        ], 0)

    def test_an_address_named_in_the_environment_is_refused_too(self):
        # The Claude account's address can differ from git's user.email.
        env = dict(ENV, MYAGENTKIT_PRIVATE_EMAILS='acct@example.org, other@example.net')
        self.assertCode([('WebFetch', {'url': 'https://x.example/?m=other@example.net', 'prompt': 'x'})], 2, env)

    def test_an_unreadable_payload_blocks(self):
        self.assertEqual(self.run_hook(None, None, payload='not json').returncode, 2)


if __name__ == '__main__':
    unittest.main()

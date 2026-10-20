"""guard_secret_files.py: an agent's Edit, Write or NotebookEdit of a secret-looking file is refused (#297)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'overlays/claude-code/files/.claude/hooks/guard_secret_files.py'
sys.path.insert(0, str(ROOT / 'core/scripts'))
import claude_bridge  # noqa: E402

# Every rule of the predicate on both sides of its edge: the names where the hook and the review agree.
NAMES = ['.env', '.env.local', '.ENV.production', '.env.example', '.env.sample', '.env.template', '.envrc',
         '.dev.vars', '.dev.vars.staging', 'credentials', 'credentials.json', 'Credentials.yml',
         'server.key', 'cert.PEM', 'id_rsa.pub', 'keys.txt', 'a.key.bak', '.npmrc', '.netrc', 'npmrc',
         'src/app.py', 'config/server.key', 'docs/.env.example', 'env', 'my.env', 'README.md', 'server.key.sample']
# The documented differences: the hook is narrower than the review, which refuses these unless
# --allow-secret-file. A guard must not stall ordinary work: a source file named after credentials
# and a template with any secret-looking stem pass the hook.
HOOK_ALLOWS = ['credentials.py', 'CredentialsForm.tsx', 'credentials_test.go', '.env.local.example', '.env.dist',
               '.dev.vars.template', 'credentials.bak']


def run(tool, call):
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps({'tool_name': tool, 'tool_input': call}),
                          capture_output=True, encoding='utf-8', errors='replace', timeout=60)


class GuardSecretFilesTests(unittest.TestCase):
    def test_a_secret_name_is_refused_and_any_other_passes(self):
        for tool, call in (('Write', {'file_path': '.dev.vars', 'content': 'TOKEN=x'}),
                           ('Edit', {'file_path': 'config/server.key', 'old_string': 'a', 'new_string': 'b'}),
                           ('Write', {'file_path': r'C:\work\app\.env.local', 'content': 'x'}),
                           ('NotebookEdit', {'notebook_path': '/w/credentials', 'new_source': 'x'}),
                           ('Write', {'file_path': 'credentials.json', 'content': 'x'}),
                           ('Write', {'file_path': '/home/o/.aws/credentials', 'content': 'x'}),
                           ('Write', {'file_path': '.env.local', 'content': 'x'})):
            with self.subTest(refused=call):
                result = run(tool, call)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('BLOCKED', result.stderr)
                self.assertIn('the owner edits it from the terminal', result.stderr)
        for tool, call in (('Write', {'file_path': '.env.example', 'content': 'TOKEN='}),
                           ('Edit', {'file_path': 'src/app.py', 'old_string': 'a', 'new_string': 'b'}),
                           ('NotebookEdit', {'notebook_path': 'notes/key.ipynb', 'new_source': 'x'}),
                           ('Edit', {'file_path': 'src/credentials.py', 'old_string': 'a', 'new_string': 'b'}),
                           ('Write', {'file_path': 'ui/CredentialsForm.tsx', 'content': 'x'}),
                           ('Write', {'file_path': 'auth/credentials_test.go', 'content': 'x'}),
                           ('Write', {'file_path': '.env.local.example', 'content': 'TOKEN='}),
                           ('Write', {'file_path': r'C:\app\.env.dist', 'content': 'TOKEN='})):
            with self.subTest(allowed=call):
                result = run(tool, call)
                self.assertEqual((result.returncode, result.stderr), (0, ''))

    def test_unreadable_input_passes_with_a_note(self):
        # Fails open (lead decision D1, as guard_root_scan): a guard that cannot read its input must
        # not refuse every edit.
        for payload in ('not json', json.dumps({'tool_input': {'file_path': 7}})):
            with self.subTest(payload=payload):
                result = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                                        encoding='utf-8', errors='replace', timeout=60)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('could not read the hook input', result.stderr)

    def test_the_hook_and_the_review_agree_but_on_the_named_differences(self):
        # The hook copies claude_bridge.secret_like rather than importing it (the hooks use the
        # stdlib alone); this table keeps the two copies one but for HOOK_ALLOWS.
        spec = importlib.util.spec_from_file_location('guard_secret_files', HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        for name in NAMES:
            with self.subTest(name=name):
                self.assertEqual(hook.secret_like(name), claude_bridge.secret_like(name))
        for name in HOOK_ALLOWS:
            with self.subTest(hook_allows=name):
                self.assertEqual((hook.secret_like(name), claude_bridge.secret_like(name)), (False, True))
        for name in ('credentials.toml', 'credentials.ini', 'credentials.env', 'credentials-prod', '.aws/credentials'):
            with self.subTest(refused=name):
                self.assertTrue(hook.secret_like(name))
        self.assertTrue(hook.secret_like(r'C:\app\config\server.key'))


if __name__ == '__main__':
    unittest.main()

"""Follow the documented companion list into an existing project, using fake CLIs."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReviewUpgradeTests(unittest.TestCase):
    def test_documented_upgrade_supplies_runtime_and_test_imports(self):
        # Extract the actual docs, so an incomplete upgrade list cannot pass this test.
        docs = (ROOT / 'core/docs/DEV_SETUP.md').read_text()
        block = docs.split('<!-- REVIEW_COMPANIONS_START -->')[1].split('<!-- REVIEW_COMPANIONS_END -->')[0]
        companions = re.findall(r'`([a-z_]+\.py)`', block)
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / 'scripts'
            scripts.mkdir()
            for name in companions:
                shutil.copyfile(ROOT / 'core/scripts' / name, scripts / name)
            # Import the dispatcher and every suite used by the installed self-test.
            probe = ('import review_dispatch, test_claude_bridge, test_agent_usage, test_codex_quota; '
                     'print("UPGRADE IMPORTS: PASS")')
            result = subprocess.run([sys.executable, '-B', '-c', probe], cwd=scripts,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('UPGRADE IMPORTS: PASS', result.stdout)
            # An existing project upgrades its wrapper as well as its companion files.
            project = Path(tmp)
            (scripts / 'review.sh').write_text('# Previous project-owned wrapper.\nexit 2\n')
            shutil.copyfile(ROOT / 'core/scripts/review.sh', scripts / 'review.sh')
            (project / '.gitignore').write_bytes((ROOT / 'core/.gitignore').read_bytes())
            for name in ('AGENTS.md', 'docs/ARCHITECTURE.md', 'docs/REVIEW_GATE.md'):
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('Synthetic project guidance.\n')
            (project / 'file.py').write_text('original\n')
            for args in (['init', '-q'], ['add', '.'],
                         ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                          '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                          'commit', '-qm', 'Synthetic existing project']):
                subprocess.run(['git', '-C', str(project), *args], check=True, capture_output=True)
            (project / 'file.py').write_text('changed\n')
            fake = project / 'fake-codex'
            fake.write_text('#!/usr/bin/env python3\nimport json,pathlib,sys\n'
                            'sys.stdin.read()\n'
                            'pathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_text("VERDICT: Accept\\n")\n'
                            'print(json.dumps({"type":"turn.completed","usage":{}}))\n')
            fake.chmod(0o755)
            env = dict(os.environ, REVIEW_CLI_BIN=str(fake),
                       CLAUDE_CLI_BIN=str(project / 'NO-PAID-CLI'),
                       REVIEW_REPO_ROOT=str(project), REVIEW_CODEX_MODEL='fixture-codex-model',
                       REVIEW_CLAUDE_MODEL='', MYAGENTKIT_CAPTURE_QUOTA='0',
                       MYAGENTKIT_DELEGATION_DEPTH='0', REVIEW_TIMEOUT_SECONDS='30',
                       REVIEW_DOCS='AGENTS.md, docs/ARCHITECTURE.md and docs/REVIEW_GATE.md')
            result = subprocess.run(['sh', str(scripts / 'review.sh'), '--reviewer', 'codex'],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('VERDICT: Accept', result.stdout)
            # Removing the dispatcher recreates the old instructions' concrete failure.
            (scripts / 'review_dispatch.py').unlink()
            result = subprocess.run([sys.executable, '-B', '-c', probe], cwd=scripts,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('review_dispatch', result.stderr)

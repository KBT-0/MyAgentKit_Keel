"""Quota reads are optional, bounded, non-billing, and never a per-call debit estimate."""
import json
from pathlib import Path
import tempfile
import unittest
import codex_quota

SERVER = '''#!/usr/bin/env python3
import json, pathlib, sys, time
for line in sys.stdin:
    message = json.loads(line)
    method = message['method']
    assert method in ('initialize', 'initialized', 'account/rateLimits/read')
    if method == 'initialize':
        print(json.dumps({'id': 1, 'result': {}}), flush=True)
    if method == 'account/rateLimits/read':
        case = pathlib.Path('case').read_text()
        if case == 'timeout': time.sleep(20)
        if case == 'error': print(json.dumps({'id': 2, 'error': {'message': 'unavailable'}}), flush=True)
        else:
            print(json.dumps({'id': 2, 'result': {'email': 'private@example.invalid',
                'accessToken': 'private-token', 'rateLimitsByLimitId': {'codex': {
                    'planType': 'pro', 'primary': {'usedPercent': 25, 'windowDurationMins': 300,
                                                 'resetsAt': 1800000000}, 'secondary': None}}}}), flush=True)
'''


class QuotaTests(unittest.TestCase):
    def test_reads_only_quota_methods_and_sanitizes_account_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cli = repo / 'codex'
            cli.write_text(SERVER)
            cli.chmod(0o755)
            (repo / 'case').write_text('success')
            result = codex_quota.snapshot(str(cli), repo, timeout=2)
            self.assertEqual(result['status'], 'available')
            self.assertEqual(result['buckets']['codex']['primary']['used_percent'], 25)
            self.assertNotIn('private', json.dumps(result))

    def test_unavailable_and_unresponsive_quota_reads_return_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cli = repo / 'codex'
            cli.write_text(SERVER)
            cli.chmod(0o755)
            for case in ('error', 'timeout'):
                (repo / 'case').write_text(case)
                result = codex_quota.snapshot(str(cli), repo, timeout=0.3)
                self.assertEqual(result['status'], 'unavailable')
                self.assertEqual(result['buckets'], {})

    def test_invalid_percent_is_not_zero(self):
        for percent in (-1, 101, True, float('nan'), '25'):
            buckets = codex_quota.sanitize({'rateLimits': {'primary': {'usedPercent': percent}}})
            self.assertIsNone(buckets['codex']['primary'])


if __name__ == '__main__':
    unittest.main()

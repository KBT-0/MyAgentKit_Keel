"""The kit's SessionStart warns the lead once when the last AI-sector scan is older than seven
days (PLAN item 10B, owner 2026-11-10): the inline check in .claude/settings.json reads
`Son tarama: YYYY-MM-DD` from docs/research/ai-watch.md, is silent when fresh, says so when the
line or the file is missing, stays quiet for workers and never fails the session."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LINE = '(docs/research/ai-watch.md); paralelde aiwatch araştırma işçisini başlat\n'


def stale_command():
    settings = json.loads((ROOT / '.claude/settings.json').read_text(encoding='utf-8'))
    found = [h['command'] for entry in settings['hooks']['SessionStart'] if entry.get('matcher') == 'startup'
             for h in entry['hooks'] if 'ai-watch.md' in h['command']]
    if len(found) != 1:
        raise AssertionError('one startup SessionStart command reading ai-watch.md, found %d' % len(found))
    return found[0]


@unittest.skipUnless(shutil.which('sh'), 'the hook runs under sh')
class AiWatchStaleTests(unittest.TestCase):
    def setUp(self):
        self.command = stale_command()
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / 'kit'
        (self.project / 'docs/research').mkdir(parents=True)
        # A fixed "today": a date on PATH that answers +%F, so the case does not depend on the clock.
        self.bin = Path(tmp.name) / 'bin'
        self.bin.mkdir()
        fake = self.bin / 'date'
        fake.write_text('#!/bin/sh\necho "$FAKE_TODAY"\n', encoding='utf-8', newline='\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    def run_hook(self, today='2026-11-10', doc=None, role=''):
        if doc is not None:
            (self.project / 'docs/research/ai-watch.md').write_text(doc, encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if k != 'MYAGENTKIT_ROLE'}
        env.update(CLAUDE_PROJECT_DIR=str(self.project), FAKE_TODAY=today,
                   PATH=str(self.bin) + os.pathsep + env.get('PATH', ''))
        if role:
            env['MYAGENTKIT_ROLE'] = role
        result = subprocess.run(['sh', '-c', self.command], capture_output=True, text=True, encoding='utf-8',
                                env=env, timeout=30)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        return result.stdout

    def test_fresh_up_to_seven_days_is_silent(self):
        for last in ('2026-11-10', '2026-11-03'):
            with self.subTest(last=last):
                self.assertEqual(self.run_hook(doc='# x\n\nSon tarama: %s\n' % last), '')

    def test_older_than_seven_days_prints_one_line_with_the_days(self):
        self.assertEqual(self.run_hook(doc='Son tarama: 2026-11-02\n'), 'ai-watch: son tarama 8 gün önce ' + LINE)
        # Across a year end and a leap day: 2028-02-27 .. 2028-03-06 is 8 days.
        self.assertEqual(self.run_hook(today='2028-03-06', doc='Son tarama: 2028-02-27\n'),
                         'ai-watch: son tarama 8 gün önce ' + LINE)
        self.assertEqual(self.run_hook(today='2027-01-02', doc='Son tarama: 2026-12-20\n'),
                         'ai-watch: son tarama 13 gün önce ' + LINE)

    def test_a_missing_line_or_file_says_there_was_no_scan(self):
        self.assertEqual(self.run_hook(), 'ai-watch: son tarama yok ' + LINE)
        self.assertEqual(self.run_hook(doc='# ai-watch\n\nSon tarama: soon\n'), 'ai-watch: son tarama yok ' + LINE)

    def test_a_worker_session_gets_nothing(self):
        self.assertEqual(self.run_hook(doc='Son tarama: 2020-01-01\n', role='worker'), '')


if __name__ == '__main__':
    unittest.main()

"""Usage accounting and bounded-process regressions with no paid CLI calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import agent_process
import agent_usage


class UsageTests(unittest.TestCase):
    def test_private_staging_and_publication_require_ignore_rules(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            ignore = repo / '.gitignore'
            ignore.write_text('/.myagentkit/\n/docs/reviews/*-review.md\n')
            report = repo / 'docs/reviews/fixture-review.md'
            original = tempfile.NamedTemporaryFile

            def capture(*args, **kwargs):
                stream = original(*args, **kwargs)
                result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--quiet',
                                         stream.name])
                self.assertEqual(result.returncode, 0, 'temporary raw evidence must also be ignored')
                return stream

            with patch.object(agent_usage.tempfile, 'NamedTemporaryFile', side_effect=capture):
                agent_usage.write_evidence(repo, report, 'private output', private=True)
            ignore.write_text('')
            with self.assertRaisesRegex(ValueError, 'Git-ignored'):
                agent_usage.write_evidence(repo, report.with_name('new-review.md'), 'private', private=True)
            self.assertFalse(report.with_name('new-review.md').exists())

    def test_private_storage_cannot_follow_an_in_repo_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / '.gitignore').write_text('/.myagentkit/\n')
            (repo / 'public').mkdir()
            (repo / '.myagentkit').mkdir()
            (repo / '.myagentkit/usage').symlink_to(repo / 'public', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinked storage'):
                agent_usage.require_private_storage(repo)

    def test_evidence_cannot_overwrite_or_escape_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'
            repo.mkdir()
            report = repo / 'docs/reviews/report.json'
            agent_usage.write_evidence(repo, report, 'first evidence')
            with self.assertRaises(FileExistsError):
                agent_usage.write_evidence(repo, report, 'replacement')
            self.assertEqual(report.read_text(), 'first evidence')
            (repo / 'outside').symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'inside the repository'):
                agent_usage.write_evidence(repo, repo / 'outside/leak.json', 'private')
            self.assertFalse((Path(tmp) / 'leak.json').exists())

    def test_excess_output_is_stopped_without_disk_capture(self):
        from unittest.mock import patch
        original = tempfile.TemporaryFile
        with patch.object(agent_process.tempfile, 'TemporaryFile', wraps=original) as temp_file:
            for fd in (1, 2):
                child = 'import os;\nwhile True: os.write(' + str(fd) + ', b"x" * 65536)'
                result = agent_process.run([sys.executable, '-c', child], '', Path.cwd(), 2)
                self.assertEqual(result['termination'], 'output_limit')
                self.assertLessEqual(len(result['stdout']), 8_000_000)
                self.assertLessEqual(len(result['stderr']), 8_000_000)
            self.assertEqual(temp_file.call_count, 2, 'Only stdin may use a temporary file')

    def test_large_prompt_reaches_a_slow_starting_child_without_deadlock(self):
        child = "import sys,time; time.sleep(0.3); print(len(sys.stdin.read()))"
        result = agent_process.run([sys.executable, "-c", child], "x" * 200000, Path.cwd(), 2)
        self.assertIsNone(result["termination"], result)
        self.assertEqual(result["stdout"].strip(), "200000")

    def test_unknown_usage_is_not_zero_or_a_subscription_estimate(self):
        value = agent_usage.normalize("codex", [], False)
        for key in ["input_tokens", "output_tokens", "api_cost_usd_reported",
                    "subscription_percent_consumed", "credits_used_reported"]:
            self.assertIsNone(value[key])
        for value in [-1, float("inf"), float("nan"), True, "12"]:
            self.assertIsNone(agent_usage.number(value))

    def test_codex_cache_and_reasoning_are_not_added_to_input_and_output(self):
        values = [{"type": "turn.completed", "usage": {"input_tokens": 100,
                   "cached_input_tokens": 90, "output_tokens": 20, "reasoning_output_tokens": 10}}]
        normalized = agent_usage.normalize("codex", values, True)
        self.assertEqual(normalized["input_tokens"], 100)
        self.assertEqual(normalized["output_tokens"], 20)
        self.assertEqual(normalized["reasoning_tokens"], 10)
        self.assertTrue(normalized["input_includes_cache"])

    def test_failure_classification_does_not_read_review_prose(self):
        execution = {"exit_code": 0, "termination": None}
        good = [{"type": "result", "subtype": "success", "is_error": False,
                 "result": "Review found a bug in quota handling and HTTP 429 tests"}]
        self.assertIsNone(agent_usage.failure("claude", execution, good))
        for message, expected in [("context window exceeded", "context_limit"),
                                  ("authentication failed", "authentication"),
                                  ("rate limit exceeded", "quota")]:
            self.assertEqual(agent_usage.failure("codex", execution,
                [{"type": "turn.failed", "error": {"message": message}}]), expected)

    def test_records_are_unique_and_report_filters_without_exposing_raw_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            execution = {"exit_code": 1, "stdout": "private transcript", "stderr": "", "duration_ms": 2}
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / '.gitignore').write_text('/.myagentkit/\n')
            one, _ = agent_usage.record(repo, "codex", "fixture", "claude/fixture", {"id": "one"},
                                       execution, "failed", "quota", None)
            two, _ = agent_usage.record(repo, "codex", "fixture", "claude/fixture", {"id": "two"},
                                       execution, "failed", "quota", None)
            self.assertNotEqual(one, two)
            result = subprocess.run([sys.executable, str(Path(agent_usage.__file__)), "--repo", tmp,
                                     "--task-id", "one", "--json"], capture_output=True, text=True, check=True)
            rows = json.loads(result.stdout)
            self.assertEqual(len(rows), 1)
            self.assertNotIn("private transcript", result.stdout)

    def test_unavailable_child_is_a_returned_failure_not_an_exception(self):
        result = agent_process.run(["/nonexistent-myagentkit-cli"], "", Path.cwd(), 1)
        self.assertEqual(result["termination"], "unavailable")

    def test_usage_path_cannot_follow_a_symlink_outside_the_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, outside = root / "repo", root / "outside"
            repo.mkdir()
            outside.mkdir()
            (repo / ".myagentkit").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "inside the repository"):
                agent_usage.record(repo, "codex", "fixture", "claude/fixture", {},
                                   {"stdout": "", "exit_code": 1}, "failed", "quota", None)
            self.assertFalse((outside / "usage").exists())

    def test_timeout_stops_the_process_group_and_keeps_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            descendant = "import time,pathlib; time.sleep(2); pathlib.Path('escaped').write_text('bad')"
            parent = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," +
                      repr(descendant) + "]); print('partial',flush=True); time.sleep(10)")
            result = agent_process.run([sys.executable, "-c", parent], "", repo, 1)
            self.assertEqual(result["termination"], "timeout")
            self.assertIn("partial", result["stdout"])
            time.sleep(1.2)
            self.assertFalse((repo / "escaped").exists())


if __name__ == "__main__":
    unittest.main()

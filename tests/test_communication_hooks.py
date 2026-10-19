"""The two communication hooks: bounce a bare label once, nudge after five silent calls, never block a turn."""
import itertools
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks'


IDS = itertools.count()


def run(hook, payload, **env):
    # Claude Code sends UTF-8 whatever the host's code page; MYAGENTKIT_ROLE is the worker marker.
    env = {**{k: v for k, v in os.environ.items() if k != 'MYAGENTKIT_ROLE'}, **env}
    return subprocess.run([sys.executable, str(HOOKS / hook)], input=payload, text=True, encoding='utf-8',
                          capture_output=True, timeout=30, env=env)


def assistant(*blocks):
    return {'type': 'assistant', 'uuid': 'u%d' % next(IDS), 'message': {'content': list(blocks)}}


def tool(name='Read'):
    return {'type': 'tool_use', 'name': name, 'input': {}}


def text(s='Found it.'):
    return {'type': 'text', 'text': s}


class PlainReportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        (self.project / 'docs').mkdir()
        (self.project / 'docs/STATE.md').write_text('r2: second review round\nK4: task\nL1b: task\nK7-a: task\n',
                                                  encoding='utf-8')

    def test_task_ids_and_unregistered_rounds(self):
        for label in ('K4', 'L1b', 'K7-a'):
            self.assertEqual(self.stop(label + ' finished.').returncode, 2, label)
        (self.project / 'docs/STATE.md').write_text('K4: active\n', encoding='utf-8')
        self.assertEqual(self.stop('The r2 value is ordinary prose.').returncode, 0)
        (self.project / 'docs/BACKLOG.md').write_text('r2: pending\n', encoding='utf-8')
        self.assertEqual(self.stop('r2 finished.').returncode, 2)
        self.assertEqual(self.stop('r20 finished.').returncode, 0)

    def test_fences_close_only_with_the_same_character_and_length(self):
        for message in ('````\n```\nK4 D-5\n````', '```\n~~~\nK4 D-5\n```',
                        '~~~~\n~~~\nK4 D-5\n~~~~~'):
            self.assertEqual(self.stop(message).returncode, 0, message)
            self.assertEqual(self.stop(message + '\nK4 finished.').returncode, 2, message)
        # A backtick fence's info string has no backtick: this line is an inline span, not a fence.
        self.assertEqual(self.stop('```sh``` is the tag.\nK4 finished.').returncode, 2)

    def test_project_task_positions_register_every_canonical_prefix(self):
        entries = ('{id}: active', '- {id}: active', '### {id} — active',
                   '- [ ] **{id}**: active', '| `{id}` | active |')
        for name in ('STATE.md', 'BACKLOG.md'):
            for label in ('AB12', 'abc12', 'ABC-12', 'abc1234', 'UTF8'):
                for entry in entries:
                    with self.subTest(file=name, label=label, entry=entry):
                        (self.project / 'docs' / name).write_text(entry.format(id=label) + '\n', encoding='utf-8')
                        self.assertEqual(self.stop(label + ' finished.').returncode, 2)
            (self.project / 'docs' / name).unlink()

    def test_prose_mentions_never_register_technical_words(self):
        words = ('UTF-8', 'SHA-256', 'win32', 'cp1252', 'x86', 'Python3', 'IPv6', 'GPT-5')
        for name in ('STATE.md', 'BACKLOG.md'):
            (self.project / 'docs' / name).write_text('\n'.join(
                'Verify the %s build on Windows.\n- Verify the %s build.\n| Notes | Verify %s |'
                % (word, word, word) for word in words), encoding='utf-8')
            for word in words:
                with self.subTest(file=name, word=word):
                    self.assertEqual(self.stop('The %s build passes.' % word).returncode, 0)
            (self.project / 'docs' / name).unlink()

    def test_common_technical_words_pass_and_labels_are_still_caught(self):
        for word in ('UTF-8', 'SHA-256', 'win32', 'cp1252', 'x86', 'Python3', 'IPv6', 'GPT-5',
                     'e2e', 'i18n', 'SHA256', 'IPv4', 'x86-64', 'base64', 'Win11', 'v1'):
            with self.subTest(word=word):
                result = self.stop('Decoding is %s now.' % word)
                self.assertEqual((result.returncode, result.stderr), (0, ''), word)
        for label in ('K4', 'L1b', 'K7-a', 'v011-d5', 'D-5'):
            self.assertEqual(self.stop('Decoding is %s now.' % label).returncode, 2, label)

    def test_products_priorities_and_gpu_names_are_not_unregistered_labels(self):
        (self.project / 'docs/STATE.md').write_text('', encoding='utf-8')
        for word in ('S3', 'P0', 'P1', 'Q3', 'M2', 'L2', 'R2', 'A100', 'H100', 'H100s'):
            with self.subTest(word=word):
                self.assertEqual(self.stop('The %s deployment passes.' % word).returncode, 0)
        (self.project / 'docs/STATE.md').write_text('P0: deployment task\n', encoding='utf-8')
        self.assertEqual(self.stop('P0 finished.').returncode, 2)
        self.assertEqual(self.stop('K4 is an unregistered value.').returncode, 0)

    def test_project_owned_patterns_bypass_builtin_task_filters_and_survive_sync(self):
        config = self.project / '.claude/plain_report_labels.json'
        config.parent.mkdir()
        patterns = [r'\bPR-\d+\b', r'\bBUG-\d+\b', r'\bsprint\d+\b', r'\bREADY\b']
        config.write_text(json.dumps(patterns), encoding='utf-8')
        for label in ('PR-12', 'BUG-7', 'sprint3', 'READY'):
            with self.subTest(label=label):
                self.assertEqual(self.stop(label + ' finished.').returncode, 2)
                self.assertEqual(self.stop('The project task (%s) finished.' % label).returncode, 0)
                self.assertEqual(self.stop('Task (%s), again (%s).' % (label, label)).returncode, 2)
        self.assertEqual(self.stop('PR-12 is `READY`.', MYAGENTKIT_ROLE='worker').returncode, 0)
        # No source file at this path: sync cannot overwrite the project-owned configuration.
        self.assertFalse((HOOKS.parents[4] / 'core/.claude/plain_report_labels.json').exists())

    def test_label_inputs_are_read_once_per_message(self):
        spec = importlib.util.spec_from_file_location('plain_report_test', HOOKS / 'plain_report.py')
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        reads = []
        original = Path.read_text
        def read(path, *args, **kwargs):
            reads.append(path)
            return original(path, *args, **kwargs)
        with patch.dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project)), patch.object(Path, 'read_text', read):
            self.assertIn('K4', hook.bare_labels('K4 K4 L1b D-5 (r2) r2 v011-d5'))
        for name in ('STATE.md', 'BACKLOG.md', 'commit-msg'):
            self.assertEqual(sum(path.name == name for path in reads), 1, (name, reads))

    def test_legacy_project_patterns_still_bypass_task_filters(self):
        spec = importlib.util.spec_from_file_location('plain_report_legacy', HOOKS / 'plain_report.py')
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        hook.LABELS += (r'\bPR-\d+\b', r'\bREADY\b')
        with patch.dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project)):
            self.assertEqual(hook.bare_labels('PR-12 READY'), ['PR-12', 'READY'])
            self.assertEqual(hook.bare_labels('The task (PR-12) is ready (READY).'), [])

    def test_invalid_project_patterns_preserve_builtin_and_valid_project_labels(self):
        config = self.project / '.claude/plain_report_labels.json'
        config.parent.mkdir()
        for invalid in ('a{4294967296}', '['):
            with self.subTest(pattern=invalid):
                config.write_text(json.dumps([invalid, r'\bPR-\d+\b']), encoding='utf-8')
                result = self.stop('D-5 K4 Accept-MC finished.')
                self.assertEqual(result.returncode, 2, result.stderr)
                for label in ('D-5', 'K4', 'Accept-MC'):
                    self.assertIn(label, result.stderr)
                self.assertEqual(self.stop('PR-12 finished.').returncode, 2)
                self.assertEqual(self.stop('The S3 deployment passes.').returncode, 0)

    def test_project_pattern_runtime_errors_preserve_checks_and_discard_partial_matches(self):
        spec = importlib.util.spec_from_file_location('plain_report_runtime', HOOKS / 'plain_report.py')
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        config = self.project / '.claude/plain_report_labels.json'
        config.parent.mkdir()
        config.write_text(json.dumps(['bad-pattern', r'\bPR-\d+\b']), encoding='utf-8')
        original = hook.re.finditer
        def finditer(pattern, text, flags=0):
            if pattern != 'bad-pattern':
                return original(pattern, text, flags)
            def broken():
                yield hook.re.match('partial', 'partial')
                raise RuntimeError('project regex iteration failed')
            return broken()
        with patch.dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project)), patch.object(hook.re, 'finditer', finditer):
            self.assertEqual(hook.bare_labels('D-5 K4 Accept-MC PR-12'), ['D-5', 'K4', 'Accept-MC', 'PR-12'])

    def test_installed_hook_reads_the_commit_hooks_canonical_grammar(self):
        hooks = self.project / '.claude/hooks'
        hooks.mkdir(parents=True)
        shutil.copyfile(HOOKS / 'plain_report.py', hooks / 'plain_report.py')
        git_hooks = self.project / '.githooks'
        git_hooks.mkdir()
        source = HOOKS.parents[4] / 'core/.githooks/commit-msg'
        grammar = source.read_text(encoding='utf-8').replace("TASK_ID_PATTERN='[A-Za-z]", "TASK_ID_PATTERN='Z")
        (git_hooks / 'commit-msg').write_text(grammar, encoding='utf-8')
        (self.project / 'docs/STATE.md').write_text('K4: task\nZ4: task\n', encoding='utf-8')
        for label, expected in (('K4', 0), ('Z4', 2)):
            result = run(hooks / 'plain_report.py', json.dumps({'last_assistant_message': label}),
                         CLAUDE_PROJECT_DIR=str(self.project))
            self.assertEqual(result.returncode, expected, result.stderr)

    def stop(self, message, active=False, **env):
        env.setdefault('CLAUDE_PROJECT_DIR', str(self.project))
        return run('plain_report.py', json.dumps({'last_assistant_message': message, 'stop_hook_active': active},
                                                 ensure_ascii=False), **env)

    def test_a_bare_label_is_bounced_with_every_label_named_once(self):
        result = self.stop('D-5 review done, r2 clean, r2 archived: Accept-MC. D-5 next.')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('BLOCKED', result.stderr)
        self.assertIn('D-5, r2, Accept-MC', result.stderr)
        self.assertIn('docs/COMMUNICATION.md', result.stderr)

    def test_labels_inside_code_paths_versions_and_hashes_pass(self):
        for message in ('The archive is `docs/reviews/r2-D-5.md`.',
                        'The archive is docs/reviews/r2-D-5.md, on Windows docs\\reviews\\r2-D-5.md.',
                        'Run:\n```\nREVIEW_LABEL=v011-d5 sh review.sh  # r2\n```\nthen stop.',
                        'Run:\n~~~\nsh review.sh  # r2\n~~~\nthen stop.',
                        'The span ``r2 `D-5` here`` is code.',
                        'An unclosed block:\n```\nD-5 r2',
                        '- step\n  - sub\n    ```\n    git commit -m "Done: K4"\n    ```\n',
                        '- Run:\n    ```\n    REVIEW_LABEL=v011-d5 sh review.sh\n    ```\nthen stop.',
                        '> ```\n> K4\n> ```\nthen stop.',
                        'The second review round (r2) is clean.',
                        'master is at a62e282, v0.11, issue #75; the `Accept-MC` verdict is in the file.',
                        'İkinci inceleme turu temiz; kabul, iki küçük not ile.',
                        ''):
            with self.subTest(message=message):
                result = self.stop(message)
                self.assertEqual((result.returncode, result.stderr), (0, ''), message)

    def test_slash_pairs_and_backticked_registered_ids_are_labels(self):
        # "K4/L1b" was dropped as a path and a backticked registered id passed (#210).
        for message in ('Tasks K4/L1b are merged.', 'The `K4` task is merged.'):
            with self.subTest(message=message):
                self.assertEqual(self.stop(message).returncode, 2, message)

    def test_a_bounce_asks_for_one_line_never_a_resend(self):
        # A Stop hook runs after the owner read the message: a full resend made them read it twice (#209).
        for message in ('K4 finished.', 'Shall I merge it?'):
            with self.subTest(message=message):
                result = self.stop(message)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('do not send it again', result.stderr)
                self.assertNotIn('send the message again', result.stderr)

    def test_a_second_label_in_parentheses_is_bounced(self):
        result = self.stop('The second review round (r2) is clean; the next one follows it (r2).')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(': r2.', result.stderr)

    def test_turkish_and_emoji_are_read_under_any_code_page(self):
        # The ANSI code page decoded stdin before: a Turkish letter or an emoji raised and the
        # silent fallback turned the hook off.
        for page in ('cp1252', 'cp1254'):
            with self.subTest(page=page):
                result = self.stop('Şimdi ❌ D-5 bitti.', PYTHONIOENCODING=page)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('D-5', result.stderr)

    def test_a_question_left_in_chat_text_is_bounced(self):
        # #289: a lead twice ended a report with an open question instead of asking it with the tool.
        for message in ('Tests pass. Shall I push the branch?', 'Bitti.\n\nPush edeyim mi? 🙂',
                        'Done; one question is still open: the release date.',
                        'Rapor hazır. Bir açık soru kaldı: sürüm tarihi.', '**Open question:** the date.'):
            with self.subTest(message=message):
                result = self.stop(message)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('AskUserQuestion', result.stderr)
        # Without the commit-msg grammar the label check is off, the question check is not.
        alone = self.project / 'hooks/plain_report.py'
        alone.parent.mkdir()
        shutil.copy(HOOKS / 'plain_report.py', alone)
        for message, code in (('D-5 is done.', 0), ('Shall I push?', 2)):
            result = subprocess.run([sys.executable, str(alone)], input=json.dumps({'last_assistant_message': message}),
                                    encoding='utf-8', capture_output=True, timeout=30,
                                    env={**os.environ, 'CLAUDE_PROJECT_DIR': str(self.project), 'MYAGENTKIT_ROLE': ''})
            self.assertEqual(result.returncode, code, result.stderr)
        for message in ('Why did it fail? The cache was stale; fixed and tested.', 'No open questions; done.',
                        'Açık soru yok, iş bitti.', 'Testler geçti. Açık sorun yok.', 'Açık sorunlar: #83',
                        'Done.\n\nOpen questions: none.', 'No questions are open.',
                        'All open questions are answered.','Run:\n```\nls -la ?\n```', 'Is `x?` set: yes.'):
            with self.subTest(passes=message):
                result = self.stop(message)
                self.assertEqual((result.returncode, result.stderr), (0, ''), message)
        both = self.stop('D-5 is done. Shall I push?')
        self.assertEqual(both.returncode, 2, both.stderr)
        self.assertIn('AskUserQuestion', both.stderr)
        self.assertIn('D-5', both.stderr)

    def test_a_worker_session_is_not_checked(self):
        result = self.stop('D-5 done, r2 clean.', MYAGENTKIT_ROLE='worker')
        self.assertEqual((result.returncode, result.stderr), (0, ''))

    def test_a_continued_turn_is_not_bounced_again(self):
        result = self.stop('D-5 is still here.', active=True)
        self.assertEqual((result.returncode, result.stderr), (0, ''))

    def test_a_broken_input_never_holds_the_turn(self):
        for payload in ('', 'not json', '{"last_assistant_message": 5}'):
            with self.subTest(payload=payload):
                self.assertEqual(run('plain_report.py', payload).returncode, 0)


class ProgressReminderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.transcript = Path(tmp.name) / 'session.jsonl'

    def nudge(self, records, raw=None, **env):
        self.transcript.write_text(raw if raw is not None else ''.join(json.dumps(r) + '\n' for r in records),
                                   encoding='utf-8')
        result = run('progress_reminder.py', json.dumps({'transcript_path': str(self.transcript)},
                                                        ensure_ascii=False), **env)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        if not result.stdout:
            return None
        return json.loads(result.stdout)['hookSpecificOutput']

    def test_the_fifth_silent_call_nudges_once_and_a_visible_line_resets(self):
        calls = [assistant(tool()) for _ in range(4)]
        self.assertIsNone(self.nudge(calls))
        said = self.nudge(calls + [assistant(tool())])
        self.assertEqual(said['hookEventName'], 'PostToolUse')
        self.assertIn('5 tool calls', said['additionalContext'])
        self.assertIn('docs/COMMUNICATION.md', said['additionalContext'])
        calls += [assistant(tool()), assistant(tool())]  # 6 and 7: already said
        self.assertIsNone(self.nudge(calls))
        calls += [assistant(text(), tool())]  # a visible line: the count restarts
        self.assertIsNone(self.nudge(calls + [assistant(tool()) for _ in range(3)]))
        self.assertIn('5 tool calls', self.nudge(calls + [assistant(tool()) for _ in range(4)])['additionalContext'])

    def test_a_sub_agent_call_leaves_the_leads_nudge_unspent(self):
        # A sub-agent's first call at a delegation took the lead's nudge, quoting the lead's count (#214).
        calls = [assistant(text())] + [assistant(tool()) for _ in range(5)]
        self.transcript.write_text(''.join(json.dumps(r) + '\n' for r in calls), encoding='utf-8')
        result = run('progress_reminder.py', json.dumps({'transcript_path': str(self.transcript), 'agent_id': 'a1'}))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertIn('5 tool calls', self.nudge(calls)['additionalContext'])

    def test_a_worker_session_is_never_nudged(self):
        # #132: a spawned worker's chat has no reader, and the nudge asked it for the narration
        # AGENTS.md forbids.
        # Its own band still reaches it: a 250k request makes the band line, so an empty output fails.
        calls = [assistant(tool()) for _ in range(5)]
        calls[-1]['message']['usage'] = {'input_tokens': 250000}
        said = self.nudge(calls, MYAGENTKIT_ROLE='worker')['additionalContext']
        self.assertIn('Context is 250k tokens', said)
        self.assertNotIn('tool calls since', said)

    def test_three_nudges_per_silence_then_text_and_compaction_rearm(self):
        calls = []
        for count in range(1, 26):
            calls.append(assistant(tool()))
            nudge = self.nudge(calls)
            self.assertEqual(nudge is not None, count in (5, 10, 15), count)
        for reset in (assistant(text()), {'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'reset'}):
            calls += [reset] + [assistant(tool()) for _ in range(5)]
            self.assertIsNotNone(self.nudge(calls))

    def test_a_parallel_batch_that_jumps_over_the_threshold_still_nudges_once(self):
        calls = [assistant(tool()) for _ in range(4)] + [assistant(tool(), tool(), tool())]
        self.assertIn('7 tool calls', self.nudge(calls)['additionalContext'])
        self.assertIsNone(self.nudge(calls + [assistant(tool())]))  # 8
        self.assertIn('10 tool calls', self.nudge(calls + [assistant(tool(), tool(), tool())])['additionalContext'])

    def test_thinking_sidechains_and_empty_text_do_not_count_as_visible(self):
        calls = [assistant({'type': 'thinking', 'thinking': 'hm'}, tool()), assistant(text('  '), tool()),
                 {'type': 'assistant', 'isSidechain': True, 'message': {'content': [text('worker talk')]}},
                 assistant(tool()), assistant(tool())]
        self.assertIsNone(self.nudge(calls))
        self.assertIn('5 tool calls', self.nudge(calls + [assistant(tool())])['additionalContext'])

    def test_the_same_count_seen_again_never_nudges_twice(self):
        # Claude Code writes one record per content block; a parallel batch runs the hook once
        # per call, and a sub-agent's calls may all see the lead's frozen transcript.
        calls = [assistant(text())] + [assistant(tool()) for _ in range(4)] + [assistant(tool()) for _ in range(3)]
        self.assertIn('7 tool calls', self.nudge(calls)['additionalContext'])
        for _ in range(3):
            self.assertIsNone(self.nudge(calls))
        self.assertTrue(self.transcript.with_suffix('.progress-step').exists())

    def test_a_compaction_starts_a_new_count(self):
        calls = [assistant(tool()) for _ in range(4)]
        calls += [{'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'c1'}] + calls
        self.assertIsNone(self.nudge(calls))
        self.assertIn('5 tool calls', self.nudge(calls + [assistant(tool())])['additionalContext'])

    def test_a_broken_state_file_counts_as_none_and_a_turkish_path_works(self):
        # LC_ALL=C on Linux leaves an ASCII file system encoding, where no such name exists.
        utf8 = sys.getfilesystemencoding().lower().replace('-', '') == 'utf8'
        folder = self.transcript.parent / ('Şimdi ❌' if utf8 else 'plain')
        folder.mkdir()
        self.transcript = folder / 'session.jsonl'
        for broken in ('{broken', 'null', '{"said": "5", "mark": null}', '{"said": 5}'):
            with self.subTest(state=broken):
                self.transcript.with_suffix('.progress-step').write_text(broken, encoding='utf-8')
                said = self.nudge([assistant(tool()) for _ in range(5)], PYTHONIOENCODING='cp1252')
                self.assertIn('5 tool calls', said['additionalContext'])

    def test_a_large_transcript_counts_the_latest_silent_interval(self):
        padding = json.dumps({'type': 'user', 'message': {'content': 'x' * 10_000}}) + '\n'
        raw = padding * 120 + ''.join(json.dumps(assistant(tool())) + '\n' for _ in range(5))
        self.assertIn('5 tool calls', self.nudge(None, raw=raw)['additionalContext'])
        raw = padding * 120 + json.dumps(assistant(text())) + '\n' + ''.join(json.dumps(assistant(tool())) + '\n' for _ in range(4))
        self.assertIsNone(self.nudge(None, raw=raw))

    def test_a_silence_longer_than_the_tail_keeps_the_three_nudge_cap(self):
        calls = [assistant(text())]
        for count in range(1, 16):
            calls.append(assistant(tool()))
            self.assertEqual(self.nudge(calls) is not None, count in (5, 10, 15), count)
        raw = ''.join(json.dumps(r) + '\n' for r in calls)
        raw += (json.dumps({'type': 'user', 'message': {'content': 'x' * 10_000}}) + '\n') * 120
        for count in range(1, 6):
            raw += json.dumps(assistant(tool())) + '\n'
            self.assertIsNone(self.nudge(None, raw=raw), count)

    def test_a_missing_or_broken_transcript_never_blocks(self):
        result = run('progress_reminder.py', json.dumps({'transcript_path': str(self.transcript / 'missing')}))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertIsNone(self.nudge(None, raw='{broken\n' * 3))
        self.assertEqual(run('progress_reminder.py', '').returncode, 0)

    def test_visible_text_before_a_large_tool_result_rearms_the_cap(self):
        calls = []
        for count in range(1, 16):
            calls.append(assistant(tool()))
            self.assertEqual(self.nudge(calls) is not None, count in (5, 10, 15))
        for reset in (assistant(text('Still working.')),
                      {'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'large-reset'}):
            calls += [reset, {'type': 'user', 'message': {'content': [
                {'type': 'tool_result', 'content': 'x' * 600_000}]}}]
            self.assertIsNone(self.nudge(calls))
            for count in range(1, 21):
                calls.append(assistant(tool()))
                self.assertEqual(self.nudge(calls) is not None, count in (5, 10, 15), count)

    def test_large_results_preserve_counts_before_the_first_nudge(self):
        calls = [assistant(tool()), assistant(tool())]
        self.assertIsNone(self.nudge(calls))
        calls.append({'type': 'user', 'message': {'content': 'x' * 600_000}})
        for count in range(3, 21):
            calls.append(assistant(tool()))
            self.assertEqual(self.nudge(calls) is not None, count in (5, 10, 15), count)

    def test_a_partial_record_is_read_again_when_complete(self):
        calls = [assistant(tool()) for _ in range(15)]
        self.assertIsNotNone(self.nudge(calls))
        prefix = ''.join(json.dumps(r) + '\n' for r in calls)
        visible = json.dumps(assistant(text()))
        self.assertIsNone(self.nudge(None, raw=prefix + visible[:20]))
        raw = prefix + visible + '\n' + json.dumps({'type': 'user', 'message': {
            'content': 'x' * 600_000}}) + '\n'
        self.assertIsNone(self.nudge(None, raw=raw))
        for count in range(1, 6):
            raw += json.dumps(assistant(tool())) + '\n'
            self.assertEqual(self.nudge(None, raw=raw) is not None, count == 5)


if __name__ == '__main__':
    unittest.main()

"""The context hook must speak once per 50k step past 200k, choose nothing itself, and never block."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'overlays/claude-code/files'
HOOK = OVERLAY / '.claude/hooks/context_size.py'


def prompt(text='go'):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def request(ctx, read=None):
    return {'type': 'assistant', 'message': {'model': 'claude-x', 'usage': {
        'input_tokens': 10, 'cache_read_input_tokens': ctx - 1010 if read is None else read,
        'cache_creation_input_tokens': 1000}}}


class ContextHookTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.transcript = self.tmp / 'session-1.jsonl'
        # The project whose .myagentkit/presence the hooks read: never the kit checkout's own.
        # A lead's session: a worker running these tests carries MYAGENTKIT_ROLE=worker.
        self.env = {k: v for k, v in os.environ.items() if k != 'MYAGENTKIT_ROLE'}
        self.env['CLAUDE_PROJECT_DIR'] = str(self.tmp)

    def run_hook(self, records, raw=None, command=None, env=None):
        self.transcript.write_text(raw if raw is not None else ''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        result = subprocess.run(command or [sys.executable, str(HOOK)],
                                input=json.dumps({'transcript_path': str(self.transcript)}),
                                text=True, encoding='utf-8', capture_output=True, timeout=30, env=env or self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_once_per_step_past_the_line(self):
        turns = [prompt(), request(150_000), prompt(), request(190_000), prompt(), request(210_000)]
        said = self.run_hook(turns + [prompt()])
        self.assertIn('Context is 210k tokens', said)
        self.assertIn('/compact', said)
        self.assertIn('hand-off', said)
        self.assertIn("closing summary", said)  # when AGENTS.md's MENTION ONCE list says
        self.assertEqual(self.run_hook(turns + [prompt(), prompt()]), '')  # a retry with no request
        turns += [prompt(), request(240_000)]
        self.assertEqual(self.run_hook(turns + [prompt()]), '')  # same step: said already
        turns += [prompt(), request(255_000)]
        self.assertIn('Context is 255k tokens', self.run_hook(turns + [prompt()]))
        # /compact: the boundary comes before any new request, and the old size is gone.
        turns += [prompt('/compact'), {'type': 'system', 'subtype': 'compact_boundary'},
                  {'type': 'user', 'isCompactSummary': True, 'message': {'content': 'summary'}}]
        self.assertEqual(self.run_hook(turns + [prompt()]), '')
        turns += [request(60_000), prompt(), request(205_000)]
        self.assertIn('Context is 205k tokens', self.run_hook(turns + [prompt()]))  # armed again

    def test_running_work_of_the_session_blocks_the_hand_off(self):
        # Owner 2026-10-26 (leeway, no-handoff-while-work-runs): a bg Bash task or async sub-agent
        # started here blocks the hand-off until its <task-id> notification or a TaskStop.
        def use(uid, name, **inp):
            return {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': uid, 'name': name, 'input': inp}]}}

        def result(uid, at='2026-10-26T10:00:00.000Z', **tur):
            return {'type': 'user', 'toolUseResult': tur, 'timestamp': at,
                    'message': {'content': [{'type': 'tool_result', 'tool_use_id': uid, 'content': 'started'}]}}

        def ended(job):
            return prompt(f'<task-notification>\n<task-id>{job}</task-id>\n<status>completed</status>\n</task-notification>')

        turns = [prompt(), use('t1', 'Bash', command='sh x', run_in_background=True, description='Run the gate'),
                 result('t1', backgroundTaskId='b1'), request(210_000)]
        said = self.run_hook(turns + [prompt()])
        self.assertIn('Hand-off blocked: 1 job(s) started in this session still run (Run the gate (b1))', said)
        self.assertNotIn('recommend ONE', said)
        turns += [ended('b1'), request(260_000)]
        said = self.run_hook(turns + [prompt()])  # the state file resumes the scan with the job ended
        self.assertNotIn('blocked', said)
        self.assertIn('recommend ONE', said)
        turns += [use('t2', 'Agent', prompt='x', description='Review the diff'),
                  result('t2', status='async_launched', agentId='a2'),
                  use('t3', 'Agent', prompt='y', description='Sync one'), result('t3', status='completed'),
                  {'type': 'system', 'subtype': 'compact_boundary'}, request(310_000)]
        said = self.run_hook(turns + [prompt()])  # the running list survives the compaction
        self.assertIn('1 job(s) started in this session still run (Review the diff (a2))', said)
        self.assertIn('never a second /compact', said)
        turns += [use('t4', 'TaskStop', task_id='a2'), request(360_000)]
        self.assertIn('recommend a hand-off', self.run_hook(turns + [prompt()]))
        # A watch on a worker's result is the worker's, not this session's (review v014-nohandoff, High);
        # a job with no end record for a day died with an earlier session (Medium).
        turns = [prompt(), use('t5', 'Bash', run_in_background=True, description='Watch w1',
                               command="until [ a -nt b ] && grep -qF '<!-- codex-worker: ready -->' a; do sleep 30; done"),
                 result('t5', backgroundTaskId='b5'),
                 use('t7', 'Bash', run_in_background=True, description='Wait w2',
                     command='python3 scripts/codex_worker.py --wait R --since S --stale I --exit E'),
                 result('t7', backgroundTaskId='b7'), request(210_000)]
        self.transcript.with_suffix('.context-step').unlink()
        self.assertIn('recommend ONE', self.run_hook(turns + [prompt()]))
        turns += [use('t6', 'Bash', run_in_background=True, description='Run the gate', command='sh scripts/check.sh'),
                  result('t6', backgroundTaskId='b6'), request(260_000)]
        self.assertIn('still run (Run the gate (b6))', self.run_hook(turns + [prompt()]))
        turns += [prompt(), {'type': 'assistant', 'timestamp': '2026-10-27T10:00:01.000Z',
                             'message': {'model': 'claude-x', 'usage': {'input_tokens': 310_000}}}]
        self.assertIn('recommend ONE', self.run_hook(turns + [prompt()]))

    def test_a_null_counter_is_zero(self):
        self.assertIn('Context is 210k tokens', self.run_hook([prompt(), {'type': 'assistant', 'message': {
            'model': 'claude-x', 'usage': {'input_tokens': 210_000, 'cache_read_input_tokens': None,
                                           'cache_creation_input_tokens': None}}}]))

    def test_legacy_step_after_compaction_is_not_announced_again(self):
        self.transcript.with_suffix('.context-step').write_text('1', encoding='utf-8')
        turns = [{'type': 'system', 'subtype': 'compact_boundary'}, request(260_000)]
        self.assertEqual(self.run_hook(turns), '')
        self.assertIn('Context is 260k tokens', self.run_hook(
            turns + [{'type': 'system', 'subtype': 'compact_boundary'}, request(260_000)]))
        self.assertIn('Context is 310k tokens', self.run_hook(turns + [request(310_000)]))

    def test_a_state_of_the_wrong_type_is_a_missing_state(self):
        # Compared, a null or string step raised TypeError, the hook swallowed it and never
        # rewrote the state: no warning until the next compaction.
        state = self.transcript.with_suffix('.context-step')
        for saved in ('{"step": null, "compactions": 0}', '{"step": "0", "compactions": 0}',
                      '{"step": 0, "compactions": true}', 'true'):
            with self.subTest(saved=saved):
                state.write_text(saved, encoding='utf-8')
                self.assertIn('Context is 260k tokens', self.run_hook([prompt(), request(260_000)]))
                self.assertIn('Context is 400k tokens', self.run_hook([prompt(), request(400_000)]))

    def test_each_band_names_itself(self):
        for ctx, band, others in ((210_000, 'yellow (200k)', ('red', 'ceiling')),
                                  (299_000, 'yellow (200k)', ('red', 'ceiling')),
                                  (300_000, 'red (300k)', ('yellow', 'ceiling')),
                                  (420_000, 'ceiling (400k)', ('yellow', 'red'))):
            with self.subTest(ctx=ctx):
                self.transcript.with_suffix('.context-step').unlink(missing_ok=True)
                said = self.run_hook([prompt(), request(ctx), prompt()])
                self.assertIn('Context is %dk tokens, %s' % (ctx // 1000, band), said)
                for other in others:
                    self.assertNotIn(other, said)

    def test_killing_a_lock_holder_allows_the_next_prompt(self):
        wrapper = self.tmp / 'held_hook.py'
        wrapper.write_text('import runpy, time\n'
                           'hook = runpy.run_path(%r)\n'
                           'def held(path, saved=None):\n'
                           '    print("held", flush=True)\n'
                           '    time.sleep(60)\n'
                           'hook["main"].__globals__["scan"] = held\n'
                           'hook["main"]()\n' % str(HOOK), encoding='utf-8')
        self.transcript.write_text(json.dumps(request(260_000)) + '\n', encoding='utf-8')
        holder = subprocess.Popen([sys.executable, str(wrapper)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        try:
            holder.stdin.write(json.dumps({'transcript_path': str(self.transcript)}))
            holder.stdin.close()
            self.assertEqual(holder.stdout.readline().strip(), 'held')
            self.assertEqual(self.run_hook([request(260_000)]), '')
        finally:
            holder.kill()
            holder.wait(timeout=5)
            holder.stdout.close()
            holder.stderr.close()
        self.assertIn('Context is 260k tokens', self.run_hook([request(260_000)]))

    def test_compaction_rearms_even_when_a_request_already_followed_it(self):
        turns = [request(310_000)]
        self.assertIn('Context is 310k tokens', self.run_hook(turns))
        turns += [{'type': 'system', 'subtype': 'compact_boundary'}, request(210_000)]
        self.assertIn('Context is 210k tokens', self.run_hook(turns))
        self.assertEqual(self.run_hook(turns), '')

    def test_after_a_compaction_only_a_hand_off_is_recommended(self):
        turns = [request(210_000)]
        said = self.run_hook(turns)
        self.assertIn('"/compact keep the open decisions', said)  # never a bare /compact
        turns += [{'type': 'system', 'subtype': 'compact_boundary'}, request(210_000)]
        said = self.run_hook(turns)
        self.assertIn('compacted already', said)
        self.assertIn('recommend a hand-off', said)
        self.assertNotIn('/compact keep', said)

    def test_a_drop_without_compaction_does_not_rearm(self):
        turns = [request(255_000)]
        self.assertIn('Context is 255k tokens', self.run_hook(turns))
        turns += [request(240_000)]
        self.assertEqual(self.run_hook(turns), '')
        turns += [request(255_000)]
        self.assertEqual(self.run_hook(turns), '')

    def test_concurrent_prompts_announce_a_step_once(self):
        self.transcript.write_text(json.dumps(request(255_000)) + '\n', encoding='utf-8')
        state = self.transcript.with_suffix('.context-step')
        state.write_text('-1', encoding='utf-8')  # the earlier hook's state is also accepted on upgrade
        # Slow the read after it got the old value: without a lock, every child announces.
        wrapper = self.tmp / 'slow_hook.py'
        wrapper.write_text('import runpy, time\nfrom pathlib import Path\n'
                           'read = Path.read_text\n'
                           'def slow(self, *args, **kwargs):\n'
                           '    value = read(self, *args, **kwargs)\n'
                           '    time.sleep(0.5)\n'
                           '    return value\n'
                           'Path.read_text = slow\n'
                           'runpy.run_path(%r, run_name="__main__")\n' % str(HOOK), encoding='utf-8')

        def invoke(_):
            return subprocess.run([sys.executable, str(wrapper)],
                                  input=json.dumps({'transcript_path': str(self.transcript)}),
                                  capture_output=True, text=True, encoding='utf-8', timeout=30, env=self.env)

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(invoke, range(6)))
        for result in results:
            self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(sum('Context is 255k tokens' in r.stdout for r in results), 1)
        self.assertEqual(self.run_hook([request(255_000)]), '')

    def test_silent_below_the_line_and_on_a_broken_transcript(self):
        self.assertEqual(self.run_hook([prompt(), request(199_000)]), '')
        self.assertEqual(self.run_hook([], raw='not json\n5\n{"type": "assistant", "message": 5}\n'), '')
        result = subprocess.run([sys.executable, str(HOOK)], input='{}', text=True, encoding='utf-8', capture_output=True,
                                timeout=30, env=self.env)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_same_named_transcripts_keep_their_own_step(self):
        # Projects' transcripts share file names; the step one named must not silence another.
        other = self.tmp / 'other'
        other.mkdir()
        turns = [prompt(), request(210_000)]
        self.assertIn('Context is 210k tokens', self.run_hook(turns))
        self.transcript = other / self.transcript.name
        self.assertIn('Context is 210k tokens', self.run_hook(turns))

    def test_a_large_transcript_resumes_at_the_saved_offset(self):
        # A full read of a 33 MB transcript took 0.9 s, too slow for every tool call (#138).
        spec = importlib.util.spec_from_file_location('context_size_under_test', HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.RECOUNT = 0
        first = json.dumps(request(210_000)) + '\n'
        self.transcript.write_bytes(first.encode())
        self.assertEqual(module.scan(self.transcript), (210_000, 0, True, len(first), {}, {}))
        with self.transcript.open('ab') as stream:
            stream.write((json.dumps(request(260_000)) + '\n' + '{"type": "system", "subtype": "compact_bou').encode())
        size = len(first) + len(json.dumps(request(260_000))) + 1
        saved = {'offset': len(first), 'last': 1, 'compactions': 5, 'known': True, 'running': {'b9': ['old job', 0]},
                 'pending': {'t9': 'Run x'}}
        # The saved compaction count proves the prefix was not read again; a partial record waits.
        self.assertEqual(module.scan(self.transcript, saved), (260_000, 5, True, size, {'b9': ['old job', 0]}, {'t9': 'Run x'}))
        self.assertEqual(module.scan(self.transcript, dict(saved, offset=10 ** 9)), (260_000, 0, True, size, {}, {}))

    def run_progress(self, records, **extra):
        self.transcript.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        result = subprocess.run([sys.executable, str(HOOK.with_name('progress_reminder.py'))],
                                input=json.dumps({'transcript_path': str(self.transcript), **extra}),
                                text=True, encoding='utf-8', capture_output=True, timeout=30, env=self.env)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        return json.loads(result.stdout)['hookSpecificOutput']['additionalContext'] if result.stdout else ''

    def test_a_tool_call_names_the_band_inside_a_long_turn(self):
        # #138: a long autonomous turn crossed 300k and 400k with no notice until the next prompt.
        self.assertEqual(self.run_progress([request(250_000)], agent_id='a1'), '')  # a sub-agent's call
        said = self.run_progress([request(250_000)])
        self.assertIn('Context is 250k tokens, yellow (200k)', said)
        self.assertNotIn('tool calls since', said)
        self.assertEqual(self.run_progress([request(250_000), request(260_000)]), '')  # same step
        self.assertEqual(self.run_hook([request(260_000)]), '')  # the prompt hook shares the step
        self.assertIn('Context is 310k tokens, red (300k)', self.run_progress([request(250_000), request(310_000)]))

    def away(self):
        (self.tmp / '.myagentkit').mkdir(exist_ok=True)
        (self.tmp / '.myagentkit/presence').write_text('away 2026-10-22T23:00:00+03:00\n', encoding='utf-8')

    def test_while_away_the_band_and_a_second_compaction_say_keep_going(self):
        # v0.13 autopilot: the lead stopped at a band line overnight and the night was lost.
        self.away()
        for turns in ([request(410_000)], [request(410_000), {'type': 'system', 'subtype': 'compact_boundary'},
                                          request(210_000)]):
            said = self.run_progress(turns)
            with self.subTest(said=said):
                self.assertIn('Context is', said)
                self.assertIn('autopilot', said)
                self.assertIn('keep going', said)
                self.assertNotIn('stop now', said)
                self.assertNotIn('recommend', said)
                self.assertNotIn('owner is back', said)  # a tool call is never the owner's message
                self.assertIn('docs/STATE.md', said)
        # leeway L14: a worker leaves STATE.md to the lead (docs/HANDOFF.md).
        self.env['MYAGENTKIT_ROLE'] = 'worker'
        said = self.run_progress([request(410_000)])
        self.assertIn('keep going', said)
        self.assertNotIn('STATE.md', said)

    def test_a_committed_away_line_without_a_presence_record_reads_as_away(self):
        # leeway L12: a clone or worktree of a night's commit carries the away line but not the
        # ignored .myagentkit/presence; the hooks follow the line until a switch records it here.
        (self.tmp / 'docs').mkdir()
        (self.tmp / 'docs/STATE.md').write_text(
            '# State\n**Owner:** away (autopilot since 2026-10-22T23:00:00+03:00)\n', encoding='utf-8')
        self.assertIn('working_mode.py present', self.run_hook([request(10_000)]))
        (self.tmp / '.myagentkit').mkdir()
        (self.tmp / '.myagentkit/presence').write_text('present 2026-10-22T23:00:00+03:00 x\n', encoding='utf-8')
        self.assertEqual(self.run_hook([request(10_000)]), '')  # the record wins over the line

    def test_a_prompt_while_away_names_the_owners_return_and_present_is_silent(self):
        self.assertEqual(self.run_hook([request(10_000)]), '')
        self.away()
        said = self.run_hook([request(10_000)])
        self.assertIn('working_mode.py present', said)
        self.assertIn('AskUserQuestion', said)
        # Owner, 2026-10-22: only a message that says or implies the return or the exit ends it;
        # a farewell, the /goal line or a late instruction is acted on and autopilot stays.
        self.assertIn('says or implies', said)
        self.assertIn('/goal line', said)
        self.assertIn('stay in autopilot', said)
        self.assertEqual(self.run_hook([request(10_000)], env=dict(self.env, MYAGENTKIT_ROLE='worker')), '')
        (self.tmp / '.myagentkit/presence').write_text('present 2026-10-22T23:00:00+03:00 x\n', encoding='utf-8')
        self.assertEqual(self.run_hook([request(10_000)]), '')


class BeforeCompactTests(unittest.TestCase):
    """PreCompact writes the git facts; SessionStart(compact) prints them after the summary (handoff-48 item 10)."""

    def test_the_note_holds_the_git_facts_and_the_compact_hook_prints_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = ['git', '-C', tmp, '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
            subprocess.run(git + ['init', '-q', '-b', 'night'], check=True)
            (root / 'a.txt').write_text('a', encoding='utf-8')
            subprocess.run(git + ['add', 'a.txt'], check=True)
            subprocess.run(git + ['commit', '-q', '-m', 'first step'], check=True)
            (root / 'b.txt').write_text('b', encoding='utf-8')
            (root / 'docs/handoffs').mkdir(parents=True)
            (root / 'docs/handoffs/old.md').write_text('old', encoding='utf-8')
            os.utime(root / 'docs/handoffs/old.md', (1, 1))
            (root / '.myagentkit/v1').mkdir(parents=True)
            (root / '.myagentkit/v1/handoff-3.md').write_text('new', encoding='utf-8')
            env = {**os.environ, 'CLAUDE_PROJECT_DIR': tmp}
            hook = OVERLAY / '.claude/hooks/before_compact.py'
            run = subprocess.run([sys.executable, str(hook)], input=json.dumps({'trigger': 'auto', 'cwd': tmp}),
                                 capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
            self.assertEqual((run.returncode, run.stdout, run.stderr), (0, '', ''))
            note = (root / '.myagentkit/compact-note.md').read_text(encoding='utf-8')
            self.assertIn('branch: night, HEAD ', note)
            self.assertIn('first step', note)
            self.assertIn('?? b.txt', note)
            self.assertIn('newest hand-off file: ' + str(Path('.myagentkit/v1/handoff-3.md')), note)
            settings = json.loads((OVERLAY / '.claude/settings.json').read_text(encoding='utf-8'))
            self.assertIn('before_compact.py', json.dumps(settings['hooks']['PreCompact']))
            command = settings['hooks']['SessionStart'][0]['hooks'][0]['command']
            (root / '.claude/hooks').mkdir(parents=True)
            (root / '.claude/hooks/after_compact.txt').write_text('re-read the rules\n', encoding='utf-8')
            printed = subprocess.run(['sh', '-c', command], capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
            self.assertEqual(printed.returncode, 0)
            self.assertIn('re-read the rules', printed.stdout)
            self.assertIn('first step', printed.stdout)
            # Printed once: a PreCompact that never ran (no Python) cannot bring the last note back.
            again = subprocess.run(['sh', '-c', command], capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
            self.assertEqual(again.returncode, 0)
            self.assertIn('re-read the rules', again.stdout)
            self.assertNotIn('first step', again.stdout)
            (root / '.myagentkit/compact-note.md').write_text('stale', encoding='utf-8')
            broken = subprocess.run([sys.executable, str(hook)], input='not json', capture_output=True, text=True, encoding='utf-8',
                                    env=env, timeout=30)
            self.assertEqual(broken.returncode, 0)
            self.assertIn('first step', (root / '.myagentkit/compact-note.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

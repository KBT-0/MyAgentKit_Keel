"""guard_worker_route.py routes a sub-agent that would wait on a long job to spawn_worker.sh.

A sub-agent runs on the five-minute cache, so a wait past five minutes re-writes its whole
context: $100 of Keel's re-writes in 14 days, all background Agent calls such as "Fix round-3
review gate findings" and "Merge three branches" (#307 baseline, docs/WORKFLOW.md "Worker cost"
rule 1). The model and effort checks live in test_overlay_permissions.py.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_worker_route.py'


def run(tool_input, tool='Agent', **extra):
    payload = json.dumps(dict({'tool_name': tool, 'tool_input': tool_input}, **extra))
    return subprocess.run([sys.executable, str(HOOK)], input=payload.encode(), capture_output=True, timeout=60)


class LongWaitRouteTests(unittest.TestCase):
    def test_a_sub_agent_that_names_a_long_job_is_refused(self):
        for tool, call in [
            ('Agent', {'description': 'Fix round-3 review gate findings',
                       'prompt': 'Fix them, then run the review gate again.'}),
            ('Agent', {'description': 'v012 ci worker', 'prompt': 'Push and wait for CI to go green.'}),
            ('Task', {'description': 'Merge three branches', 'prompt': 'Merge a, b and c into master.'}),
            ('Agent', {'description': 'x', 'prompt': 'Merging a into master; watching the pipeline until green.'}),
            ('Agent', {'description': 'x', 'prompt': 'gh run watch 123, then report.'}),
            ('Agent', {'description': 'x', 'prompt': 'Run scripts/check.sh, then report.'}),
            ('Agent', {'subagent_type': 'fork', 'description': 'x', 'prompt': 'Wait for the review.sh round.'}),
            # The kit writes identifiers in backticks; quoted job names are the same wait.
            ('Agent', {'description': 'x', 'prompt': 'Fix them, then run `scripts/check.sh` and report.'}),
            ('Agent', {'description': 'x', 'prompt': 'Push, then wait for `gh run` to finish.'}),
            ('Agent', {'description': 'x', 'prompt': 'Run "scripts/check.sh" then report.'}),
            # A rich-text paste's non-breaking space is a blank too (review 88777d130196).
            ('Agent', {'description': 'x', 'prompt': 'wait for\u00a0CI'}),
            # Not a prohibition: "not" belongs to another clause.
            ('Agent', {'description': 'x', 'prompt': 'If it is not green, run the gate again.'}),
            # Review 99c84bd7fb41: a contraction is no possessive (Medium); re-merge and a ci- job name (Lows).
            ('Agent', {'description': 'x', 'prompt': "Let's merge w3 into master."}),
            ('Agent', {'description': 'x', 'prompt': "It's merging into master; report after."}),
            ('Agent', {'description': 'x', 'prompt': 'Rebase and re-merge the branch.'}),
            ('Agent', {'description': 'x', 'prompt': 'Wait for the ci-build to go green, then report.'}),
            # Review r-leewayfield: a command whose object is a plural noun is a merge job.
            ('Agent', {'description': 'x', 'prompt': 'Merge commits from w1 and w2 into master.'}),
            ('Agent', {'description': 'x', 'prompt': 'Fix it, then merge requests from the workers in.'}),
            ('Agent', {'description': 'x', 'prompt': 'Done. Merge results of w1 and w2 into one branch.'}),
            # Review r-leewayfield round 2: a list item or a comma list gives a merge job too; a compound
            # noun is not told apart from it, so "No long wait:" stays the way past a false match.
            ('Agent', {'description': 'x', 'prompt': 'Steps:\n- rebase w2 on master\n- merge commits from w1 into master'}),
            ('Agent', {'description': 'x', 'prompt': 'Rebase w2, merge commits from w1 into master, report.'}),
        ]:
            with self.subTest(call=call):
                result = run(dict(call, model='claude-opus-5-5', effort='high'), tool)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'spawn_worker.sh', result.stderr)
                self.assertIn(b'No long wait:', result.stderr)

    def test_a_short_errand_or_one_that_says_it_will_not_wait_passes(self):
        for call in [
            {'description': 'Find the callers', 'prompt': 'List every caller of frontmatter().'},
            {'description': 'Gate review', 'prompt': 'Read the diff.\nNo long wait: reads one diff, runs nothing.'},
            {'description': 'Integration test', 'prompt': 'Count the cicd folders in navigation.'},
            # An inner diff-reviewer's prompt cites the review protocol by its file name.
            {'subagent_type': 'diff-reviewer', 'description': 'Inner review round 1',
             'prompt': 'Review the diff against docs/REVIEW_GATE.md, "What a reviewer attacks first".'},
            # Naming a job, or reporting one that already ran, waits on nothing.
            {'subagent_type': 'diff-reviewer', 'description': 'Inner review round 2',
             'prompt': 'The author ran scripts/check.sh: PASS. Fix the review gate findings and commit.'},
            {'description': 'Review', 'prompt': 'Review the merge commit 1a2b3c.'},
            {'description': 'Review', 'prompt': 'Review the  merge commit 1a2b3c.'},
            # Review 88777d130196: a prohibition waits on nothing (Medium); the noun across a line,
            # after a possessive or a demonstrative, a hyphenated word, and ci inside a name (Lows).
            {'description': 'Review', 'prompt': 'Review the diff. Do not run the gate.'},
            {'description': 'Review', 'prompt': 'Never run check.sh here.'},
            {'description': 'Review', 'prompt': 'Do NOT run the gate; the lead does.'},
            {'description': 'Review', 'prompt': "Don't wait for CI."},
            {'description': 'Review', 'prompt': 'Review the\nmerge commit 1a2b3c.'},
            {'description': 'Review', 'prompt': "Review the author's merge."},
            {'description': 'Review', 'prompt': 'Review this merge.'},
            {'description': 'Sort', 'prompt': 'Merge-sort the list.'},
            {'description': 'Docs', 'prompt': 'Watch the CI/CD section.'},
            {'description': 'Lint', 'prompt': 'Running the ci.yml linter locally.'},
            {'description': 'Tests', 'prompt': 'Run precise/CI/tests.'},
            {'description': 'Review', 'prompt': 'Review the re-merge.'},
            {'description': 'Docs', 'prompt': 'Watch the CI-CD section.'},
            {'description': 'Lint', 'prompt': 'Running the ci-lint.sh linter locally.'},
        ]:
            with self.subTest(call=call):
                result = run(dict(call, model='claude-opus-5-5', effort='high'))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_kits_own_task_prompt_template_passes(self):
        # core/docs/HANDOFF.md "Day-to-day task prompt" names the commit gate, CI and the review
        # gate; a sub-agent briefed per it must not be refused.
        handoff = (HOOK.parents[5] / 'core/docs/HANDOFF.md').read_text(encoding='utf-8')
        template = handoff.split('## Day-to-day task prompt', 1)[1].split('```', 2)[1]
        self.assertIn('review gate', template)
        result = run({'description': 'Task', 'prompt': template, 'model': 'claude-opus-5-5', 'effort': 'high'})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_other_tools_pass(self):
        self.assertEqual(run({'command': 'gh run watch 1'}, 'Bash').returncode, 0)


class FableNeverAWorkerTests(unittest.TestCase):
    # docs/WORKFLOW.md "Worker cost" rule 2 (owner 2026-11-03): Fable leads, reviews and consults only.
    def transcript(self, model):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = os.path.join(folder.name, 's.jsonl')
        lines = [{'type': 'user', 'message': {'role': 'user', 'content': 'hi'}},
                 {'type': 'assistant', 'message': {'model': 'claude-opus-5-5', 'content': []}},
                 {'type': 'assistant', 'message': {'model': model, 'content': []}},
                 {'type': 'user', 'message': {'role': 'user', 'content': 'go'}}]
        with open(path, 'w', encoding='utf-8') as f:
            f.write('x' * 70000 + '\n' + '\n'.join(json.dumps(line) for line in lines) + '\n')
        return path

    def test_a_fable_worker_is_refused(self):
        for model in ('claude-fable-5-1', 'fable', 'Fable', 'claude-fable-6'):
            for kind in (None, 'general-purpose', 'claude', 'worker', 'my-builder'):
                call = {'description': 'Build it', 'prompt': 'Write the parser.', 'model': model, 'effort': 'high'}
                if kind:
                    call['subagent_type'] = kind
                with self.subTest(model=model, kind=kind):
                    result = run(call)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(b'"Worker cost" rule 2', result.stderr)
                    self.assertIn(b'Fable consult: REASON', result.stderr)
                    self.assertIn(b'Fable worker approved by the owner: REASON', result.stderr)

    def test_a_fable_reviewer_or_an_escape_line_passes(self):
        for kind, prompt in (('diff-reviewer', 'Review the diff.'), ('myagentkit:pipeline-reviewer', 'Review it.'),
                             ('general-purpose', 'Weigh the two designs.\nFable consult: a design question, edits nothing'),
                             (None, 'Build it.\n  Fable worker approved by the owner: "do it on Fable" (2026-11-03)')):
            call = {'description': 'x', 'prompt': prompt, 'model': 'claude-fable-5-1', 'effort': 'high'}
            if kind:
                call['subagent_type'] = kind
            with self.subTest(kind=kind, prompt=prompt):
                self.assertEqual(run(call).returncode, 0)

    def test_an_escape_line_inside_a_sentence_or_without_a_reason_does_not_pass(self):
        for prompt in ('Build it; no Fable consult: needed here.', 'Fable consult:', 'Fable consult:   \nBuild it.',
                       'Write it. Fable worker approved by the owner: yes'):
            with self.subTest(prompt=prompt):
                result = run({'description': 'x', 'prompt': prompt, 'model': 'claude-fable-5-1', 'effort': 'high'})
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_a_fork_takes_the_sessions_model(self):
        fork = {'subagent_type': 'fork', 'description': 'x', 'prompt': 'Write the parser.'}
        result = run(fork, transcript_path=self.transcript('claude-fable-5-1'))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(b'Fable consult: REASON', result.stderr)
        # A fork ignores a per-call model: it still runs on Fable.
        self.assertEqual(run(dict(fork, model='claude-opus-5-5'), transcript_path=self.transcript('claude-fable-5-1')).returncode, 2)
        self.assertEqual(run(dict(fork, prompt='Fable consult: reads and answers'),
                             transcript_path=self.transcript('claude-fable-5-1')).returncode, 0)
        self.assertEqual(run(fork, transcript_path=self.transcript('claude-opus-5-5')).returncode, 0)

    def test_an_inherit_pinned_worker_on_a_fable_session_is_refused(self):
        project = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        agents = Path(project.name, '.claude', 'agents')
        agents.mkdir(parents=True)
        (agents / 'builder.md').write_text('---\nname: builder\nmodel: inherit\n---\nBuild.\n', encoding='utf-8')
        (agents / 'code-reviewer.md').write_text('---\nname: code-reviewer\nmodel: inherit\n---\nReview.\n', encoding='utf-8')
        env = dict(os.environ, CLAUDE_PROJECT_DIR=project.name)
        env.pop('CLAUDE_CODE_SUBAGENT_EFFORT', None)  # set, an inherit type with no effort names one
        env['CLAUDE_CONFIG_DIR'] = project.name  # no user settings.json that sets it either
        for kind, code in (('builder', 2), ('code-reviewer', 0)):
            payload = json.dumps({'tool_name': 'Agent', 'transcript_path': self.transcript('claude-fable-5-1'),
                                  'tool_input': {'subagent_type': kind, 'description': 'x', 'prompt': 'Do it.'}})
            with self.subTest(kind=kind):
                result = subprocess.run([sys.executable, str(HOOK)], input=payload.encode(), capture_output=True,
                                        timeout=60, env=env)
                self.assertEqual(result.returncode, code, result.stderr)

    def test_a_definition_pinned_to_fable_is_a_fable_worker(self):
        # Review 20261103T200903Z-9741b0f48830 (Medium): a pinned Fable model passed with no per-call model.
        project = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        agents = Path(project.name, '.claude', 'agents')
        agents.mkdir(parents=True)
        for name, model in (('builder', 'claude-fable-5-1'), ('quick', 'fable'), ('opus-builder', 'claude-opus-5-5'),
                            ('fable-reviewer', 'claude-fable-5-1')):
            (agents / (name + '.md')).write_text('---\nname: %s\nmodel: %s\neffort: high\n---\nDo.\n' % (name, model),
                                                 encoding='utf-8')
        env = dict(os.environ, CLAUDE_PROJECT_DIR=project.name)
        for kind, prompt, code in (('builder', 'Do it.', 2), ('quick', 'Do it.', 2),
                                   ('builder', 'Do it.\nFable consult: reads and answers', 0),
                                   ('opus-builder', 'Do it.', 0), ('fable-reviewer', 'Review it.', 0)):
            payload = json.dumps({'tool_name': 'Agent',
                                  'tool_input': {'subagent_type': kind, 'description': 'x', 'prompt': prompt}})
            with self.subTest(kind=kind, prompt=prompt):
                result = subprocess.run([sys.executable, str(HOOK)], input=payload.encode(), capture_output=True,
                                        timeout=60, env=env)
                self.assertEqual(result.returncode, code, result.stderr)
                if code:
                    self.assertIn(b'Fable worker approved by the owner: REASON', result.stderr)

    def test_a_missing_or_unreadable_transcript_passes(self):
        fork = {'subagent_type': 'fork', 'description': 'x', 'prompt': 'Write the parser.'}
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for path in (None, os.path.join(folder.name, 'gone.jsonl'), folder.name):
            with self.subTest(path=path):
                extra = {'transcript_path': path} if path else {}
                self.assertEqual(run(fork, **extra).returncode, 0)

    def test_an_opus_worker_is_untouched(self):
        result = run({'subagent_type': 'general-purpose', 'description': 'x', 'prompt': 'Write the parser.',
                      'model': 'claude-opus-5-5', 'effort': 'high'}, transcript_path=self.transcript('claude-fable-5-1'))
        self.assertEqual(result.returncode, 0, result.stderr)


class RoutingHintTests(unittest.TestCase):
    """#346: a one-page read was refused with no row to copy. PLAN 10A: CLAUDE_CODE_SUBAGENT_EFFORT ran the
    `model: inherit` diff-reviewer at the variable's effort, not the author's (RESEARCH_LOG 2026-11-10 "subeffort")."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.project, self.home = Path(folder.name, 'p'), Path(folder.name, 'h')
        agents = self.project / '.claude' / 'agents'
        agents.mkdir(parents=True)
        (self.home / '.claude').mkdir(parents=True)
        shipped = HOOK.parents[1] / 'agents' / 'diff-reviewer.md'  # the overlay's own reviewer: inherit, no effort
        (agents / 'diff-reviewer.md').write_text(shipped.read_text(encoding='utf-8'), encoding='utf-8')
        (agents / 'pinned.md').write_text('---\nname: pinned\nmodel: inherit\neffort: high\n---\nx\n', encoding='utf-8')

    def call(self, tool_input, **env_extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ('HOME', 'USERPROFILE', 'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_SUBAGENT_EFFORT')}
        env.update(CLAUDE_PROJECT_DIR=str(self.project), HOME=str(self.home), USERPROFILE=str(self.home), **env_extra)
        payload = json.dumps({'tool_name': 'Agent', 'tool_input': dict({'description': 'x', 'prompt': 'p'}, **tool_input)})
        return subprocess.run([sys.executable, str(HOOK)], input=payload.encode(), capture_output=True, timeout=60, env=env)

    def test_a_call_with_no_model_or_effort_is_shown_the_tier_1_row(self):
        for call in ({'subagent_type': 'general-purpose', 'prompt': 'read https://example.com and summarise it'},
                     {'subagent_type': 'Explore', 'prompt': 'Find where frontmatter() is called.'},
                     {'subagent_type': 'general-purpose', 'model': 'haiku'}):
            with self.subTest(call=call):
                result = self.call(call)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'"model": "haiku", "effort": "medium"', result.stderr)
        self.assertEqual(self.call({'subagent_type': 'general-purpose', 'model': 'haiku', 'effort': 'medium'}).returncode, 0)

    def test_the_subagent_effort_variable_makes_an_inherit_call_name_its_effort(self):
        def settings(path, value):
            path.write_text(json.dumps({'env': {'CLAUDE_CODE_SUBAGENT_EFFORT': value}}), encoding='utf-8')
        review = {'subagent_type': 'diff-reviewer'}
        self.assertEqual(self.call(review).returncode, 0, 'no variable: the session effort, as before')
        for where in ('environment', 'settings.local.json', 'settings.json', 'user'):
            with self.subTest(where=where):
                env = {}
                if where == 'environment':
                    env['CLAUDE_CODE_SUBAGENT_EFFORT'] = 'low'
                elif where == 'user':
                    settings(self.home / '.claude' / 'settings.json', 'low')
                else:
                    settings(self.project / '.claude' / where, 'low')
                result = self.call(review, **env)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'CLAUDE_CODE_SUBAGENT_EFFORT=low', result.stderr)
                self.assertIn(b'"Invariant"', result.stderr)
                # A per-call model leaves the variable in charge too; an effort on the call or the pin decides.
                self.assertEqual(self.call(dict(review, model='fable'), **env).returncode, 2)
                self.assertEqual(self.call(dict(review, effort='high'), **env).returncode, 0)
                self.assertEqual(self.call({'subagent_type': 'pinned'}, **env).returncode, 0)
                self.assertEqual(self.call({'subagent_type': 'fork', 'prompt': 'Read it.'}, **env).returncode, 0)
                for name in ('settings.local.json', 'settings.json'):
                    (self.project / '.claude' / name).unlink(missing_ok=True)
                (self.home / '.claude' / 'settings.json').unlink(missing_ok=True)
        (self.project / '.claude' / 'settings.json').write_text('{not json', encoding='utf-8')
        self.assertEqual(self.call(review).returncode, 0, 'an unreadable settings file is none')

    def test_a_subagent_effort_at_the_review_ceiling_runs_the_review(self):
        # hooka2 (review r1 of hookA, Low): high, the value setup/INTERVIEW.md lets a project set, is the ceiling a
        # review may run at (REVIEW_GATE.md, "Invariant"); a worker type that inherits is still asked for its effort.
        (self.project / '.claude' / 'agents' / 'builder.md').write_text(
            '---\nname: builder\nmodel: inherit\n---\nBuild.\n', encoding='utf-8')
        for level, kind, code in (('high', 'diff-reviewer', 0), ('xhigh', 'diff-reviewer', 0), ('max', 'diff-reviewer', 0),
                                  ('HIGH', 'diff-reviewer', 0), ('medium', 'diff-reviewer', 2), ('auto', 'diff-reviewer', 2),
                                  ('high', 'builder', 2)):
            with self.subTest(level=level, kind=kind):
                result = self.call({'subagent_type': kind}, CLAUDE_CODE_SUBAGENT_EFFORT=level)
                self.assertEqual(result.returncode, code, result.stderr)


if __name__ == '__main__':
    unittest.main()

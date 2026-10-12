"""The templates' pointers name sections that exist, and a reviewer reads only reviewer text."""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CALLER_HEADINGS = ('## Running it', '## Unavailable reviewer', '## Template to paste')


def source(name):
    """The kit file behind a project path: AGENTS.md is core/AGENTS.md, docs/X is core/docs/X."""
    name = name.strip()
    if name.startswith('core/') or name == 'CONTRIBUTING.md':
        return ROOT / name
    return ROOT / 'core' / name


def headings(path):
    return [line.lstrip('#').strip() for line in path.read_text().splitlines()
            if re.match(r'#{2,3} ', line)]


def reviewer_doc_lists():
    """Every default list of documents a reviewer is told to read, by where it is set."""
    lists = {}
    bridge = (ROOT / 'core/scripts/claude_bridge.py').read_text()
    for i, found in enumerate(re.findall(r'docs = (\[[^\]]*\])', bridge)):
        lists['claude_bridge.py list %d' % i] = re.findall(r'"([^"]+)"', found)
    codex = (ROOT / 'core/scripts/codex_bridge.py').read_text()
    for name, text in (('codex_bridge.py', re.search(r'"REVIEW_DOCS", "([^"]+)"', codex)),
                       ('scripts/review.sh', re.search(r'REVIEW_DOCS:-([^}]+)\}',
                                                       (ROOT / 'scripts/review.sh').read_text()))):
        lists[name] = re.split(r',\s*|\s+and\s+', text.group(1))
    return lists


class ReviewerDocumentTests(unittest.TestCase):
    def test_a_reviewer_reads_the_contract_and_not_the_caller_sections(self):
        # The reviewer once loaded the whole review protocol, 14 KB of which told the CALLER how
        # to run a review, fail over and paste a template. That text now lives in its own file.
        lists = reviewer_doc_lists()
        self.assertEqual(len(lists), 4, lists)
        for where, docs in lists.items():
            with self.subTest(where=where):
                self.assertTrue(any(d.endswith('docs/REVIEW_GATE.md') for d in docs), docs)
                for doc in docs:
                    text = source(doc).read_text()
                    for heading in CALLER_HEADINGS:
                        self.assertFalse(heading in text, '%s (%s) carries the caller section %s' % (doc, where, heading))
        gate = (ROOT / 'core/docs/REVIEW_GATE.md').read_text()
        policy = ' '.join(gate.split())
        self.assertIn('each verdict counts only for the parts the reviewing model did not write', policy)
        self.assertIn('one fresh NEW-label final review per model', policy)
        self.assertIn('both return without a High or Medium finding', policy)
        worker = ' '.join((ROOT / 'overlays/claude-code/files/.claude/agents/worker.md').read_text().split())
        self.assertIn('Inner same-model checks stay with the worker', worker)
        self.assertIn('cross-model gate findings go to the model that found them', worker)
        for needed in ('`Accept` / `Accept with Manual Checks` / `Reject`',
                       'a disproved finding counts\nonly after the reviewer has checked it against the code',
                       'a deferred one stays open under\nManual checks, so it rules out a plain Accept',
                       '**A Reject is not closed by its fixes.**'):
            self.assertIn(needed, gate)
        running = (ROOT / 'core/docs/REVIEW_RUNNING.md').read_text()
        for heading in CALLER_HEADINGS:
            self.assertIn(heading, running)


class SectionPointerTests(unittest.TestCase):
    def test_routing_and_closure_rules_agree(self):
        workflow = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8')
        self.assertIn('after the second dirty round', workflow)
        self.assertIn('python3 scripts/usage_summary.py', workflow)
        flat = ' '.join(workflow.split())
        for rule in ('two at a time until the lead has measured its host', '4 GB reserve',
                     'Win32_OperatingSystem', 'free -g', 'vm_stat', 'lowers the number after a low-memory reap',
                     'conflict resolution is a part authored by whoever resolved it',
                     'rebuilding the integration branch without it', 'kills the background jobs started from its tool shell'):
            self.assertIn(rule, flat)
        self.assertIn('review rounds run per cluster of related branches', flat)
        self.assertIn('After their first round, merge branches touching the same files into one integration branch', flat)
        self.assertIn('remaining rounds run on the cluster', flat)
        gotchas = ' '.join((ROOT / 'core/docs/GOTCHAS.md').read_text(encoding='utf-8').split())
        for rule in ("lead's tool shell", 'on most hosts', '`&` under `sh -c`',
                     '`nohup`', 'Windows Terminal tab', 'command line names the checkout or its worktrees',
                     'Wait for the survivors by default', 'reason that holds', 'Win32_Process', 'pgrep -af', 'ps -eww'):
            self.assertIn(rule, gotchas)
        self.assertNotIn('stop them with a reason', gotchas)
        running = ' '.join((ROOT / 'core/docs/REVIEW_RUNNING.md').read_text(encoding='utf-8').split())
        self.assertIn('Start the self-test and two reviewers at once', running)
        self.assertIn('memory budget', running)
        self.assertIn('"Worker cost", rule 6', running)
        for policy in (flat, gotchas, running):
            self.assertNotIn('at most two heavy background jobs', policy)
            self.assertNotIn('this host', policy)
        # Rules of 2026-10-12: each said once, beside its siblings; reviews are never reduced.
        for rule in ('effort is never carried up from the round before',
                     'Both start at the cheapest table row that fits',
                     'the lead never opens visible sessions to show the workflow',
                     'The self-test runs once per batch, beside the review',
                     'Open issues are never closed to finish a release',
                     "never only into a lead's private memory",
                     'reviews are never reduced'):
            self.assertEqual(flat.count(rule), 1, rule)
        self.assertIn('**Prevention over detection.**', workflow.split('## Review rounds')[1].split('\n\n')[1])
        self.assertIn('| Mechanical work and re-review of a small fix round | medium |', workflow)
        for name in ('core/docs/REVIEW_RUNNING.md', 'core/docs/WORKFLOW.md',
                     'core/docs/REVIEW_GATE.md', 'core/AGENTS.md'):
            policy = ' '.join((ROOT / name).read_text(encoding='utf-8').split())
            for rule in ('model B fixes its own findings',
                         'model A reviews B\'s fix under a fresh label',
                         'B\'s final review counts as clean for every other part',
                         'no open High or Medium finding on any part by a model that did not write that part'):
                self.assertIn(rule, policy, name)
        handoff = (ROOT / 'core/docs/HANDOFF.md').read_text(encoding='utf-8')
        self.assertIn('Route: quick|build|deep · Risk: low|medium|high · Checks: ...', handoff)
        for name in ('core/docs/REVIEW_RUNNING.md', 'core/docs/REVIEW_GATE.md', 'core/AGENTS.md'):
            policy = ' '.join((ROOT / name).read_text(encoding='utf-8').split())
            self.assertIn('one fresh NEW-label final review per model', policy, name)
            self.assertIn('both return without a High or Medium finding', policy, name)
        bridge = (ROOT / 'core/scripts/claude_bridge.py').read_text(encoding='utf-8')
        self.assertIn('one fresh NEW-label final review per model', bridge)
        self.assertNotIn('model did not write the latest fix; the final Accept', bridge)
        # A single closing review contradicts the per-model final reviews wherever it is said.
        for path in [ROOT / 'core/AGENTS.md', *sorted((ROOT / 'core/docs').glob('*.md'))]:
            self.assertNotIn('closing review', path.read_text(encoding='utf-8').lower(), path)

    def test_the_mode_command_and_skill_know_every_mode_the_workflow_defines(self):
        # The kit ships the working modes; {{MODEL_ROUTING}} left each project to write its own.
        workflow = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8')
        table = workflow.split('### Working modes, by name')[1].split('####')[0]
        rows = re.findall(r'^\| `([a-z-]+)` \| ([^|(]+?)(?: \(main mode\))? \|', table, re.M)
        self.assertEqual(sorted(m for m, _ in rows), ['claude-first', 'claude-only', 'claude-saver', 'codex-first',
                                                       'codex-saver', 'cross-performance', 'cross-saving'])
        command = (ROOT / 'plugin/commands/mode.md').read_text(encoding='utf-8')
        skill = (ROOT / 'plugins/myagentkit/skills/myagentkit-mode/SKILL.md').read_text(encoding='utf-8')
        # The command may run its helper unprompted, never any Python code.
        tools = re.search(r'(?m)^allowed-tools: (.*)$', command)[1].split(', ')
        self.assertEqual([t for t in tools if t.startswith('Bash(')],
                         ['Bash(%s scripts/working_mode.py:*)' % p for p in ('python', 'python3', 'py -3')])
        for mode, turkish in rows:
            with self.subTest(mode=mode):
                self.assertRegex(workflow, r'(?m)^#### %s \(%s\)' % (mode, turkish))
                definition = workflow.split('#### %s (' % mode)[1].split('####')[0]
                for field in ('Ends', 'Lessons', 'Effort', 'Workers'):
                    self.assertIn('**%s:**' % field, definition)
                for text in (command, skill):
                    self.assertIn(mode, text)
                    self.assertIn(turkish, text)
        self.assertIn('**Working mode:** cross-performance', (ROOT / 'core/docs/STATE.md').read_text())
        for name in ('core/docs/WORKFLOW.md', 'setup/INTERVIEW.md'):
            self.assertNotIn('{{MODEL_ROUTING}}', (ROOT / name).read_text(encoding='utf-8'))
        handoff = (ROOT / 'core/docs/HANDOFF.md').read_text(encoding='utf-8')
        for sidecar in ('.myagentkit/workers/NAME.session', 'QUESTION-NAME.md'):
            self.assertIn(sidecar, handoff)
        self.assertNotIn('`RESULT-NAME.session`', handoff)
        self.assertIn('<!-- codex-worker: ready -->', handoff)
        self.assertIn('codex_worker.py --wait FILE --since START', handoff)
        self.assertIn('before publishing the question', handoff)
        self.assertIn('Publish the blocked result with this same protocol before publishing the question.', handoff)
        self.assertNotIn('commits the file. It then goes on', handoff)
        self.assertNotIn('owner only after that commit', handoff)

    def test_the_lead_keeps_its_shell_in_its_own_checkout(self):
        text = (ROOT / 'core/docs/WORKFLOW.md').read_text().split("### The lead's steps when a branch is ready")[1]
        self.assertIn("The lead never changes its shell directory into a worker's worktree", text)
        self.assertIn('use `git -C <worktree>` for its Git commands', text)
        self.assertIn("The shell stays in the lead's checkout", text)

    def test_incremental_build_briefs_name_both_shared_dependencies(self):
        text = (ROOT / 'core/docs/HANDOFF.md').read_text().split('## The brief')[1].split('4. **Acceptance:**')[0]
        self.assertIn("include inputs read by always-run steps in every stage's dependency set", text)
        self.assertIn('The driver script that holds the stage commands must invalidate every stage when it changes.', text)

    def test_readme_ci_platforms_match_the_matrix(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('os: [ubuntu-latest, macos-latest]', workflow)
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('windows:\n    name: windows-latest', workflow)
        self.assertIn('Ubuntu, macOS and native Windows are in CI', readme)
        self.assertIn('developed on native Windows', readme)
        self.assertNotIn('Linux, WSL and macOS are in CI', readme)

    def test_every_named_section_exists_in_the_file_named(self):
        # A pointer such as (`docs/WORKFLOW.md`, "Writing a gate") sends an agent to one section
        # instead of the whole file; a renamed heading would send it nowhere.
        pattern = re.compile(r'`((?:docs/)?[A-Z_]+\.md)`,\s+(?:the four\s+)?"([^"]+)"')
        sources = [ROOT / 'core/AGENTS.md'] + sorted((ROOT / 'core/docs').glob('*.md'))
        checked = 0
        for path in sources:
            text = re.sub(r'\s+', ' ', path.read_text())
            for target, section in pattern.findall(text):
                with self.subTest(source=path.name, target=target, section=section):
                    # A heading, or a bold label inside a list (HANDOFF's "**Proof:**").
                    names = headings(source(target))
                    self.assertTrue(any(h == section or h.startswith(section + ' ') for h in names)
                                    or '**' + section + ':**' in source(target).read_text(),
                                    '%s names "%s" in %s, which has no such heading' % (path.name, section, target))
                    checked += 1
        self.assertGreater(checked, 10)

    def test_the_attack_list_lives_once_and_both_checklists_point_at_it(self):
        # A reviewer attacks the list and a worker checks it before reporting. Two copies drift,
        # and a worker then reports clean against a list the reviewer no longer uses.
        section = 'What a reviewer attacks first'
        self.assertIn(section, headings(ROOT / 'core/docs/REVIEW_GATE.md'))
        pointer = '`docs/REVIEW_GATE.md`, "%s"' % section
        for path in (ROOT / 'core/docs/WORKFLOW.md',
                     ROOT / 'overlays/claude-code/files/.claude/agents/worker.md'):
            with self.subTest(checklist=path.name):
                text = re.sub(r'\s+', ' ', path.read_text())
                self.assertIn('Before you report', text)
                self.assertIn(pointer, text)
                self.assertFalse('core.checkStat' in text, 'the list is copied, not pointed at')

    def test_the_gotchas_contents_lists_every_entry(self):
        text = (ROOT / 'core/docs/GOTCHAS.md').read_text()
        contents = text[text.index('## Contents'):text.index('---')]
        for heading in headings(ROOT / 'core/docs/GOTCHAS.md'):
            if heading != 'Contents':
                self.assertIn(heading, contents)


if __name__ == '__main__':
    unittest.main()

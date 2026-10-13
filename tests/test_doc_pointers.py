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
        self.assertIn('The session that wrote a patch never reviews or approves it', policy)
        self.assertIn('At most two rounds under one label', policy)
        self.assertIn('Report new Critical or High findings', (ROOT / 'core/scripts/claude_bridge.py').read_text())
        worker = ' '.join((ROOT / 'overlays/claude-code/files/.claude/agents/worker.md').read_text().split())
        self.assertIn('Inner checks stay with the worker', worker)
        self.assertIn("a gate finding goes to a fresh worker of the author's side", worker)
        for needed in ('`Accept` / `Accept with Manual Checks` / `Reject`',
                       'a disproved finding counts only after the reviewer has checked it against the code',
                       'a deferred one stays open under Manual checks, so it rules out a plain Accept',
                       '**A Reject is not closed by its fixes.**'):
            self.assertIn(needed, policy)
        running = (ROOT / 'core/docs/REVIEW_RUNNING.md').read_text()
        for heading in CALLER_HEADINGS:
            self.assertIn(heading, running)


class SectionPointerTests(unittest.TestCase):
    def test_routing_and_closure_rules_agree(self):
        workflow = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8')
        self.assertIn('python3 scripts/usage_summary.py', workflow)
        flat = ' '.join(workflow.split())
        for rule in ('two at a time until the lead has measured its host', '4 GB reserve',
                     'Win32_OperatingSystem', 'free -g', 'vm_stat', 'lowers the number after a low-memory reap',
                     'conflict resolution is a part authored by whoever resolved it',
                     'rebuilding the integration branch without it', 'kills the background jobs started from its tool shell'):
            self.assertIn(rule, flat)
        budget_rule = ' '.join(workflow.split('6. **Parallel workers only for independent modules**')[1].split('7. **Worker reports are short**')[0].split())
        for rule in ('Start the two reviewers together',
                     'Start the self-test with them only when all three jobs fit within the budget',
                     'With a budget of two, start both reviewers first, then the self-test when one reviewer ends',
                     'Never reduce the reviews; run them one after the other only when the owner is away and at least one job fits the budget, as defined below; the self-test waits'):
            self.assertIn(rule, budget_rule)
        self.assertIn("A review round's floor is the two reviewers", budget_rule)
        self.assertIn('when two slots are free; heavy jobs already running take slots', budget_rule)
        self.assertIn('rather than waiting without limit', budget_rule)
        self.assertIn("as a recorded exception (a line in the lead's RESULT/notes file names the budget figure)", budget_rule)
        self.assertIn('starts the round only when two jobs fit', budget_rule)
        self.assertIn('When the owner gives no answer to that question within one review timeout (`REVIEW_TIMEOUT_SECONDS`), the owner is away', budget_rule)
        self.assertIn('When the owner is away and at least one job fits the budget', budget_rule)
        self.assertIn('When not even one job fits, the review round stays blocked and the lead reports the capacity figure to the owner; nothing heavy starts.', budget_rule)
        self.assertIn('"In parallel" means the reviewers', flat)
        self.assertIn('then gets ONE final review under a label never used before', flat)
        gotchas = ' '.join((ROOT / 'core/docs/GOTCHAS.md').read_text(encoding='utf-8').split())
        for rule in ("lead's tool shell", 'on most hosts', '`&` under `sh -c`',
                     '`nohup`', 'Windows Terminal tab', 'command line names the checkout or its worktrees',
                     'Wait for the survivors by default', 'reason that holds',
                     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf('<checkout>', [StringComparison]::OrdinalIgnoreCase) -ge 0 } | Select ProcessId,CommandLine",
                     "Linux `ps -eo pid,args | grep -F -- '<checkout>'`",
                     "macOS `ps -eww -o pid,args | grep -iF -- '<checkout>'`",
                     "Ignore the listing's own rows: the `grep`, and the shell or PowerShell that runs the listing",
                     'The command-line listing is only a shortcut for the jobs it can see',
                     "The project's gate holds the lock at `git rev-parse --git-path check.lock` and publishes `check-selftest` beside it; find the lock holder as described under ",
                     "A build server the gate started keeps the gate lock",
                     "A review holds no checkout lock; read its chain record as follows.",
                     "The kit's own self-test (`scripts/check.sh` → `scripts/check_kit.py`) holds no checkout lock and publishes no checkout self-test marker.",
                     'It is visible only in the process listing: look for a `python` process whose arguments name `check_kit.py` under the checkout.',
                     "If those arguments are relative, confirm the checkout through the process's working directory.",
                     'After a cut-off, look for this self-test before resuming heavy work; wait for any survivor or ask the owner.',
                     'For reviews, read the highest-numbered `<chain>-N.json` in `.myagentkit/usage/chains/`; nothing in the record names its process.',
                     '`<chain>-0.json` always stays pending and is not evidence of a running review.',
                     'A review is finished only when that latest record has status `completed`, or status `failed` with no further attempt possible (the attempt count equals the number of possible attempts, a `failure_kind` outside the dispatcher\'s unavailable set, `fallback_blocked` set, or `fallback_allowed` false, or the failed attempt has no `evidence` or `usage_record`: the dispatcher never falls over from such an attempt).',
                     'The number of possible attempts is one without `--fallback`, two with it.',
                     'Use the mtime of `<chain>-0.json` as the review start time.',
                     'After a cut-off, treat the review as running for at least `REVIEW_TIMEOUT_SECONDS` (2700 s when unset, 3600 at most; the record does not store it) times the number of possible attempts plus overhead (about two hours with 3600 s and `--fallback`), unless the latest record shows it is finished as above.',
                     'This window is a lower bound, not proof that an orphaned reviewer stopped.',
                     'After the window, the lead still confirms completion in the process listing.',
                     'On POSIX, the reviewer runs in its own session; a supervisor killed with `SIGKILL` cannot enforce its timeout.',
                     'Look for a `codex` or `claude` process whose arguments name the throwaway copy under the temp folder (`myagentkit-codex-*` or `myagentkit-review-*`).',
                     'Use the same listing commands with the copy path; confirm its working directory if the arguments omit that path.',
                     'If a reviewer survives, wait for it or ask the owner before starting any heavy job.',
                     'Never start a heavy job beside a survivor, or edit or merge its worktree.',
                     "Git Bash's `/c/x`", 'the `pwd -P` form of a symlinked checkout', '`/private/var` for `/var`',
                     "A checkout path containing an apostrophe cannot go inside the single quotes as is; on Linux/macOS write it as `'\\''` or put the path in a variable and match \"$checkout\"; on Windows double the apostrophe inside the PowerShell single-quoted string.",
                     'The Windows match ignores case because Windows paths do'):
            with self.subTest(rule=rule):
                self.assertIn(rule, gotchas)
        self.assertNotIn("grep -v -F 'grep -F'", gotchas)
        self.assertNotIn('every other row is a survivor', gotchas)
        self.assertNotIn('It ignores its own rows', gotchas)
        self.assertNotIn("Only a review's own reviewer process holds no checkout lock.", gotchas)
        self.assertNotIn('`.git/check.lock` and publishes `.git/check-selftest`', gotchas)
        self.assertNotIn('the chain record has a completed or failed attempt', gotchas)
        self.assertNotIn('Never reduce the reviews or deliberately run the reviewers one after the other', budget_rule)
        self.assertNotIn('stop them with a reason', gotchas)
        self.assertNotIn('its own process by grepping the listing for `.myagentkit/usage`', gotchas)
        running = ' '.join((ROOT / 'core/docs/REVIEW_RUNNING.md').read_text(encoding='utf-8').split())
        self.assertIn('Start the self-test and two reviewers together only when the memory budget permits', running)
        self.assertIn('memory budget', running)
        self.assertIn('"Worker cost", rule 6', running)
        for old_launch in ('Independent reviews run at the same time, with each other and with the self-test',
                           'in parallel with the self-test, never after it',
                           'Start the self-test and the review together, on the same commit, never one after the other',
                           'Start the self-test and two reviewers at once'):
            self.assertNotIn(old_launch, flat + ' ' + running)
        self.assertIn('The launch sequence follows "Worker cost", rule 6', flat)
        self.assertIn('Start the self-test and the reviews on the same commit, following "Worker cost", rule 6', flat)
        self.assertNotIn("Where-Object CommandLine -like '*<checkout>*'", gotchas)
        self.assertNotIn('pgrep -af <checkout>', gotchas)
        self.assertNotIn('grep <checkout>', gotchas)
        for policy in (flat, gotchas, running):
            self.assertNotIn('at most two heavy background jobs', policy)
            self.assertNotIn('this host', policy)
        # Rules of 2026-10-12: each said once, beside its siblings; reviews are never reduced.
        for rule in ('effort is never carried up from the round before',
                     'Both start at the cheapest table row that fits',
                     'the lead never opens visible sessions to show the workflow',
                     'The self-test runs once per batch',
                     'Open issues are never closed to finish a release',
                     "never only into a lead's private memory",
                     'reviews are never reduced'):
            self.assertEqual(flat.count(rule), 1, rule)
        self.assertIn('**Prevention over detection.**', workflow.split('## Review rounds')[1].split('\n\n')[1])
        self.assertIn('| Mechanical work and re-review of a small fix round | medium |', workflow)
        handoff = (ROOT / 'core/docs/HANDOFF.md').read_text(encoding='utf-8')
        self.assertIn('Route: quick|build|deep · Risk: low|medium|high · Checks: ...', handoff)
        # The per-model closure rules of v0.10 are gone with the single-model default: one
        # round limit and one final review, said in the gate and nowhere else.
        for name in ('core/docs/REVIEW_RUNNING.md', 'core/docs/WORKFLOW.md', 'core/docs/REVIEW_GATE.md',
                     'core/AGENTS.md', 'core/scripts/claude_bridge.py'):
            policy = ' '.join((ROOT / name).read_text(encoding='utf-8').split())
            for old in ('model B fixes its own findings', 'one fresh NEW-label final review per model',
                        'both return without a High or Medium finding', 'after the second dirty round'):
                self.assertNotIn(old, policy, name)
        bridge = (ROOT / 'core/scripts/claude_bridge.py').read_text(encoding='utf-8')
        self.assertNotIn('model did not write the latest fix; the final Accept', bridge)
        for path in [ROOT / 'core/AGENTS.md', *sorted((ROOT / 'core/docs').glob('*.md'))]:
            self.assertNotIn('closing review', path.read_text(encoding='utf-8').lower(), path)

    def test_the_mode_command_and_skill_know_every_mode_the_workflow_defines(self):
        # The kit ships the working modes; {{MODEL_ROUTING}} left each project to write its own.
        workflow = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8')
        table = workflow.split('### Working modes, by name')[1].split('####')[0]
        rows = re.findall(r'^\| `([a-z-]+)` \| ([^|(]+?)(?: \(main mode\))? \|', table, re.M)
        self.assertEqual(sorted(m for m, _ in rows), ['normal', 'saver', 'solo'])
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
        self.assertIn('**Working mode:** solo', (ROOT / 'core/docs/STATE.md').read_text())
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

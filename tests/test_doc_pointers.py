"""The templates' pointers name sections that exist, and a reviewer reads only reviewer text."""
import re
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CALLER_HEADINGS = ('## Running it', '## Unavailable reviewer', '## Template to paste')
# The reference docs whose generic text is kit-owned (#94): docs/<NAME>.md points into docs/<NAME>_KIT.md.
KIT_SIBLINGS = ('DEV_SETUP', 'GOTCHAS', 'HANDOFF', 'REVIEW_RUNNING')


def source(name):
    """The kit file behind a project path: AGENTS.md is core/AGENTS.md, docs/X is core/docs/X."""
    name = name.strip()
    if name.startswith('core/') or name == 'CONTRIBUTING.md':
        return ROOT / name
    return ROOT / 'core' / name


def headings(path):
    return [line.lstrip('#').strip() for line in path.read_text(encoding='utf-8').splitlines()
            if re.match(r'#{2,3} ', line)]


def workflow_rules_and_reasons():
    """WORKFLOW.md and its kit-owned rationale (#296), for text that may live in either."""
    return '\n'.join((ROOT / 'core/docs' / name).read_text(encoding='utf-8')
                     for name in ('WORKFLOW.md', 'WORKFLOW_RATIONALE.md'))


def with_kit(name):
    """A reference doc and its kit-owned part (#94), for text that may live in either."""
    return '\n'.join((ROOT / 'core/docs' / (name + suffix)).read_text(encoding='utf-8')
                     for suffix in ('.md', '_KIT.md'))


def reviewer_doc_lists():
    """Every default list of documents a reviewer is told to read, by where it is set."""
    lists = {}
    bridge = (ROOT / 'core/scripts/claude_bridge.py').read_text(encoding='utf-8')
    for i, found in enumerate(re.findall(r'^REVIEW_DOCS = (\([^)]*\))|docs = (\[[^\]]*\])', bridge, re.M)):
        lists['claude_bridge.py list %d' % i] = re.findall(r'"([^"]+)"', ''.join(found))
    codex = (ROOT / 'core/scripts/codex_bridge.py').read_text(encoding='utf-8')
    assert re.search(r'from claude_bridge import \([^)]*\bREVIEW_DOCS\b', codex, re.S), 'Codex must import the shared reading list'
    assert 'os.environ.get("REVIEW_DOCS", ", ".join(REVIEW_DOCS))' in codex, 'Codex must use the shared default'
    lists['codex_bridge.py'] = re.findall(r'"([^"]+)"', re.search(r'^REVIEW_DOCS = (\([^)]*\))', bridge, re.M).group(1))
    text = re.search(r'REVIEW_DOCS:-([^}]+)\}',
                     (ROOT / 'scripts/review.sh').read_text(encoding='utf-8'))
    lists['scripts/review.sh'] = re.split(r',\s*|\s+and\s+', text.group(1))
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
                    text = source(doc).read_text(encoding='utf-8')
                    for heading in CALLER_HEADINGS:
                        self.assertFalse(heading in text, '%s (%s) carries the caller section %s' % (doc, where, heading))
        gate = (ROOT / 'core/docs/REVIEW_GATE.md').read_text(encoding='utf-8')
        policy = ' '.join(gate.split())
        self.assertIn('The session that wrote a patch never reviews or approves it', policy)
        self.assertIn('At most two rounds under one label', policy)
        self.assertIn('Report new Critical or High findings', (ROOT / 'core/scripts/claude_bridge.py').read_text(encoding='utf-8'))
        worker = ' '.join((ROOT / 'overlays/claude-code/files/.claude/agents/worker.md').read_text(encoding='utf-8').split())
        self.assertIn('Inner checks stay with the worker', worker)
        self.assertIn("a gate finding goes back to the author's side", worker)
        for needed in ('`Accept` / `Accept with Manual Checks` / `Reject`',
                       'a disproved finding counts only after the reviewer has checked it against the code',
                       'a deferred one stays open under Manual checks, so it rules out a plain Accept',
                       '**A Reject is not closed by its fixes.**'):
            self.assertIn(needed, policy)
        running = (ROOT / 'core/docs/REVIEW_RUNNING.md').read_text(encoding='utf-8')
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
        # Paid reviews run one after the other unless the owner allows parallel (v0.11 close-out
        # decision 9, BACKLOG B14); a tier's floor is its own reviewer count (KARARLAR B01 (3), B15).
        for rule in ('Paid reviews run one after the other (rule 1)',
                     'run together only when {{OWNER_NAME}} allows it for that round and two slots are free',
                     "heavy jobs already running take slots",
                     'The acceptance gate run starts beside a review when the budget has a slot for it',
                     "Never reduce a tier's reviews: a high-tier round's floor is its two reviewers, a low or medium round's its one",
                     'the review round stays blocked and the lead reports the capacity figure to the owner; nothing heavy starts.'):
            self.assertIn(rule, budget_rule)
        for old in ("A review round's floor is the two reviewers", 'Start the two reviewers together',
                    'the owner is away', 'as a recorded exception'):
            self.assertNotIn(old, budget_rule)
        self.assertIn("the gate's reviewers run one after the other unless {{OWNER_NAME}} allows parallel", flat)
        self.assertIn('then gets ONE final review under a label never used before', flat)
        gotchas = ' '.join(with_kit('GOTCHAS').split())
        for rule in ("lead's tool shell", 'on most hosts', '`&` under `sh -c`',
                     '`nohup`', 'Windows Terminal tab', 'command line names the checkout or its worktrees',
                     'Wait for the survivors by default', 'reason that holds',
                     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf('<checkout>', [StringComparison]::OrdinalIgnoreCase) -ge 0 } | Select ProcessId,CommandLine",
                     "Linux `ps -eo pid,args | grep -F -- '<checkout>'`",
                     "macOS `ps -eww -o pid,args | grep -iF -- '<checkout>'`",
                     "Ignore the listing's own rows: the `grep`, and the shell or PowerShell that runs the listing",
                     'The command-line listing is only a shortcut for the jobs it can see',
                     "The project's gate holds the lock at `git rev-parse --git-path check.lock`; find the lock holder as described under ",
                     "A build server the gate started keeps the gate lock",
                     "A review holds no checkout lock; read its chain record as follows.",
                     "The kit's own check (`scripts/check.sh` → `scripts/check_kit.py`) holds no checkout lock.",
                     'It is visible only in the process listing: look for a `python` process whose arguments name `check_kit.py` under the checkout.',
                     "If those arguments are relative, confirm the checkout through the process's working directory.",
                     'After a cut-off, look for this check before resuming heavy work; wait for any survivor or ask the owner.',
                     'For reviews, read the highest-numbered `<chain>-N.json` in `.myagentkit/usage/chains/`; nothing in the record names its process.',
                     '`<chain>-0.json` always stays pending and is not evidence of a running review.',
                     'A review is finished only when that latest record has status `completed`, or status `failed` and no `next_attempt`.',
                     'The number of possible attempts is one, plus up to two capacity retries of Codex (a wait of up to 20 minutes before each), plus one quota switch or fallback.',
                     'Use the mtime of `<chain>-0.json` as the review start time.',
                     'After a cut-off, treat the review as running for at least `REVIEW_TIMEOUT_SECONDS` (2700 s when unset, 3600 for a high-effort Codex review and at most; the record does not store it) times the number of possible attempts plus the capacity waits and overhead (about 4 h 40 min with 3600 s: four attempts and two 20-minute waits), unless the latest record shows it is finished as above.',
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
        # rpipe review Low: "about two hours" was the window before the capacity retries counted.
        self.assertNotIn('about two hours', gotchas)
        self.assertNotIn('every other row is a survivor', gotchas)
        self.assertNotIn('It ignores its own rows', gotchas)
        self.assertNotIn("Only a review's own reviewer process holds no checkout lock.", gotchas)
        self.assertNotIn('check-selftest', gotchas)
        self.assertNotIn('the chain record has a completed or failed attempt', gotchas)
        self.assertNotIn('Never reduce the reviews or deliberately run the reviewers one after the other', budget_rule)
        self.assertNotIn('stop them with a reason', gotchas)
        self.assertNotIn('its own process by grepping the listing for `.myagentkit/usage`', gotchas)
        running = ' '.join((ROOT / 'core/docs/REVIEW_RUNNING.md').read_text(encoding='utf-8').split())
        self.assertIn('The two reviewers run one after the other unless {{OWNER_NAME}} allows parallel', running)
        self.assertIn('start the acceptance gate run beside a review only when the memory budget permits', running)
        self.assertIn('memory budget', running)
        self.assertIn('"Worker cost", rule 6', running)
        for old_launch in ('Independent reviews run at the same time, with each other and with the self-test',
                           'in parallel with the self-test, never after it',
                           'Start the self-test and the review together, on the same commit, never one after the other',
                           'Start the self-test and two reviewers at once'):
            self.assertNotIn(old_launch, flat + ' ' + running)
        self.assertIn('The launch sequence follows "Worker cost", rule 6', flat)
        self.assertIn('Start the acceptance gate run (`./scripts/check.sh`) and the reviews on the same commit, following "Worker cost", rule 6', flat)
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
                     'The acceptance run is once per batch',
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

    def test_the_patchs_author_records_dispositions_and_drops_no_finding(self):
        # #104: cross-review told the requesting session, possibly the author, to drop what it
        # disproved and to report its own verdict, so the author approved its own patch.
        read = lambda name: ' '.join((ROOT / name).read_text(encoding='utf-8').split())
        for name in ('plugin/commands/cross-review.md', 'core/docs/REVIEW_GATE.md', 'core/docs/WORKFLOW.md'):
            with self.subTest(name=name):
                self.assertIn('the author of the patch drops nothing', read(name).lower())
        command = read('plugin/commands/cross-review.md')
        self.assertIn("report the reviewer's verdict and your dispositions", command)

    def test_the_diff_reviewer_names_its_reading_and_makes_its_own_copy(self):
        # #105: "run your reproductions in a throwaway copy" named no way to make one (a review
        # mutated tracked files and reverted them), and "its reading list" pointed at nothing.
        # #103: it is the author's side's early check, not the gate's review.
        reviewer = ' '.join((ROOT / 'overlays/claude-code/files/.claude/agents/diff-reviewer.md')
                            .read_text(encoding='utf-8').split())
        self.assertIn('Read `AGENTS.md`, `docs/ARCHITECTURE.md` and `docs/REVIEW_GATE.md`', reviewer)
        self.assertIn("the author's side's early check, not the gate's review", reviewer)
        self.assertIn('Never edit a file of the checkout, even for a moment', reviewer)
        self.assertIn('git archive HEAD | tar -x -C "$copy"', reviewer)
        # rpipe review Low: without the bridge's flags an owner's diff.noprefix broke `git apply`
        # in the copy, and a TMPDIR inside the checkout put the copy in the reviewed repository.
        self.assertIn('git diff HEAD --binary --no-ext-diff --no-textconv --no-color --src-prefix=a/ --dst-prefix=b/', reviewer)
        self.assertIn('must not lie inside the checkout', reviewer)
        self.assertNotIn('its reading list', reviewer)
        self.assertIn('### Review inside the worker', (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8'))

    def test_a_brief_names_what_the_workers_environment_lacks(self):
        # #107: six briefs of one project re-taught sandbox workarounds by hand.
        handoff = ' '.join((ROOT / 'core/docs/HANDOFF.md').read_text(encoding='utf-8').split())
        self.assertIn('A task whose checks build, download or write outside the worktree quotes its '
                      'environment', handoff)

    def test_review_rounds_are_capped_once_and_the_lead_reads_a_short_block(self):
        # #106: inner rounds ran "until no Medium remains", which never ends. #123: the final
        # review was due per branch in WORKFLOW and per release in the gate. #85: the lead's
        # required reading was ~45k characters of "Worker cost" and "Review rounds".
        read = lambda name: ' '.join((ROOT / name).read_text(encoding='utf-8').split())
        workflow, gate = read('core/docs/WORKFLOW.md'), read('core/docs/REVIEW_GATE.md')
        worker = read('overlays/claude-code/files/.claude/agents/worker.md')
        self.assertIn('At most two inner rounds', worker)
        self.assertIn("Inner rounds keep the gate's cap", workflow)
        # One round-2 scope, the gate's, in all three; no unconditional second reviewer.
        scope = 'round 2 confirms every finding the dispositions claim fixed, a Medium included'
        self.assertIn('R' + scope[1:], gate)
        brief = workflow.split('### The rules in brief')[1].split('### The measurements')[0]
        self.assertIn(scope, brief)
        self.assertIn(scope.split('round 2 ')[1], workflow.split('Inner rounds keep the gate')[1])
        self.assertIn(scope.split('round 2 ')[1], worker)
        self.assertIn('starts a new fresh reviewer on the result only when round 1 left a Critical or High fix', workflow)
        for text in (worker, workflow, brief):
            self.assertNotIn('until no Critical, High or Medium finding remains', text)
            self.assertNotIn('only verifies Critical or High fixes', text)
            self.assertNotIn("runs only to verify round 1's Critical or High fixes", text)
        self.assertIn('The final review is due once per release, never per branch', gate)
        self.assertNotIn('re-read at medium effort', workflow)
        brief = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8').split(
            '### The rules in brief')[1].split('### The measurements and the full rules')[0]
        self.assertLess(len(brief), 2500)
        self.assertIn('"Worker cost", its first block "The rules in brief"', read('core/AGENTS.md'))
        self.assertIn('"Worker cost", its block "The rules in brief"',
                      read('overlays/claude-code/files/.claude/hooks/after_compact.txt'))

    def test_plugin_commands_preapprove_only_the_commands_they_need(self):
        # A wildcard after git diff also approves --output=FILE, which overwrites a file.
        # Pin exact read-only forms; send commands must still meet the permission prompt.
        expected = {
            'kit-feedback': ['Bash(gh auth status)', 'Bash(git status)',
                             'Bash(git diff)', 'Bash(git diff --stat)'],
            # Handoff reads the cost script's figure (#278); cross-review delegates Git access to review.sh.
            'handoff': ['Bash(%s scripts/agent_cost.py --latest)' % p for p in ('python', 'python3', 'py -3')],
            'cross-review': ['Bash(./scripts/review.sh:*)'],
        }
        for name, allowed in expected.items():
            with self.subTest(command=name):
                command = (ROOT / ('plugin/commands/%s.md' % name)).read_text(encoding='utf-8')
                tools = re.search(r'(?m)^allowed-tools: (.*)$', command)[1].split(', ')
                self.assertEqual([t for t in tools if t.startswith('Bash(')], allowed)
        command = (ROOT / 'plugin/commands/kit-feedback.md').read_text(encoding='utf-8')
        self.assertIn('the permission prompt is the second gate', command)
        # #230: the command searches the tracker before it drafts, so a duplicate becomes a comment.
        self.assertIn("Then search the kit's issues, open and closed, before drafting anything", command)
        self.assertIn('propose a comment on it', command)
        self.assertIn('It is not pre-approved on purpose', command)
        # #154 (owner decision 57): a project switch, asked at setup and read by the command.
        flat = ' '.join(command.split())
        self.assertIn('read the `kit_feedback:` line of `AGENTS.md`', command)
        # An unknown value or two conflicting lines fall back to asking (gateR review).
        self.assertIn('No line, any other value, or two `kit_feedback:` lines that disagree mean `ask-each-time`', flat)
        self.assertIn('- `standing-approval`: ', command)
        # The prompt shows only the file path and is skipped under bypass or a gh allow rule.
        self.assertNotIn('permission prompt still asks', flat)
        self.assertIn('does not ask at all under `bypassPermissions` or an allow rule for `gh`', flat)
        # Issue batching (owner accepted option B): one checklist issue per area per session.
        self.assertIn('## 1b. Batch, do not trickle', command)
        self.assertIn('`- [ ]` line: the kit file, the symptom, how to repeat it', flat)
        self.assertIn('At most about 10 lines and 6000 characters per issue', flat)
        self.assertIn('A separate issue only for a security problem, a blocker', flat)
        self.assertIn('once per batch, never per finding', flat)
        # kfb review Low: an explicit mid-session request was put off to the session's end, and
        # the permission prompt was called the second gate where standing-approval skips it.
        self.assertIn('A finding the owner hands this command mid-session is filed now, not put off', flat)
        self.assertIn('Under `standing-approval` it may not ask at all (§4)', flat)
        # Both kit-feedback pointers name the standing approval beside the chat yes (decision 57).
        for name in ('core/docs/WORKFLOW.md', 'setup/RESEARCH_PROTOCOL.md'):
            text = ' '.join((ROOT / name).read_text(encoding='utf-8').split())
            self.assertNotIn('without an explicit yes', text, name)
            self.assertIn('`kit_feedback: standing-approval`', text, name)
        interview = (ROOT / 'setup/INTERVIEW.md').read_text(encoding='utf-8')
        phase = interview.split('## Phase 0.5', 1)[1].split('\n## ', 1)[0]
        self.assertIn('`kit_feedback: ask-each-time`', phase)
        self.assertIn('`kit_feedback: standing-approval`', phase)
        yes = phase.split('**If yes:**', 1)[1].split('**If no:**', 1)[0]
        self.assertIn('>   `kit_feedback: ask-each-time`\n', yes)
        self.assertIn('offer them ONCE, at its end, as one batch per area', ' '.join(yes.replace('>', ' ').split()))
        # #278: /usage, the canonical name, and a NOT RUN line instead of an unread figure.
        handoff = ' '.join((ROOT / 'plugin/commands/handoff.md').read_text(encoding='utf-8').split())
        self.assertNotIn('/cost', handoff)
        self.assertIn('`/usage: NOT RUN`', handoff)

    def test_the_mode_command_and_skill_know_every_mode_the_workflow_defines(self):
        # The kit ships the working modes; {{MODEL_ROUTING}} left each project to write its own.
        workflow = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8')
        table = workflow.split('### Working modes, by name')[1].split('####')[0]
        rows = re.findall(r'^\| `([a-z-]+)` \|', table, re.M)
        self.assertEqual(sorted(rows), ['cross', 'saver', 'solo'])
        command = (ROOT / 'plugin/commands/mode.md').read_text(encoding='utf-8')
        skill = (ROOT / 'plugins/myagentkit/skills/myagentkit-mode/SKILL.md').read_text(encoding='utf-8')
        # The command may run its helper unprompted, never any Python code.
        tools = re.search(r'(?m)^allowed-tools: (.*)$', command)[1].split(', ')
        self.assertEqual([t for t in tools if t.startswith('Bash(')],
                         ['Bash(%s scripts/working_mode.py:*)' % p for p in ('python', 'python3', 'py -3')])
        for mode in rows:
            with self.subTest(mode=mode):
                definition = re.split(r'(?m)^#### %s(?![\w-]).*$' % mode, workflow)[1].split('####')[0]
                for field in ('Ends', 'Lessons', 'Effort', 'Workers'):
                    self.assertIn('**%s:**' % field, definition)
                for text in (command, skill):
                    self.assertIn(mode, text)
        # The modes have their English names only (owner, KARARLAR B06 inv3#178).
        for name in ('core/docs/WORKFLOW.md', 'plugin/commands/mode.md', 'setup/INTERVIEW.md',
                     'plugins/myagentkit/skills/myagentkit-mode/SKILL.md'):
            for turkish in ('Tek Model Modu', 'Çapraz Mod', 'Tasarruf Modu', 'Turkish name'):
                self.assertNotIn(turkish, (ROOT / name).read_text(encoding='utf-8'), name)
        self.assertIn('**Working mode:** solo', (ROOT / 'core/docs/STATE.md').read_text(encoding='utf-8'))
        for name in ('core/docs/WORKFLOW.md', 'setup/INTERVIEW.md'):
            self.assertNotIn('{{MODEL_ROUTING}}', (ROOT / name).read_text(encoding='utf-8'))
        handoff = with_kit('HANDOFF')
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
        text = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8').split("### The lead's steps when a branch is ready")[1]
        self.assertIn("The lead never changes its shell directory into a worker's worktree", text)
        self.assertIn('use `git -C <worktree>` for its Git commands', text)
        self.assertIn("The shell stays in the lead's checkout", text)

    def test_incremental_build_briefs_name_both_shared_dependencies(self):
        text = (ROOT / 'core/docs/HANDOFF.md').read_text(encoding='utf-8').split('## The brief')[1].split('4. **Acceptance:**')[0]
        self.assertIn('A task that writes an incremental-build planner quotes `docs/GOTCHAS.md`, "An incremental\n   build misses its always-run inputs"', text)
        gotcha = (ROOT / 'core/docs/GOTCHAS_KIT.md').read_text(encoding='utf-8').split('## An incremental build misses its always-run inputs')[1]
        self.assertIn("always-run steps in every stage's dependency set", gotcha)
        self.assertIn('make the driver script invalidate\nevery stage when it changes', gotcha)
        # Decision 10: ARCHITECTURE.md is read on condition by a worker, always by a reviewer.
        agents = (ROOT / 'core/AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('`docs/ARCHITECTURE.md`: read it when the task crosses a module boundary', agents)
        bridge = (ROOT / 'core/scripts/claude_bridge.py').read_text(encoding='utf-8')
        self.assertIn('REVIEW_DOCS = ("AGENTS.md", "docs/ARCHITECTURE.md", "docs/REVIEW_GATE.md")', bridge)

    def test_readme_ci_platforms_match_the_matrix(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertIn('os: [ubuntu-latest, macos-latest]', workflow)
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('windows:\n    name: windows-latest', workflow)
        self.assertIn('Ubuntu, macOS and native Windows are in CI', readme)
        self.assertIn('developed on native Windows', readme)
        self.assertNotIn('Linux, WSL and macOS are in CI', readme)

    def test_the_ci_template_clones_the_whole_history(self):
        # A depth-1 clone of a pull request holds only GitHub's merge commit, so the gate's
        # Done: history check examined no commit of it (#135).
        workflow = (ROOT / 'core/.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertRegex(workflow, r'uses: actions/checkout@v\d+\n(?:\s*#.*\n)*\s*with:\n\s*fetch-depth: 0\n')
        # The kit's own jobs: with no tag in a depth-1 clone, the ACTION check never ran in CI.
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'uses: actions/checkout@\w+ # v\d+\n(?:\s*#.*\n)*\s*with:\n'
                                        r'\s*fetch-depth: 0\n', workflow)), 2)

    def test_a_missing_shellcheck_is_reported_with_its_install_command(self):
        # The gate's NOT RUN came on every run with no fix, and doctor called the host ready (#155).
        install = 'apt install shellcheck, brew install shellcheck or winget install koalaman.shellcheck'
        gate = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        self.assertRegex(gate, r'NOT RUN \[shellcheck\][^\n]*\n\s*echo " *Install it: ' + re.escape(install))
        doctor = (ROOT / 'core/scripts/doctor.sh').read_text(encoding='utf-8')
        self.assertIn('command -v shellcheck >/dev/null 2>&1 ||\n  echo "NOTE: shellcheck is not installed', doctor)
        self.assertIn(install, doctor)

    def test_every_named_section_exists_in_the_file_named(self):
        # A pointer such as (`docs/WORKFLOW.md`, "Writing a gate") sends an agent to one section
        # instead of the whole file; a renamed heading would send it nowhere.
        pattern = re.compile(r'`((?:docs/)?[A-Z_]+\.md)`,\s+(?:the four\s+)?"([^"]+)"')
        # #159: the kit's own docs cite sections too; a kit doc names a project path (core/) or its own.
        sources = ([ROOT / 'core/AGENTS.md'] + sorted((ROOT / 'core/docs').glob('*.md'))
                   + sorted((ROOT / 'docs').glob('*.md')) + [ROOT / 'docs/research/README.md', ROOT / 'README.md'])
        checked = 0
        for path in sources:
            text = re.sub(r'\s+', ' ', path.read_text(encoding='utf-8'))
            for target, section in pattern.findall(text):
                with self.subTest(source=path.name, target=target, section=section):
                    cited = source(target) if source(target).is_file() else ROOT / target
                    # A heading, or a bold label inside a list (HANDOFF's "**Proof:**").
                    names = headings(cited)
                    self.assertTrue(any(h == section or h.startswith(section + ' ') for h in names)
                                    or '**' + section + ':**' in cited.read_text(encoding='utf-8'),
                                    '%s names "%s" in %s, which has no such heading' % (path.name, section, target))
                    checked += 1
        self.assertGreater(checked, 10)

    def test_documented_plugin_counts_match_the_shipped_directories(self):
        # #159: README named three commands after mode.md shipped, CODEX.md two skills of three.
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        for command in (ROOT / 'plugin/commands').glob('*.md'):
            self.assertIn('`/myagentkit:%s`' % command.stem, readme)
        skills = [d for d in (ROOT / 'plugins/myagentkit/skills').iterdir() if d.is_dir()]
        words = {2: 'two', 3: 'three', 4: 'four', 5: 'five'}
        self.assertIn('The Codex plugin packages %s skills' % words[len(skills)],
                      ' '.join((ROOT / 'docs/CODEX.md').read_text(encoding='utf-8').split()))

    def test_documented_python_commands_name_the_windows_form(self):
        # #160: a bare `python3 scripts/...` opens the Store alias or fails on a python.org
        # Windows install, and a bare `python` is absent on macOS; each doc names both forms.
        docs = ([ROOT / 'README.md', ROOT / 'CONTRIBUTING.md'] + sorted((ROOT / 'docs').glob('*.md'))
                + sorted((ROOT / 'core').rglob('*.md')) + sorted((ROOT / 'setup').glob('*.md')))
        for path in docs:
            text = path.read_text(encoding='utf-8')
            with self.subTest(doc=str(path.relative_to(ROOT))):
                self.assertIsNone(re.search(r'(?<![\w-])python (core/)?scripts/', text))
                if re.search(r'python3 (core/)?scripts/', text):
                    self.assertTrue('`python` on native Windows' in ' '.join(text.split())
                                    or 'native Windows: python instead of python3' in text)

    def test_the_constitution_carries_project_rules_only(self):
        # #112: sub-agents load AGENTS.md and followed the lead's reading order; #131: a release's
        # dogfood rule and kit decision ids shipped into project-owned files; #150: the binding
        # COMMUNICATION.md was in no reading order.
        agents = ' '.join((ROOT / 'core/AGENTS.md').read_text(encoding='utf-8').split())
        head = agents[:agents.index('## What this project is')]
        self.assertIn('skips the reading order', head)
        self.assertIn('leaves `docs/STATE.md` to the lead', head)
        reading = agents[agents.index('## Reading order'):agents.index('## HARD RULES')]
        self.assertIn('`docs/COMMUNICATION.md`', reading)
        communication = (ROOT / 'core/docs/COMMUNICATION.md').read_text(encoding='utf-8')
        for path, text in (('AGENTS.md', agents), ('COMMUNICATION.md', communication)):
            for kit_only in ('dogfood', 'KARARLAR', 'ACCEPTANCE.md', 'Fable 5.1'):
                self.assertNotIn(kit_only, text, '%s carries kit-internal text' % path)

    def test_model_routing_values_and_the_inheritance_rule_live_once(self):
        # #142: rule 1 restated the tier table as "the cheaper model (Sonnet)" while the table
        # said Haiku or Sonnet, and the inheritance rule was copied into four places.
        docs = {name: ' '.join((ROOT / 'core/docs' / name).read_text(encoding='utf-8').split())
                for name in ('WORKFLOW.md', 'WORKFLOW_RATIONALE.md', 'HANDOFF.md', 'HANDOFF_KIT.md')}
        self.assertNotIn('cheaper model (Sonnet)', docs['WORKFLOW.md'])
        self.assertEqual(sum(text.count('omitted sub-agent model') for text in docs.values()), 1)

    def test_the_kits_agents_chains_leave_room_under_codexs_limit(self):
        # #143: Codex silently drops what passes project_doc_max_bytes (32 KiB) of the AGENTS.md
        # chain from the root to the working folder, and the tail holds the STOP list. The kit's
        # own text keeps a quarter of the limit for the project's rules and placeholders.
        root = (ROOT / 'core/AGENTS.md').stat().st_size
        for nested in (ROOT / 'core/docs/AGENTS.md', ROOT / 'overlays/unity/files/unity/AGENTS.md'):
            with self.subTest(chain=str(nested.relative_to(ROOT))):
                self.assertLess(root + nested.stat().st_size, 24 * 1024)

    def test_a_style_plugin_never_replaces_the_test_and_report_rules(self):
        # #140: ponytail injects a "one self-check" test rule and a three-line report cap.
        interview = ' '.join((ROOT / 'setup/INTERVIEW.md').read_text(encoding='utf-8').split())
        self.assertNotIn('was not measured here', interview)
        self.assertIn("the kit's rules win", interview)
        for path in (ROOT / 'core/AGENTS.md', ROOT / 'overlays/claude-code/files/.claude/agents/worker.md'):
            with self.subTest(doc=path.name):
                self.assertIn('never replaces these', ' '.join(path.read_text(encoding='utf-8').split()))

    def test_a_new_projects_research_pass_starts_from_the_kits_reports(self):
        # #157: with no project log, every bootstrap ran a full ecosystem pass.
        protocol = ' '.join((ROOT / 'setup/RESEARCH_PROTOCOL.md').read_text(encoding='utf-8').split())
        self.assertIn("the kit's own reports", protocol)
        self.assertIn('`docs/research/README.md`', protocol)
        self.assertTrue((ROOT / 'docs/research/README.md').is_file())

    def test_the_attack_list_lives_once_and_both_checklists_point_at_it(self):
        # A reviewer attacks the list and a worker checks it before reporting. Two copies drift,
        # and a worker then reports clean against a list the reviewer no longer uses.
        section = 'What a reviewer attacks first'
        self.assertIn(section, headings(ROOT / 'core/docs/REVIEW_GATE.md'))
        pointer = '`docs/REVIEW_GATE.md`, "%s"' % section
        for path in (ROOT / 'core/docs/WORKFLOW.md',
                     ROOT / 'overlays/claude-code/files/.claude/agents/worker.md'):
            with self.subTest(checklist=path.name):
                text = re.sub(r'\s+', ' ', path.read_text(encoding='utf-8'))
                self.assertIn('Before you report', text)
                self.assertIn(pointer, text)
                self.assertFalse('core.checkStat' in text, 'the list is copied, not pointed at')

    def test_the_gotchas_contents_lists_every_entry(self):
        # GOTCHAS_KIT.md too: the project's GOTCHAS.md is not synced, so its Contents never
        # names an entry the kit added after the install.
        for path in (ROOT / 'core/docs/GOTCHAS.md', ROOT / 'core/docs/GOTCHAS_KIT.md'):
            text = path.read_text(encoding='utf-8')
            contents = text[text.index('## Contents'):text.index('---')]
            for heading in headings(path):
                if heading != 'Contents':
                    with self.subTest(path=path.name, heading=heading):
                        self.assertIn(heading, contents)

    def test_review_docs_state_what_the_code_does(self):
        # #229: the skill said authentication fails over and a round makes two attempts.
        sys.path.insert(0, str(ROOT / 'core/scripts'))
        import review_dispatch
        skill = ' '.join((ROOT / 'plugins/myagentkit/skills/myagentkit-review/SKILL.md').read_text(encoding='utf-8').split())
        failover = skill.split('Otherwise only `--allow-fallback`')[1].split('A setup fault never fails over')[0]
        for kind in review_dispatch.UNAVAILABLE:
            self.assertIn('`%s`' % kind, failover)
        self.assertNotIn('authentication', failover)
        self.assertIn('One round makes at most four attempts', skill)
        self.assertNotIn('four attempts maximum for two rounds', skill)
        self.assertNotIn('four calls maximum', (ROOT / 'docs/CODEX.md').read_text(encoding='utf-8'))
        self.assertNotIn('(quota, auth,', (ROOT / 'core/scripts/review.sh').read_text(encoding='utf-8'))
        # #281: no shipped file cites a decision log the kit does not ship, and KARARLAR is explained.
        for path in [*ROOT.glob('core/**/*'), *ROOT.glob('plugins/**/*')]:
            if path.is_file() and path.suffix in ('.md', '.py', '.sh'):
                self.assertNotIn('decisions.md', path.read_text(encoding='utf-8'), path)
        workflow = ' '.join(workflow_rules_and_reasons().split())
        self.assertIn("names an entry of the kit maintainer's decision log, which the kit does not ship", workflow)
        # rsel3: the top tier reviews itself in a fresh session (Invariant), so WORKFLOW never sends
        # a review to "another tier" or "the tier that did not write the change"; the effort rule
        # holds for every required review and is written once, in REVIEW_GATE.
        # rsel4: nor any other doc the kit ships or keeps (reviews are archived evidence).
        for path in [*ROOT.glob('*.md'), *[p for d in ('core', 'plugin', 'plugins', 'overlays', 'setup', 'docs')
                                           for p in (ROOT / d).glob('**/*.md')]]:
            if 'reviews' not in path.relative_to(ROOT).parts:
                text = ' '.join(path.read_text(encoding='utf-8').split())
                self.assertEqual([p for p in ('another tier of the same family', 'the tier that did not write',
                                              "another Claude tier than the author's") if p in text], [], path)
        self.assertNotIn("effort or above, high at most", workflow)
        self.assertIn("Every required review runs at an effort equal to or above the author's, high at most",
                      ' '.join((ROOT / 'core/docs/REVIEW_GATE.md').read_text(encoding='utf-8').split()))

    def test_setup_docs_match_solo_mode_and_the_shipped_files(self):
        read = lambda name: ' '.join((ROOT / name).read_text(encoding='utf-8').split())
        # #227: one Claude CLI is enough; a second CLI serves cross mode only.
        for name in ('core/docs/DEV_SETUP.md', 'overlays/claude-code/README.md'):
            text = read(name)
            self.assertNotIn('needs a second CLI', text, name)
            self.assertNotIn('A SECOND CLI', text, name)
            self.assertIn('cross mode only', text, name)
        # #217: the overlay README names every marker its files carry, and keeps worker.md.
        readme = read('overlays/claude-code/README.md')
        markers = set()
        for path in (ROOT / 'overlays/claude-code/files').rglob('*'):
            if path.is_file():
                markers |= set(re.findall(r'\{\{[A-Z0-9_]+\}\}', path.read_text(encoding='utf-8', errors='replace')))
        self.assertGreater(len(markers), 5)
        for marker in markers:
            self.assertIn(marker, readme)
        self.assertNotIn('delete both files', readme)
        self.assertIn('keep `.claude/agents/worker.md`', readme)
        # #215: the installed Unity doc carries the fragment step and points at no absent README.
        unity = read('overlays/unity/files/docs/UNITY_SETUP.md')
        self.assertIn('Append `docs/kit/unity.gitignore-fragment` to `.gitignore`', unity)
        self.assertNotIn('overlays/unity/README.md', unity)
        self.assertNotIn('skip this section', unity)
        self.assertIn('`docs/UNITY_SETUP.md`', read('setup/INTERVIEW.md'))

    def test_branch_workers_and_the_gate_timing_have_one_rule(self):
        read = lambda name: ' '.join((ROOT / name).read_text(encoding='utf-8').split())
        # #178: a branch or worktree worker writes its note, never STATE.md.
        for name in ('core/docs/HANDOFF.md', 'core/docs/HANDOFF_KIT.md', 'core/docs/AGENTS.md'):
            self.assertIn('docs/worktree-notes/<branch>.md', read(name), name)
        self.assertIn('`git merge --no-commit <branch>`', read('core/docs/WORKFLOW.md'))
        # #220: the timing is written once, in the gate; AGENTS.md no longer says "before commit".
        agents = read('core/AGENTS.md')
        self.assertNotIn('pass the review gate before commit', agents)
        self.assertNotIn('review gate applies before commit', agents)
        self.assertIn('This is the one place the timing is written', read('core/docs/REVIEW_GATE.md'))
        # #286: a commit is a long job because its hooks run the gate.
        self.assertIn('`git commit` and `git merge` are long jobs too', read('core/docs/WORKFLOW.md'))
        self.assertIn('default foreground timeout is 120 seconds',
                      read('overlays/claude-code/files/.claude/agents/worker.md'))

    def test_a_duration_is_agent_time_from_the_projects_measured_rows(self):
        # Owner request 2026-10-21 (leeway: "4-6 weeks" planned, ~27 h actual): a model prices work
        # in human time and has no clock (docs/research/agent-durations.md), so the rule every lead
        # and worker reads points at a fixed table of the project's own measured times.
        read = lambda name: ' '.join((ROOT / name).read_text(encoding='utf-8').split())
        rule = [line for line in read('core/BEHAVIOUR.md').split(' - ') if 'not measured' in line]
        self.assertEqual(len(rule), 1, 'BEHAVIOUR.md needs one duration line')
        for needed in ('agent wall clock', '`docs/WORKFLOW.md`, "Task sizing"', 'person-days',
                       '<!-- author-only -->'):
            self.assertIn(needed, rule[0])
        workflow = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8')
        sizing = workflow.split('## Task sizing', 1)[1].split('\n## ', 1)[0]
        units = ['Worker step, brief to result', 'Review fix round', 'Light review',
                 'Full review', 'Gate run', 'Merge', 'Session start or compaction']
        rows = re.findall(r'^\| ([^|]+?) \| not measured \|$', sizing, re.M)
        self.assertEqual(rows, units, 'the template ships every row "not measured"')
        # The kit's own checkout has no docs/WORKFLOW.md: its rows live in CONTRIBUTING.md, so the
        # kit's times never ship in the template (review r1).
        self.assertIn('(in the kit\'s own checkout, `CONTRIBUTING.md`, "Measured agent times")', rule[0])
        kit = (ROOT / 'CONTRIBUTING.md').read_text(encoding='utf-8').split('## Measured agent times', 1)[1]
        self.assertEqual(re.findall(r'^\| ([^|]+?) \| [^|]+ \|$', kit.split('\n## ', 1)[0], re.M)[1:], units)
        flat = ' '.join(sizing.split())
        for needed in ('overwrites', 'never appended', 'docs/research/agent-durations.md',
                       'implicit', 'waits'):
            self.assertIn(needed, flat)
        self.assertIn('how long in agent time (`docs/WORKFLOW.md`, "Task sizing")',
                      read('core/docs/COMMUNICATION.md'))

    def test_the_research_index_lists_every_report(self):
        # The reports are the kit's bibliography (CONTRIBUTING.md): one missing from the index
        # is a source nobody finds, so every report needs a row that links it.
        folder = ROOT / 'docs/research'
        index = (folder / 'README.md').read_text(encoding='utf-8')
        reports = sorted(p.name for p in folder.glob('*.md') if p.name != 'README.md')
        self.assertTrue(reports)
        for name in reports:
            with self.subTest(report=name):
                self.assertIn('](%s)' % name, index)

    def test_the_workflow_keeps_the_rules_and_the_kit_owns_the_rationale(self):
        # #296: rules and reasons in one 1,741-line project-owned file gave seven conflicts in one
        # three-way merge. The reasons live in a kit-owned file the sync replaces, by heading.
        path = ROOT / 'core/docs/WORKFLOW_RATIONALE.md'
        rationale = path.read_text(encoding='utf-8')
        workflow = (ROOT / 'core/docs/WORKFLOW.md').read_text(encoding='utf-8')
        self.assertTrue(rationale.startswith('<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->\n'))
        # A sync copies the file unfilled, and the project's gate fails on a placeholder.
        self.assertIsNone(re.search(r'\{\{[A-Z0-9_]+\}\}', rationale))
        self.assertNotIn("## Where the constitution's rules come from", workflow)
        # wfsplit review: a rule or an owner decision in the kit-owned file is overwritten by the
        # next sync, so the worker-cost rules 1-9 stay whole in WORKFLOW.md and only reasons move.
        reasons = rationale.split("## Where the constitution's rules come from")[0]
        for n, rule in enumerate(("A worker's cache must outlive its waits", "Gate findings go to the author's side",
                                  'One small task per worker.', 'The lead does not poll either.',
                                  'Mechanical work goes to the cheaper model', 'Parallel workers only for independent modules',
                                  'Worker reports are short', 'The lead session is compacted or handed over',
                                  'A worker runs the cheapest check'), 1):
            with self.subTest(rule=n):
                self.assertIn('\n%d. **%s' % (n, rule), workflow)
                self.assertNotIn(rule, reasons)
        for decision in ("owner's choice", 'owner decision', 'KARARLAR B', '{{OWNER_NAME}}'):
            self.assertNotIn(decision, reasons)
        whys = list(re.finditer(r'^Why: docs/WORKFLOW_RATIONALE\.md, "([^"]+)"\.$', workflow, re.M))
        self.assertTrue(whys)
        for why in whys:
            with self.subTest(section=why[1]):
                self.assertIn(why[1], headings(path))
                # The pointer ends the section of the same name.
                before = workflow[:why.start()].rstrip('\n')
                section = re.findall(r'^#{2,4} (.+)$', before, re.M)[-1]
                self.assertEqual(section, why[1])
                self.assertRegex(workflow[why.end():], r'^\n*(#|\Z)')
        # The rationale has no heading of its own: a reader finds the why under the rule's name.
        self.assertEqual([h for h in headings(path) if h not in headings(ROOT / 'core/docs/WORKFLOW.md')],
                         ["Where the constitution's rules come from"])

    def test_the_reference_docs_keep_project_lines_and_the_kit_owns_the_rest(self):
        # #94: generic text in a project-owned file reached a project only by a hand merge. In
        # the on-demand reference docs it moves to a kit-owned <NAME>_KIT.md; the project file
        # keeps every placeholder, owner decision and quoted heading (owner decision 2026-10-22,
        # docsowned question 1). The tool-loaded and owner-centred docs stay whole.
        header = '<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->\n'
        self.assertTrue((ROOT / 'core/docs/USAGE.md').read_text(encoding='utf-8').startswith(header))
        for name in KIT_SIBLINGS:
            with self.subTest(doc=name):
                project = (ROOT / 'core/docs' / (name + '.md')).read_text(encoding='utf-8')
                path = ROOT / 'core/docs' / (name + '_KIT.md')
                kit = path.read_text(encoding='utf-8')
                self.assertTrue(kit.startswith(header))
                # A sync overwrites the file, so an edit there is lost: the project's rule goes in
                # its own file, which wins (lead, 2026-10-22).
                self.assertIn('Do not edit it: a project that needs a different rule writes it in `docs/%s.md`, the '
                              'project-owned file, and the project file wins over this one.' % name, ' '.join(kit.split()))
                self.assertIn('A project that needs a different rule writes it here, and this file wins over '
                              '`docs/%s_KIT.md`.' % name, ' '.join(project.split()))
                self.assertIsNone(re.search(r'\{\{[A-Z0-9_]+\}\}', kit))
                body = kit.split('\n## ', 1)[1]
                for decision in ("owner's choice", 'owner decision', 'KARARLAR', '{{OWNER_NAME}}'):
                    self.assertNotIn(decision, body)
                pointers = list(re.finditer(r'^Kit rules: docs/%s_KIT\.md, "([^"]+)"\.$' % name, project, re.M))
                self.assertTrue(pointers)
                for pointer in pointers:
                    self.assertIn(pointer[1], headings(path))
                    # The pointer ends the project's section of the same name (CHANGELOG, UPDATING.md).
                    self.assertEqual(re.findall(r'^#{2,4} (.+)$', project[:pointer.start()], re.M)[-1], pointer[1])
                    self.assertRegex(project[pointer.end():], r'^\n*(#|\Z)')
                # A quote of a heading still finds it in the file it names.
                self.assertEqual([h for h in headings(path) if h not in headings(ROOT / 'core/docs' / (name + '.md'))], [])
        for name in ('REVIEW_GATE', 'COMMUNICATION', 'GLOSSARY', 'STRONG_REVIEW', 'AGENTS'):
            self.assertFalse((ROOT / 'core/docs' / (name + '_KIT.md')).exists(), name)
        self.assertFalse((ROOT / 'core/AGENTS_KIT.md').exists())

    def test_the_interview_placeholder_scan_finds_what_the_gate_fails_on(self):
        # #271: the interview's `grep -rn` listed the exempt files, ignored .gitignore and
        # missed a marker with a digit, so the agent worked from another list than the gate's.
        import os, subprocess, tempfile
        gate = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        pattern, exempt = re.search(r"^hits=\$\(scan_grep '([^']+)' \| grep -Ev '([^']+)'", gate, re.M).groups()
        phase = (ROOT / 'setup/INTERVIEW.md').read_text(encoding='utf-8').split('## Phase 4', 1)[1]
        command = re.search(r'`((?:git )?grep [^`]*\{[^`]*)`', phase)[1]
        files = {'a.md': b'{{ONE}}\n', 'b.md': b'x\n{{TWO_2}}\n', 'build/c.md': b'{{THREE}}\n',
                 'setup/x.md': b'{{FOUR}}\n', 'MODULE_AGENTS_TEMPLATE.md': b'{{FIVE}}\n',
                 'mod/MODULE_AGENTS_TEMPLATE.md': b'{{SIX}}\n', 'bin.dat': b'{{SEVEN}}\0\n',
                 'lower.md': b'{{lower}}\n', '.gitignore': b'build/\n'}
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in files.items():
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / name).write_bytes(body)
            git = lambda *args: subprocess.run(['git', *args], cwd=tmp, check=True, capture_output=True,
                                               env=env).stdout.decode()
            git('init', '-q')
            git('add', 'a.md', 'setup', 'MODULE_AGENTS_TEMPLATE.md', 'bin.dat', '.gitignore')
            expected = []   # the gate: grep -I over tracked and untracked unignored files, minus exempt
            for name in git('ls-files', '--cached', '--others', '--exclude-standard').split():
                body = (Path(tmp) / name).read_bytes()
                for number, line in enumerate(body.decode().splitlines(), 1):
                    hit = '%s:%d:%s' % (name, number, line)
                    if b'\0' not in body and re.search(pattern, line) and not re.search(exempt, hit):
                        expected.append(hit)
            found = subprocess.run(['sh', '-c', command], cwd=tmp, capture_output=True, encoding='utf-8', env=env)
        self.assertEqual(sorted(expected), ['a.md:1:{{ONE}}', 'b.md:2:{{TWO_2}}', 'mod/MODULE_AGENTS_TEMPLATE.md:1:{{SIX}}'])
        self.assertEqual(sorted(found.stdout.splitlines()), sorted(expected), found.stderr)
        self.assertIn(pattern, command)


if __name__ == '__main__':
    unittest.main()

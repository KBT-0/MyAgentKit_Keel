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
        for needed in ('`Accept` / `Accept with Manual Checks` / `Reject`',
                       'a disproved finding counts\nonly after the reviewer has checked it against the code',
                       'a deferred one stays open under\nManual checks, so it rules out a plain Accept',
                       '**A Reject is not closed by its fixes.**'):
            self.assertIn(needed, gate)
        running = (ROOT / 'core/docs/REVIEW_RUNNING.md').read_text()
        for heading in CALLER_HEADINGS:
            self.assertIn(heading, running)


class SectionPointerTests(unittest.TestCase):
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

    def test_the_gotchas_contents_lists_every_entry(self):
        text = (ROOT / 'core/docs/GOTCHAS.md').read_text()
        contents = text[text.index('## Contents'):text.index('---')]
        for heading in headings(ROOT / 'core/docs/GOTCHAS.md'):
            if heading != 'Contents':
                self.assertIn(heading, contents)


if __name__ == '__main__':
    unittest.main()

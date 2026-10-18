"""Self-checks of tests/test_check_gate_windows.py's own clean-up helpers (terminate, descendants,
kill_tree), kept apart from that suite: no change to a shipped kit file can fail them, so they
are no gate coverage and do not count toward its minimum (#263). The kit's own part of the
clean-up, agent_process's job kill, is proven there by test_kill_tree_stops_a_child_started_after_its_snapshot.
"""
import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_check_gate_windows as harness  # noqa: E402
from test_check_gate_windows import windows_only  # noqa: E402


class HarnessSelfChecks(unittest.TestCase):
    @windows_only
    def test_kill_tree_spares_a_pid_replaced_between_snapshot_and_open(self):
        proc = Mock(pid=1, _handle=101, _kit_job=99)
        events, closed = [], []

        def query(handle, info, out, size, returned):
            self.assertEqual(handle, 102)
            out._obj.InheritedFromUniqueProcessId = 900
            return 0

        kernel32 = Mock()
        kernel32.TerminateJobObject.side_effect = lambda job, code: events.append('job')
        with patch.object(harness, 'children', side_effect=lambda pid: [(2, 'python.exe')] if pid == 1 else []), \
                patch.object(harness, 'KERNEL32', Mock(OpenProcess=Mock(return_value=102),
                                                    GetProcessId=Mock(return_value=1))), \
                patch.object(harness, 'NTDLL', Mock(NtQueryInformationProcess=Mock(side_effect=query)), create=True), \
                patch.object(harness, 'created', side_effect={101: 100, 102: 200}.get), \
                patch.object(harness, 'terminate', events.append), patch.object(harness, 'close_handle', closed.append), \
                patch('agent_process._win', return_value={'kernel32': kernel32}):
            harness.kill_tree(proc)
        self.assertEqual(events, ['job'], 'a newer replacement with another parent must never be killed')
        self.assertEqual(closed, [102])

    @windows_only
    def test_terminate_requires_a_signalled_wait_even_after_a_successful_kill(self):
        for killed in (0, 1):
            for waited in (0x102, 0xffffffff):
                with self.subTest(killed=killed, waited=waited), \
                        patch.object(harness, 'KERNEL32',
                                     Mock(TerminateProcess=Mock(return_value=killed),
                                          WaitForSingleObject=Mock(return_value=waited))), \
                        patch.object(ctypes, 'get_last_error', return_value=5), self.assertRaises(OSError):
                    harness.terminate(101)
            with patch.object(harness, 'KERNEL32',
                              Mock(TerminateProcess=Mock(return_value=killed),
                                   WaitForSingleObject=Mock(return_value=0))):
                harness.terminate(101)  # already exited processes can refuse TerminateProcess

    @windows_only
    def test_kill_tree_stops_parents_first_and_spares_a_child_of_an_earlier_pid(self):
        # TerminateJobObject alone stopped the build (4, 5) before the lock holder (2), which
        # then cleared its token. 3 names 2 as its parent but is older than 2: its parent was
        # an earlier process with that pid. It is never killed; the job is stopped last.
        events = []
        proc = Mock(pid=1, _handle=1, _kit_job=99)
        tree = {1: [(2, 'python.exe')], 2: [(4, 'sh.exe'), (3, 'unrelated.exe')], 4: [(5, 'sh.exe')]}
        born = {1: 100, 2: 110, 3: 50, 4: 120, 5: 130}
        kernel32 = Mock()
        kernel32.TerminateJobObject.side_effect = lambda job, code: events.append('job')
        with patch.object(harness, 'children', lambda pid: tree.get(pid, [])), \
                patch.object(harness, 'KERNEL32', Mock(OpenProcess=lambda access, inherit, pid: pid,
                                                    GetProcessId=lambda handle: handle)), \
                patch.object(harness, 'parent_pid', side_effect={2: 1, 3: 2, 4: 2, 5: 4}.get), \
                patch.object(harness, 'created', born.get), \
                patch.object(harness, 'terminate', events.append), patch.object(harness, 'close_handle'), \
                patch('agent_process._win', return_value={'kernel32': kernel32}):
            harness.kill_tree(proc)
        self.assertEqual(events, [2, 4, 5, 'job'])


if __name__ == '__main__':
    unittest.main()

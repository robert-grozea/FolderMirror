"""Static regression tests for GUI daemon startup monitoring."""

import unittest
from pathlib import Path


class DaemonStartupSourceTests(unittest.TestCase):
    def test_startup_checks_child_process_and_pid(self):
        source = (Path(__file__).resolve().parents[1] / "fm_gui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def _check_daemon_start(self, process, attempts_left=12):", source)
        self.assertIn("process.poll()", source)
        self.assertIn("pid == process.pid and is_folder_mirror_daemon(pid)", source)

    def test_startup_failure_displays_recent_log(self):
        source = (Path(__file__).resolve().parents[1] / "fm_gui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Daemon failed to start", source)
        self.assertIn("Recent log entries:", source)

    def test_child_is_started_unbuffered_for_immediate_logging(self):
        source = (Path(__file__).resolve().parents[1] / "fm_gui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('[sys.executable, "-u", script, "--daemon"]', source)


    def test_daemon_launcher_targets_application_entry_point(self):
        source = (Path(__file__).resolve().parents[1] / "fm_gui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'Path(__file__).resolve().with_name("folder_mirror.py")',
            source,
        )
        self.assertNotIn(
            'script = str(Path(__file__).resolve())',
            source,
        )


if __name__ == "__main__":
    unittest.main()

    def test_gui_refuses_to_stop_unverified_process(self):
        source = (Path(__file__).resolve().parents[1] / "fm_gui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("if not is_folder_mirror_daemon(pid):", source)
        self.assertIn("no process was terminated", source)

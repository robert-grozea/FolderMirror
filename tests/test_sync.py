"""Unit tests for recursive mirror behavior."""

import logging
import os
import tempfile
import unittest
from pathlib import Path

from fm_sync import sync_pair


class SyncPairTests(unittest.TestCase):
    """Use temporary folders so tests never modify real user data."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.source = root / "source"
        self.destination = root / "destination"
        self.source.mkdir()
        self.destination.mkdir()

        # A quiet logger keeps test output readable.
        self.logger = logging.getLogger(f"folder_mirror_test_{id(self)}")
        self.logger.handlers.clear()
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False

    def test_copies_new_file_and_creates_nested_directories(self):
        nested = self.source / "one" / "two"
        nested.mkdir(parents=True)
        (nested / "hello.txt").write_text("hello", encoding="utf-8")

        result = sync_pair(self.source, self.destination, self.logger)

        self.assertEqual(result, (1, 0, 0))
        self.assertEqual(
            (self.destination / "one" / "two" / "hello.txt").read_text(encoding="utf-8"),
            "hello",
        )

    def test_creates_empty_nested_directories(self):
        (self.source / "empty" / "nested").mkdir(parents=True)

        sync_pair(self.source, self.destination, self.logger)

        self.assertTrue((self.destination / "empty" / "nested").is_dir())

    def test_updates_changed_file(self):
        source_file = self.source / "data.txt"
        destination_file = self.destination / "data.txt"
        source_file.write_text("new content", encoding="utf-8")
        destination_file.write_text("old content", encoding="utf-8")

        # Ensure the modification time differs even on coarse-resolution filesystems.
        old_time = destination_file.stat().st_mtime_ns
        os.utime(source_file, ns=(old_time + 3_000_000_000, old_time + 3_000_000_000))

        result = sync_pair(self.source, self.destination, self.logger)

        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(destination_file.read_text(encoding="utf-8"), "new content")

    def test_deletes_destination_only_file(self):
        (self.destination / "obsolete.txt").write_text("remove me", encoding="utf-8")

        result = sync_pair(self.source, self.destination, self.logger)

        self.assertEqual(result, (0, 0, 1))
        self.assertFalse((self.destination / "obsolete.txt").exists())

    def test_deletes_destination_only_directory_and_contents(self):
        obsolete = self.destination / "old" / "nested"
        obsolete.mkdir(parents=True)
        (obsolete / "old.txt").write_text("remove me", encoding="utf-8")

        sync_pair(self.source, self.destination, self.logger)

        self.assertFalse((self.destination / "old").exists())

    def test_second_sync_is_idempotent(self):
        (self.source / "same.txt").write_text("same", encoding="utf-8")

        first_result = sync_pair(self.source, self.destination, self.logger)
        second_result = sync_pair(self.source, self.destination, self.logger)

        self.assertEqual(first_result, (1, 0, 0))
        self.assertEqual(second_result, (0, 0, 0))

    def test_replaces_destination_directory_with_source_file(self):
        (self.source / "item").write_text("file", encoding="utf-8")
        (self.destination / "item" / "child").mkdir(parents=True)
        (self.destination / "item" / "child" / "old.txt").write_text("old", encoding="utf-8")

        result = sync_pair(self.source, self.destination, self.logger)

        # The obsolete child file is counted as deleted before the directory is replaced.
        self.assertEqual(result, (1, 0, 1))
        self.assertTrue((self.destination / "item").is_file())
        self.assertEqual((self.destination / "item").read_text(encoding="utf-8"), "file")

    def test_replaces_destination_file_with_source_directory(self):
        (self.source / "item" / "nested").mkdir(parents=True)
        (self.destination / "item").write_text("old file", encoding="utf-8")

        sync_pair(self.source, self.destination, self.logger)

        self.assertTrue((self.destination / "item" / "nested").is_dir())

    def test_rejects_overlapping_paths(self):
        nested_destination = self.source / "inside"
        with self.assertRaisesRegex(RuntimeError, "Unsafe source/destination overlap"):
            sync_pair(self.source, nested_destination, self.logger)


if __name__ == "__main__":
    unittest.main()


class RunSyncTests(unittest.TestCase):
    """Regression tests for the public run_sync entry point."""

    def test_run_sync_validates_pairs_and_runs_them(self):
        from unittest.mock import patch
        from fm_sync import run_sync

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            (source / "hello.txt").write_text("hello", encoding="utf-8")

            logger = logging.getLogger(f"folder_mirror_run_sync_{id(self)}")
            logger.handlers.clear()
            logger.addHandler(logging.NullHandler())
            logger.propagate = False

            with patch("fm_sync.setup_logging", return_value=logger):
                result = run_sync({
                    "pairs": [{"source": str(source), "destination": str(destination)}]
                })

            self.assertEqual(result, (1, 0, 0))
            self.assertEqual(
                (destination / "hello.txt").read_text(encoding="utf-8"),
                "hello",
            )

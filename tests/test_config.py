"""Unit tests for configuration persistence and folder-pair validation."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_config


class ConfigPersistenceTests(unittest.TestCase):
    """Verify config defaults and JSON read/write behavior."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.app_dir = Path(self.temp_dir.name) / "FolderMirror"
        self.config_file = self.app_dir / "config.json"
        self.patches = (
            patch.object(app_config, "APP_DIR", self.app_dir),
            patch.object(app_config, "CONFIG_FILE", self.config_file),
        )
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_missing_config_returns_defaults(self):
        config = app_config.load_config()
        self.assertEqual(config["pairs"], [])
        self.assertEqual(config["interval_seconds"], app_config.DEFAULT_INTERVAL)
        self.assertEqual(config["deletion_mode"], "recycle_bin" if app_config.os.name == "nt" else "permanent")

    def test_save_and_load_round_trip(self):
        expected = {
            "pairs": [{"source": "C:/Source", "destination": "D:/Mirror"}],
            "interval_seconds": 120,
            "deletion_mode": "recycle_bin" if app_config.os.name == "nt" else "permanent",
        }
        app_config.save_config(expected)
        self.assertTrue(self.config_file.is_file())
        self.assertEqual(app_config.load_config(), expected)

    def test_load_adds_missing_default_keys(self):
        self.app_dir.mkdir(parents=True)
        self.config_file.write_text(json.dumps({"pairs": []}), encoding="utf-8")
        config = app_config.load_config()
        self.assertEqual(config["interval_seconds"], app_config.DEFAULT_INTERVAL)

    def test_invalid_json_raises_clear_error(self):
        self.app_dir.mkdir(parents=True)
        self.config_file.write_text("{not valid JSON", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Could not read configuration"):
            app_config.load_config()


class FolderPairValidationTests(unittest.TestCase):
    """Check path safety rules without touching user folders."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.destination = self.root / "destination"

    def test_valid_pair_is_returned_as_absolute_paths(self):
        result = app_config.validate_pairs([{
            "source": str(self.source),
            "destination": str(self.destination),
        }])
        self.assertEqual(len(result), 1)
        self.assertEqual(Path(result[0]["source"]), app_config.canonical(self.source))
        self.assertEqual(Path(result[0]["destination"]), app_config.canonical(self.destination))

    def test_missing_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source folder does not exist"):
            app_config.validate_pairs([{
                "source": str(self.root / "missing"),
                "destination": str(self.destination),
            }])

    def test_same_source_and_destination_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot be the same folder"):
            app_config.validate_pairs([{
                "source": str(self.source),
                "destination": str(self.source),
            }])

    def test_nested_source_and_destination_is_rejected(self):
        nested_destination = self.source / "mirror"
        with self.assertRaisesRegex(ValueError, "cannot be the same folder"):
            app_config.validate_pairs([{
                "source": str(self.source),
                "destination": str(nested_destination),
            }])

    def test_overlapping_destinations_are_rejected(self):
        second_source = self.root / "source2"
        second_source.mkdir()
        nested_destination = self.destination / "nested"
        with self.assertRaisesRegex(ValueError, "Two destination folders overlap"):
            app_config.validate_pairs([
                {"source": str(self.source), "destination": str(self.destination)},
                {"source": str(second_source), "destination": str(nested_destination)},
            ])


    def test_symlink_alias_cannot_hide_source_destination_overlap(self):
        alias = self.root / "source-alias"
        try:
            alias.symlink_to(self.source, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlinks are unavailable on this system")
        with self.assertRaisesRegex(ValueError, "cannot be the same folder"):
            app_config.validate_pairs([{
                "source": str(self.source),
                "destination": str(alias / "nested"),
            }])

    def test_destination_overlapping_another_source_is_rejected(self):
        second_source = self.root / "source2"
        second_source.mkdir()
        with self.assertRaisesRegex(ValueError, "overlaps a configured source"):
            app_config.validate_pairs([
                {"source": str(self.source), "destination": str(self.destination)},
                {"source": str(second_source), "destination": str(self.source / "nested")},
            ])


if __name__ == "__main__":
    unittest.main()

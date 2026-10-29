"""
Comprehensive unit tests for SafeCleaner and CleanResult.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.backup_manager import BackupManager
from confclean.core.cleaner import CleanResult, SafeCleaner
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ScanItem


class TestSafeCleaner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="confclean_cleaner_test_")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.safety = SafetyEngine(config_dir=self.test_dir)
        self.backup_mgr = BackupManager(backup_dir=self.backup_dir)
        self.cleaner = SafeCleaner(safety=self.safety, backup_mgr=self.backup_mgr)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_result_formatting(self):
        res = CleanResult()
        res.total_reclaimed_bytes = 1024 * 1024 * 25  # 25 MB
        self.assertEqual(res.formatted_reclaimed_size, "25.0 MB")

    def test_clean_empty_items(self):
        res, msg = self.cleaner.clean_items([])
        self.assertIn("No items provided", msg)
        self.assertEqual(len(res.deleted_items), 0)

    def test_clean_all_protected_blocked(self):
        item = ScanItem(
            path="/home/user/.config/dconf",
            name="dconf",
            category="config",
            is_directory=True,
            size_bytes=1000,
            file_count=1,
            last_modified=0,
            status="PROTECTED",
            reason="Core system component",
        )
        res, msg = self.cleaner.clean_items([item])
        self.assertIn("All selected items are protected", msg)
        self.assertEqual(len(res.blocked_items), 1)
        self.assertEqual(len(res.deleted_items), 0)

    def test_dry_run_simulation_preserves_files(self):
        orphan_dir = os.path.join(self.test_dir, "orphan_dir")
        os.makedirs(orphan_dir, exist_ok=True)
        orphan_file = os.path.join(orphan_dir, "file.txt")
        with open(orphan_file, "w") as f:
            f.write("content")

        item = ScanItem(
            path=orphan_dir,
            name="orphan_dir",
            category="config",
            is_directory=True,
            size_bytes=7,
            file_count=1,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Orphan test",
        )

        res, msg = self.cleaner.clean_items([item], create_backup=False, dry_run=True)
        self.assertTrue(res.is_dry_run)
        self.assertEqual(len(res.deleted_items), 1)
        self.assertIn("Dry run complete", msg)
        # Disk verification: Directory and file MUST still exist!
        self.assertTrue(os.path.exists(orphan_dir))
        self.assertTrue(os.path.exists(orphan_file))

    def test_clean_items_dry_run_by_default(self):
        orphan_dir = os.path.join(self.test_dir, "orphan_default_dry")
        os.makedirs(orphan_dir, exist_ok=True)
        orphan_file = os.path.join(orphan_dir, "file.txt")
        with open(orphan_file, "w") as f:
            f.write("content")

        item = ScanItem(
            path=orphan_dir,
            name="orphan_default_dry",
            category="config",
            is_directory=True,
            size_bytes=7,
            file_count=1,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Orphan test",
        )

        res, msg = self.cleaner.clean_items([item])  # dry_run=True by default!
        self.assertTrue(res.is_dry_run)
        self.assertEqual(len(res.deleted_items), 1)
        self.assertTrue(os.path.exists(orphan_dir))
        self.assertTrue(os.path.exists(orphan_file))

    def test_backup_failure_aborts_deletion(self):
        orphan_dir = os.path.join(self.test_dir, "orphan_abort")
        os.makedirs(orphan_dir, exist_ok=True)

        item = ScanItem(
            path=orphan_dir,
            name="orphan_abort",
            category="config",
            is_directory=True,
            size_bytes=10,
            file_count=1,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Orphan test",
        )

        # Mock backup failure
        with patch.object(self.backup_mgr, "create_backup", return_value=(False, None, None, "Disk error")):
            res, msg = self.cleaner.clean_items([item], create_backup=True, dry_run=False)

        self.assertIn("ABORTED", msg)
        self.assertEqual(len(res.deleted_items), 0)
        # Folder must still exist!
        self.assertTrue(os.path.exists(orphan_dir))

    def test_actual_clean_deletes_files_and_directories(self):
        # Target directory
        orphan_dir = os.path.join(self.test_dir, "real_orphan_dir")
        os.makedirs(orphan_dir, exist_ok=True)
        with open(os.path.join(orphan_dir, "f.txt"), "w") as f:
            f.write("test")

        # Target standalone file
        orphan_file = os.path.join(self.test_dir, "standalone.conf")
        with open(orphan_file, "w") as f:
            f.write("conf")

        item_dir = ScanItem(
            path=orphan_dir,
            name="real_orphan_dir",
            category="config",
            is_directory=True,
            size_bytes=4,
            file_count=1,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Orphan dir",
        )

        item_file = ScanItem(
            path=orphan_file,
            name="standalone.conf",
            category="config",
            is_directory=False,
            size_bytes=4,
            file_count=1,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Orphan file",
        )

        progress_calls = []

        def callback(msg, cur, tot):
            progress_calls.append((msg, cur, tot))

        res, msg = self.cleaner.clean_items(
            [item_dir, item_file],
            create_backup=True,
            dry_run=False,
            progress_callback=callback,
        )

        self.assertEqual(len(res.deleted_items), 2)
        self.assertFalse(os.path.exists(orphan_dir))
        self.assertFalse(os.path.exists(orphan_file))
        self.assertIsNotNone(res.backup_archive_path)
        self.assertTrue(os.path.exists(res.backup_archive_path))
        self.assertGreater(len(progress_calls), 0)


if __name__ == "__main__":
    unittest.main()

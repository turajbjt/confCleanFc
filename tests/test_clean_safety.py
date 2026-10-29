"""
Unit tests for SafeCleaner, SafetyEngine, and ConfigScanner.
"""

import os
import shutil
import tempfile
import unittest

from confclean.core.backup_manager import BackupManager
from confclean.core.cleaner import SafeCleaner
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ConfigScanner, ScanItem


class TestCleanAndSafety(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="confclean_safety_")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.safety = SafetyEngine(config_dir=self.test_dir)
        self.backup_mgr = BackupManager(backup_dir=self.backup_dir)
        self.cleaner = SafeCleaner(safety=self.safety, backup_mgr=self.backup_mgr)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_safelist_blocks_protected_files(self):
        # Protected items
        self.assertTrue(self.safety.is_safelisted("/home/user/.config/dconf")[0])
        self.assertTrue(self.safety.is_safelisted("/home/user/.config/pipewire")[0])
        self.assertTrue(self.safety.is_safelisted("/home/user/.config/pulse")[0])
        self.assertTrue(self.safety.is_safelisted("/home/user/.ssh")[0])
        self.assertTrue(self.safety.is_safelisted("/home/user/.gnupg")[0])
        self.assertTrue(self.safety.is_safelisted("/boot")[0])
        self.assertTrue(self.safety.is_safelisted("/etc/shadow")[0])

        # Non-protected items
        self.assertFalse(self.safety.is_safelisted("/home/user/.config/cura-lulzbot")[0])
        self.assertFalse(self.safety.is_safelisted("/home/user/.config/asunder")[0])

    def test_cleaner_refuses_to_delete_protected_item(self):
        # Create a fake dconf folder in test_dir
        fake_dconf = os.path.join(self.test_dir, "dconf")
        os.makedirs(fake_dconf, exist_ok=True)

        item = ScanItem(
            path=fake_dconf,
            name="dconf",
            category="config",
            is_directory=True,
            size_bytes=100,
            file_count=1,
            last_modified=0,
            status="PROTECTED",
            reason="Core system component",
        )

        res, summary = self.cleaner.clean_items([item], create_backup=False, dry_run=False)
        # Should be blocked and folder still exists
        self.assertEqual(len(res.blocked_items), 1)
        self.assertEqual(len(res.deleted_items), 0)
        self.assertTrue(os.path.exists(fake_dconf))

    def test_cleaner_dry_run_does_not_delete(self):
        fake_orphan = os.path.join(self.test_dir, "old_uninstalled_tool")
        os.makedirs(fake_orphan, exist_ok=True)
        with open(os.path.join(fake_orphan, "state.txt"), "w") as f:
            f.write("test")

        item = ScanItem(
            path=fake_orphan,
            name="old_uninstalled_tool",
            category="config",
            is_directory=True,
            size_bytes=4,
            file_count=1,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Orphan test",
        )

        res, summary = self.cleaner.clean_items([item], create_backup=False, dry_run=True)
        self.assertTrue(res.is_dry_run)
        self.assertEqual(len(res.deleted_items), 1)
        # File must STILL exist because of dry run!
        self.assertTrue(os.path.exists(fake_orphan))

    def test_cleaner_actual_clean_with_backup(self):
        fake_orphan = os.path.join(self.test_dir, "old_uninstalled_tool2")
        os.makedirs(fake_orphan, exist_ok=True)
        with open(os.path.join(fake_orphan, "state.txt"), "w") as f:
            f.write("test2")

        item = ScanItem(
            path=fake_orphan,
            name="old_uninstalled_tool2",
            category="config",
            is_directory=True,
            size_bytes=5,
            file_count=1,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Orphan test",
        )

        res, summary = self.cleaner.clean_items([item], create_backup=True, dry_run=False)
        self.assertEqual(len(res.deleted_items), 1)
        self.assertFalse(os.path.exists(fake_orphan))
        self.assertIsNotNone(res.backup_archive_path)
        self.assertTrue(os.path.exists(res.backup_archive_path))


if __name__ == "__main__":
    unittest.main()

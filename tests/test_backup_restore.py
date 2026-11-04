"""
Comprehensive unit tests for BackupManager, RestoreManager, and BackupMetadata.
"""

import json
import os
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.backup_manager import BackupManager, BackupMetadata
from confclean.core.restore_manager import RestoreManager, RestoreResult
from confclean.core.scanner import ScanItem, get_path_stats


class TestBackupAndRestore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="confclean_backup_test_")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.fake_config = os.path.join(self.test_dir, "fake_app_config")
        os.makedirs(self.fake_config, exist_ok=True)

        self.file1 = os.path.join(self.fake_config, "settings.json")
        with open(self.file1, "w") as f:
            f.write('{"theme": "dark", "version": 2}')

        self.file2 = os.path.join(self.fake_config, "cache.db")
        with open(self.file2, "wb") as f:
            f.write(b"SAMPLE_BINARY_CACHE_DATA_12345")

        self.backup_mgr = BackupManager(backup_dir=self.backup_dir)
        self.restore_mgr = RestoreManager()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_backup_metadata_formatting(self):
        meta = BackupMetadata(
            backup_id="test_b",
            archive_path="/p",
            log_path="/l",
            created_at="2026-10-29",
            user="test",
            item_count=5,
            total_size_bytes=1024 * 1024 * 12,  # 12 MB
        )
        self.assertEqual(meta.formatted_size, "12.0 MB")

    def test_create_backup_empty_items(self):
        ok, arch, log, msg = self.backup_mgr.create_backup([])
        self.assertFalse(ok)
        self.assertIn("No items selected", msg)

    def test_create_backup_insufficient_disk_space(self):
        item = ScanItem(
            path=self.fake_config,
            name="fake_app_config",
            category="config",
            is_directory=True,
            size_bytes=1000,
            file_count=2,
            last_modified=0,
            status="CONFIRMED_ORPHAN",
            reason="Test",
        )
        # Mock disk_usage to return 0 free bytes
        with patch("shutil.disk_usage", return_value=MagicMock(free=10)):
            ok, arch, log, msg = self.backup_mgr.create_backup([item])
            self.assertFalse(ok)
            self.assertIn("Insufficient free disk space", msg)

    def test_backup_and_restore_full_cycle(self):
        size, count, mtime = get_path_stats(self.fake_config)
        item = ScanItem(
            path=self.fake_config,
            name="fake_app_config",
            category="config",
            is_directory=True,
            size_bytes=size,
            file_count=count,
            last_modified=mtime,
            status="CONFIRMED_ORPHAN",
            reason="Test orphan application",
        )

        # 1. Create backup
        ok, arch_path, log_p, msg = self.backup_mgr.create_backup([item])
        self.assertTrue(ok)
        self.assertIsNotNone(arch_path)
        self.assertTrue(os.path.exists(arch_path))
        self.assertTrue(os.path.exists(log_p))
        manifest_p = arch_path[:-7] + ".manifest.json"
        self.assertTrue(os.path.exists(manifest_p))

        # Check manifest directly inside archive / companion
        items_inside = self.restore_mgr.get_archive_items(arch_path)
        self.assertEqual(len(items_inside), 1)
        self.assertEqual(items_inside[0]["name"], "fake_app_config")

        # Test fallback when companion manifest is removed from disk
        os.remove(manifest_p)
        self.assertFalse(os.path.exists(manifest_p))
        # list_backups should extract from archive and restore companion cache
        backups_fallback = self.backup_mgr.list_backups()
        self.assertEqual(len(backups_fallback), 1)
        self.assertEqual(backups_fallback[0].item_count, 1)
        self.assertTrue(os.path.exists(manifest_p))

        # 2. Check list_backups
        backups = self.backup_mgr.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].item_count, 1)

        # 3. Simulate deletion
        shutil.rmtree(self.fake_config)
        self.assertFalse(os.path.exists(self.fake_config))

        # 4. Restore whole archive
        res, summary = self.restore_mgr.restore(arch_path)
        self.assertTrue(res.success)
        self.assertTrue(os.path.exists(self.fake_config))
        self.assertTrue(os.path.exists(self.file1))
        self.assertTrue(os.path.exists(self.file2))

        # Verify content integrity
        with open(self.file1, "r") as f:
            self.assertEqual(f.read(), '{"theme": "dark", "version": 2}')

    def test_selective_restore_and_destination_override(self):
        size, count, mtime = get_path_stats(self.fake_config)
        item = ScanItem(
            path=self.fake_config,
            name="fake_app_config",
            category="config",
            is_directory=True,
            size_bytes=size,
            file_count=count,
            last_modified=mtime,
            status="CONFIRMED_ORPHAN",
            reason="Test orphan",
        )

        ok, arch_path, log_p, msg = self.backup_mgr.create_backup([item])
        self.assertTrue(ok)

        items = self.restore_mgr.get_archive_items(arch_path)
        item_id = items[0]["id"]

        custom_dest = os.path.join(self.test_dir, "custom_restored")
        res, summary = self.restore_mgr.restore(
            arch_path,
            selected_item_ids=[item_id],
            destination_override=custom_dest,
        )

        self.assertTrue(res.success)
        expected_path = os.path.join(custom_dest, "fake_app_config", "settings.json")
        self.assertTrue(os.path.exists(expected_path))

    def test_restore_conflict_skip_vs_overwrite(self):
        size, count, mtime = get_path_stats(self.fake_config)
        item = ScanItem(
            path=self.fake_config,
            name="fake_app_config",
            category="config",
            is_directory=True,
            size_bytes=size,
            file_count=count,
            last_modified=mtime,
            status="CONFIRMED_ORPHAN",
            reason="Test",
        )
        ok, arch_path, log_p, msg = self.backup_mgr.create_backup([item])
        self.assertTrue(ok)

        # Modify existing file
        with open(self.file1, "w") as f:
            f.write("MODIFIED_CONTENT")

        # 1. Restore with overwrite=False -> should skip
        res_skip, _ = self.restore_mgr.restore(arch_path, overwrite_existing=False)
        self.assertIn(self.fake_config, res_skip.skipped_items)
        with open(self.file1, "r") as f:
            self.assertEqual(f.read(), "MODIFIED_CONTENT")

        # 2. Restore with overwrite=True -> should replace
        res_overwrite, _ = self.restore_mgr.restore(arch_path, overwrite_existing=True)
        self.assertIn(self.fake_config, res_overwrite.restored_items)
        with open(self.file1, "r") as f:
            self.assertEqual(f.read(), '{"theme": "dark", "version": 2}')

    def test_restore_symlinks(self):
        symlink_target = os.path.join(self.fake_config, "settings.json")
        symlink_path = os.path.join(self.fake_config, "settings_symlink.json")
        os.symlink(symlink_target, symlink_path)

        size, count, mtime = get_path_stats(self.fake_config)
        item = ScanItem(
            path=self.fake_config,
            name="fake_app_config",
            category="config",
            is_directory=True,
            size_bytes=size,
            file_count=count,
            last_modified=mtime,
            status="CONFIRMED_ORPHAN",
            reason="Test symlink",
        )
        ok, arch_path, log_p, msg = self.backup_mgr.create_backup([item])
        self.assertTrue(ok)

        # Delete fake_config
        shutil.rmtree(self.fake_config)

        # Restore
        res, _ = self.restore_mgr.restore(arch_path)
        self.assertTrue(res.success)
        self.assertTrue(os.path.islink(symlink_path))

    def test_delete_backup(self):
        size, count, mtime = get_path_stats(self.fake_config)
        item = ScanItem(
            path=self.fake_config,
            name="fake_app_config",
            category="config",
            is_directory=True,
            size_bytes=size,
            file_count=count,
            last_modified=mtime,
            status="CONFIRMED_ORPHAN",
            reason="Test",
        )
        ok, arch_path, log_p, msg = self.backup_mgr.create_backup([item])
        self.assertTrue(ok)

        backups = self.backup_mgr.list_backups()
        self.assertEqual(len(backups), 1)
        b_id = backups[0].backup_id

        self.assertTrue(self.backup_mgr.delete_backup(b_id))
        self.assertEqual(len(self.backup_mgr.list_backups()), 0)
        self.assertFalse(os.path.exists(arch_path))
        self.assertFalse(os.path.exists(log_p))
        manifest_p = arch_path[:-7] + ".manifest.json"
        self.assertFalse(os.path.exists(manifest_p))

    def test_backup_with_unreadable_file_permission_denied(self):
        # Create unreadable file inside fake_config (simulating root 0600 file like sesman_passwd)
        unreadable_file = os.path.join(self.fake_config, "root_locked.key")
        with open(unreadable_file, "w") as f:
            f.write("SUPER_SECRET_ROOT_DATA")
        os.chmod(unreadable_file, 0o000)

        size, count, mtime = get_path_stats(self.fake_config)
        item = ScanItem(
            path=self.fake_config,
            name="fake_app_config",
            category="config",
            is_directory=True,
            size_bytes=size,
            file_count=count,
            last_modified=mtime,
            status="CONFIRMED_ORPHAN",
            reason="Test with unreadable file",
        )

        ok, arch_path, log_p, msg = self.backup_mgr.create_backup([item])
        # Must succeed and not abort the entire backup!
        self.assertTrue(ok)
        self.assertIn("warning", msg.lower())
        self.assertTrue(os.path.isfile(arch_path))

        # Restore permissions so tearDown can clean up test_dir
        os.chmod(unreadable_file, 0o644)


if __name__ == "__main__":
    unittest.main()

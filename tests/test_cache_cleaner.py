"""
Comprehensive unit tests for CacheCleaner and CacheCategory.
"""

import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.cache_cleaner import CacheCategory, CacheCleaner
from confclean.core.safelist import SafetyEngine


class TestCacheCleaner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="confclean_cache_test_")
        self.safety = SafetyEngine(config_dir=self.test_dir)
        self.cleaner = CacheCleaner(safety=self.safety)
        self.cleaner.is_root = False

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cache_category_properties(self):
        cat = CacheCategory(
            category_id="thumb",
            name="Thumbnails",
            description="Cached images",
            requires_root=False,
            paths=["/path/to/thumb"],
            size_bytes=1024 * 1024 * 5,  # 5 MB
            item_count=10,
        )
        self.assertEqual(cat.formatted_size, "5.0 MB")
        self.assertTrue(cat.is_selected)

    def test_scan_categories_finds_data(self):
        fake_home = os.path.join(self.test_dir, "home")
        thumb_dir = os.path.join(fake_home, ".cache", "thumbnails")
        trash_dir = os.path.join(fake_home, ".local", "share", "Trash")
        os.makedirs(thumb_dir, exist_ok=True)
        os.makedirs(trash_dir, exist_ok=True)

        with open(os.path.join(thumb_dir, "thumb1.png"), "wb") as f:
            f.write(b"PNG_DATA_12345")
        with open(os.path.join(trash_dir, "deleted.txt"), "wb") as f:
            f.write(b"TRASH_DATA_67890")

        with patch("os.path.expanduser", return_value=fake_home):
            categories = self.cleaner.scan_categories()

        self.assertGreater(len(categories), 0)
        thumb_cat = next((c for c in categories if c.category_id == "thumbnails"), None)
        self.assertIsNotNone(thumb_cat)
        self.assertEqual(thumb_cat.size_bytes, 14)
        self.assertEqual(thumb_cat.item_count, 1)

    def test_evaluate_old_tmp_files(self):
        fake_tmp = os.path.join(self.test_dir, "tmp")
        os.makedirs(fake_tmp, exist_ok=True)

        # Old file (> 7 days)
        old_file = os.path.join(fake_tmp, "old_file.tmp")
        with open(old_file, "w") as f:
            f.write("old data")
        past_time = time.time() - (10 * 86400)
        os.utime(old_file, (past_time, past_time))

        # Recent file (< 7 days)
        recent_file = os.path.join(fake_tmp, "recent_file.tmp")
        with open(recent_file, "w") as f:
            f.write("recent data")

        # Systemd private folder (should be skipped)
        sys_priv = os.path.join(fake_tmp, "systemd-private-1234")
        os.makedirs(sys_priv, exist_ok=True)

        cat = self.cleaner._evaluate_old_tmp_category(
            "tmp_test", "Tmp", "Desc", True, tmp_dirs=[fake_tmp]
        )

        # Only old_file should be matched
        self.assertEqual(cat.item_count, 1)
        self.assertIn(old_file, cat.paths)
        self.assertNotIn(recent_file, cat.paths)

    def test_clean_category_refusal_when_root_required(self):
        self.cleaner.is_root = False
        cat = CacheCategory(
            category_id="dnf_cache",
            name="DNF Cache",
            description="System package cache",
            requires_root=True,
            paths=["/var/cache/dnf"],
            size_bytes=1000,
        )
        b, c, msg = self.cleaner.clean_category(cat)
        self.assertEqual(b, 0)
        self.assertEqual(c, 0)
        self.assertIn("Root privileges required", msg)

    def test_clean_category_empties_directory_contents(self):
        cache_folder = os.path.join(self.test_dir, "user_cache")
        os.makedirs(cache_folder, exist_ok=True)
        sub_folder = os.path.join(cache_folder, "sub")
        os.makedirs(sub_folder, exist_ok=True)

        file1 = os.path.join(cache_folder, "file1.cache")
        file2 = os.path.join(sub_folder, "file2.cache")
        with open(file1, "w") as f:
            f.write("data1")
        with open(file2, "w") as f:
            f.write("data2")

        cat = CacheCategory(
            category_id="user_cache",
            name="User Cache",
            description="User cache",
            requires_root=False,
            paths=[cache_folder],
            size_bytes=10,
            item_count=2,
        )

        b, c, msg = self.cleaner.clean_category(cat, dry_run=False)
        self.assertGreater(b, 0)
        self.assertEqual(c, 2)
        # Parent folder should still exist, but contents emptied!
        self.assertTrue(os.path.exists(cache_folder))
        self.assertFalse(os.path.exists(file1))
        self.assertFalse(os.path.exists(sub_folder))

    def test_clean_category_dry_run_by_default(self):
        cache_folder = os.path.join(self.test_dir, "dry_run_cache")
        os.makedirs(cache_folder, exist_ok=True)
        file1 = os.path.join(cache_folder, "test.dat")
        with open(file1, "w") as f:
            f.write("content")

        cat = CacheCategory(
            category_id="user_cache",
            name="User Cache",
            description="User cache",
            requires_root=False,
            paths=[cache_folder],
            size_bytes=7,
            item_count=1,
        )

        b, c, msg = self.cleaner.clean_category(cat)  # Defaults to dry_run=True
        self.assertEqual(b, 7)
        self.assertEqual(c, 1)
        self.assertIn("[DRY RUN]", msg)
        self.assertTrue(os.path.exists(file1))  # File was NOT deleted

    @patch("subprocess.run")
    def test_clean_special_dnf_and_journal_commands(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        self.cleaner.is_root = True

        # Test dnf clean all
        cat_dnf = CacheCategory(
            category_id="dnf_cache",
            name="DNF Cache",
            description="Package cache",
            requires_root=True,
            paths=["/var/cache/dnf"],
            size_bytes=5000,
        )
        b, c, msg = self.cleaner.clean_category(cat_dnf, dry_run=False)
        self.assertEqual(b, 5000)
        self.assertIn("dnf clean all", msg)

        # Test journalctl vacuum
        cat_j = CacheCategory(
            category_id="systemd_journal",
            name="Journal",
            description="Journal logs",
            requires_root=True,
            paths=["/var/log/journal"],
            size_bytes=8000,
        )
        b, c, msg = self.cleaner.clean_category(cat_j, dry_run=False)
        self.assertEqual(b, 8000)
        self.assertIn("Systemd journals", msg)


if __name__ == "__main__":
    unittest.main()

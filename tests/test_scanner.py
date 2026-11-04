"""
Comprehensive unit tests for ConfigScanner, ScanItem, and path stats.
"""

import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.detector import SystemDetector
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ConfigScanner, ScanItem, get_path_stats, get_rpm_diff


class TestConfigScanner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="confclean_scanner_test_")
        self.config_dir = os.path.join(self.test_dir, ".config")
        self.local_share = os.path.join(self.test_dir, ".local", "share")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.local_share, exist_ok=True)

        self.safety = SafetyEngine(config_dir=self.test_dir)
        self.detector = SystemDetector(refresh_on_init=False)
        self.detector.rpm_packages = {"installed_tool"}
        self.scanner = ConfigScanner(detector=self.detector, safety=self.safety)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_scan_item_formatting_and_dict(self):
        # Bytes
        item_b = ScanItem("/p", "n", "cat", False, 500, 1, 0.0, "STATUS", "reason")
        self.assertEqual(item_b.formatted_size, "500 B")
        self.assertEqual(item_b.formatted_date, "Unknown")

        # KB
        item_kb = ScanItem("/p", "n", "cat", False, 2048, 1, 1000000000.0, "STATUS", "reason")
        self.assertEqual(item_kb.formatted_size, "2.0 KB")
        self.assertNotEqual(item_kb.formatted_date, "Unknown")

        # MB
        item_mb = ScanItem("/p", "n", "cat", False, 10 * 1024 * 1024, 1, 0.0, "STATUS", "reason")
        self.assertEqual(item_mb.formatted_size, "10.0 MB")

        # GB
        item_gb = ScanItem("/p", "n", "cat", False, 5 * 1024 * 1024 * 1024, 1, 0.0, "STATUS", "reason")
        self.assertEqual(item_gb.formatted_size, "5.0 GB")

        # to_dict
        d = item_b.to_dict()
        self.assertEqual(d["name"], "n")
        self.assertEqual(d["size_bytes"], 500)
        self.assertEqual(d["status"], "STATUS")

    def test_get_path_stats(self):
        # Non-existent
        s, c, m = get_path_stats("/nonexistent/path/12345")
        self.assertEqual(s, 0)
        self.assertEqual(c, 0)

        # Single file
        test_file = os.path.join(self.test_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Hello World!")
        s, c, m = get_path_stats(test_file)
        self.assertEqual(s, 12)
        self.assertEqual(c, 1)
        self.assertGreater(m, 0)

        # Directory with files and nested folders
        nested_dir = os.path.join(self.test_dir, "nested")
        os.makedirs(os.path.join(nested_dir, "sub"), exist_ok=True)
        with open(os.path.join(nested_dir, "f1.bin"), "wb") as f:
            f.write(b"1234")
        with open(os.path.join(nested_dir, "sub", "f2.bin"), "wb") as f:
            f.write(b"5678")

        s, c, m = get_path_stats(nested_dir)
        self.assertEqual(s, 8)
        self.assertEqual(c, 2)

    def test_analyze_protected_item(self):
        dconf_path = os.path.join(self.config_dir, "dconf")
        os.makedirs(dconf_path, exist_ok=True)

        item = self.scanner._analyze_item(dconf_path, "dconf", "config")
        self.assertIsNotNone(item)
        self.assertEqual(item.status, "PROTECTED")
        self.assertEqual(item.suggested_action, "keep")
        self.assertFalse(item.is_selected)

    def test_analyze_system_etc_rpmsave_and_rpmnew(self):
        rpmsave_path = os.path.join(self.test_dir, "app.conf.rpmsave")
        with open(rpmsave_path, "w") as f:
            f.write("conf")
        item_save = self.scanner._analyze_item(rpmsave_path, "app.conf.rpmsave", "system_etc")
        self.assertEqual(item_save.status, "CONFIRMED_ORPHAN")
        self.assertEqual(item_save.suggested_action, "clean")
        self.assertTrue(item_save.is_selected)

        rpmnew_path = os.path.join(self.test_dir, "app.conf.rpmnew")
        with open(rpmnew_path, "w") as f:
            f.write("conf new")
        item_new = self.scanner._analyze_item(rpmnew_path, "app.conf.rpmnew", "system_etc")
        self.assertEqual(item_new.status, "PROBABLE_ORPHAN")
        self.assertEqual(item_new.suggested_action, "review")
        self.assertFalse(item_new.is_selected)

    def test_analyze_active_app(self):
        active_path = os.path.join(self.config_dir, "installed_tool")
        os.makedirs(active_path, exist_ok=True)

        item = self.scanner._analyze_item(active_path, "installed_tool", "config")
        self.assertIsNotNone(item)
        self.assertEqual(item.status, "ACTIVE_APP")
        self.assertEqual(item.suggested_action, "keep")
        self.assertFalse(item.is_selected)

    def test_analyze_confirmed_orphan_inactive_long_ago(self):
        old_orphan_path = os.path.join(self.config_dir, "old_dead_app")
        os.makedirs(old_orphan_path, exist_ok=True)
        # Set mtime to 60 days ago
        old_time = time.time() - (60 * 86400)
        os.utime(old_orphan_path, (old_time, old_time))

        item = self.scanner._analyze_item(old_orphan_path, "old_dead_app", "config")
        self.assertIsNotNone(item)
        self.assertEqual(item.status, "CONFIRMED_ORPHAN")
        self.assertEqual(item.suggested_action, "clean")
        self.assertTrue(item.is_selected)

    def test_analyze_probable_orphan_modified_recently(self):
        recent_orphan_path = os.path.join(self.config_dir, "recent_dead_app")
        os.makedirs(recent_orphan_path, exist_ok=True)
        # Set mtime to 2 days ago
        recent_time = time.time() - (2 * 86400)
        os.utime(recent_orphan_path, (recent_time, recent_time))

        item = self.scanner._analyze_item(recent_orphan_path, "recent_dead_app", "config")
        self.assertIsNotNone(item)
        self.assertEqual(item.status, "PROBABLE_ORPHAN")
        self.assertEqual(item.suggested_action, "review")
        self.assertFalse(item.is_selected)

    def test_scan_all_orchestration_and_progress(self):
        # Create mock targets
        os.makedirs(os.path.join(self.config_dir, "item1"), exist_ok=True)
        os.makedirs(os.path.join(self.config_dir, "item2"), exist_ok=True)

        progress_calls = []

        def on_progress(msg, cur, tot):
            progress_calls.append((msg, cur, tot))

        with patch("os.path.expanduser", return_value=self.test_dir):
            items = self.scanner.scan_all(
                include_user_configs=True,
                include_flatpaks=False,
                include_dotfiles=False,
                include_system_etc=False,
                progress_callback=on_progress,
            )

        self.assertGreaterEqual(len(items), 2)
        self.assertGreaterEqual(len(progress_calls), 2)

    def test_get_rpm_diff_matching_and_differences(self):
        active_path = os.path.join(self.test_dir, "myconfig.conf")
        rpm_path = os.path.join(self.test_dir, "myconfig.conf.rpmnew")

        with open(active_path, "w", encoding="utf-8") as f:
            f.write("setting=old\n")
        with open(rpm_path, "w", encoding="utf-8") as f:
            f.write("setting=new\n")

        p1, p2, diff = get_rpm_diff(rpm_path)
        self.assertEqual(p1, active_path)
        self.assertEqual(p2, rpm_path)
        self.assertIn("-setting=old", diff)
        self.assertIn("+setting=new", diff)

    def test_get_rpm_diff_missing_active(self):
        rpm_path = os.path.join(self.test_dir, "nonexistent.conf.rpmsave")
        with open(rpm_path, "w", encoding="utf-8") as f:
            f.write("backup=true\n")

        p1, p2, msg = get_rpm_diff(rpm_path)
        self.assertIsNone(p1)
        self.assertIn("does not exist on disk", msg)

    def test_analyze_broken_desktop_file(self):
        desktop_dir = os.path.join(self.test_dir, ".local", "share", "applications")
        os.makedirs(desktop_dir, exist_ok=True)
        desktop_file = os.path.join(desktop_dir, "ghostapp.desktop")

        with open(desktop_file, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nName=Ghost App\nExec=nonexistent_binary_xyz --arg\nType=Application\n")

        with patch("shutil.which", return_value=None):
            item = self.scanner._analyze_item(desktop_file, "ghostapp.desktop", "broken_desktop")

        self.assertIsNotNone(item)
        self.assertEqual(item.status, "CONFIRMED_ORPHAN")
        self.assertEqual(item.category, "broken_desktop")
        self.assertIn("nonexistent_binary_xyz", item.reason)
        self.assertTrue(item.is_selected)

    def test_analyze_active_desktop_file(self):
        desktop_dir = os.path.join(self.test_dir, ".local", "share", "applications")
        os.makedirs(desktop_dir, exist_ok=True)
        desktop_file = os.path.join(desktop_dir, "goodapp.desktop")

        with open(desktop_file, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nName=Good App\nExec=good_binary\nType=Application\n")

        with patch("shutil.which", return_value="/usr/bin/good_binary"):
            item = self.scanner._analyze_item(desktop_file, "goodapp.desktop", "broken_desktop")

        self.assertIsNotNone(item)
        self.assertEqual(item.status, "ACTIVE_APP")
        self.assertFalse(item.is_selected)

    def test_scan_broken_symlinks(self):
        # 1. Broken symlink (target missing)
        broken_target = os.path.join(self.config_dir, "nonexistent_target.txt")
        broken_link = os.path.join(self.config_dir, "broken_tool.lnk")
        os.symlink(broken_target, broken_link)

        # 2. Valid symlink (target exists)
        valid_target = os.path.join(self.config_dir, "real_file.txt")
        with open(valid_target, "w") as f:
            f.write("hello")
        valid_link = os.path.join(self.config_dir, "valid_tool.lnk")
        os.symlink(valid_target, valid_link)

        # 3. Protected symlink (matches dconf* in safelist)
        protected_link = os.path.join(self.config_dir, "dconf_backup.lnk")
        os.symlink(broken_target, protected_link)

        items = self.scanner.scan_broken_symlinks(search_dirs=[self.config_dir])
        item_paths = {it.path: it for it in items}

        self.assertIn(broken_link, item_paths)
        broken_item = item_paths[broken_link]
        self.assertEqual(broken_item.category, "broken_symlink")
        self.assertEqual(broken_item.status, "CONFIRMED_ORPHAN")
        self.assertTrue(broken_item.is_selected)
        self.assertEqual(broken_item.suggested_action, "clean")
        self.assertIn("Broken symlink pointing to non-existent target", broken_item.reason)
        self.assertIn("nonexistent_target.txt", broken_item.reason)

        # Valid link should not be reported as an orphan
        self.assertNotIn(valid_link, item_paths)

        # Protected link should be recognized and kept safe
        self.assertIn(protected_link, item_paths)
        protected_item = item_paths[protected_link]
        self.assertEqual(protected_item.status, "PROTECTED")
        self.assertFalse(protected_item.is_selected)
        self.assertEqual(protected_item.suggested_action, "keep")

    def test_scan_stale_temp_symlink(self):
        # Create a temporary file and a symlink pointing into /tmp/
        temp_target = "/tmp/confclean_test_temp_socket"
        with open(temp_target, "w") as f:
            f.write("sock")
        try:
            temp_link = os.path.join(self.config_dir, "temp_service.sock")
            os.symlink(temp_target, temp_link)

            items = self.scanner.scan_broken_symlinks(search_dirs=[self.config_dir])
            item_paths = {it.path: it for it in items}

            self.assertIn(temp_link, item_paths)
            item = item_paths[temp_link]
            self.assertEqual(item.category, "broken_symlink")
            self.assertEqual(item.status, "PROBABLE_ORPHAN")
            self.assertFalse(item.is_selected)
            self.assertEqual(item.suggested_action, "review")
            self.assertIn("pointing to temporary directory", item.reason)
        finally:
            if os.path.exists(temp_target):
                os.remove(temp_target)


if __name__ == "__main__":
    unittest.main()

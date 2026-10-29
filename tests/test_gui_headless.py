"""
Headless unit tests for PyQt6 GUI components, tabs, and asynchronous workers.
Runs in offscreen platform mode.
"""

import os
import sys

# Force offscreen QPA platform for headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# Ensure QApplication is initialized for offscreen tests
app = QApplication.instance()
if app is None:
    app = QApplication(["-platform", "offscreen"])

from confclean.core.app_resetter import AppResetProfile, AppResetter
from confclean.core.backup_manager import BackupManager, BackupMetadata
from confclean.core.cache_cleaner import CacheCategory, CacheCleaner
from confclean.core.cleaner import CleanResult, SafeCleaner
from confclean.core.detector import SystemDetector
from confclean.core.logger import AuditLogger
from confclean.core.package_manager import PackageManager, PackageSuggestion
from confclean.core.restore_manager import RestoreManager, RestoreResult
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ConfigScanner, ScanItem
from confclean.gui.app import MainWindow
from confclean.gui.tab_app_reset import AppResetTab
from confclean.gui.tab_cache import CacheTab
from confclean.gui.tab_logs import LogsTab
from confclean.gui.tab_packages import PackageTab
from confclean.gui.tab_restore import RestoreTab
from confclean.gui.tab_scanner import ScannerTab
from confclean.gui.tab_settings import SettingsTab
from confclean.gui.workers import (
    AppResetWorker,
    CacheCleanWorker,
    CleanWorker,
    PackageScanWorker,
    RestoreWorker,
    ScanWorker,
)


class TestGUIHeadless(unittest.TestCase):
    def setUp(self):
        # Patch QMessageBox dialogs to avoid blocking headless unit tests
        self.patch_info = patch("PyQt6.QtWidgets.QMessageBox.information")
        self.patch_warn = patch("PyQt6.QtWidgets.QMessageBox.warning")
        self.patch_crit = patch("PyQt6.QtWidgets.QMessageBox.critical")
        self.patch_quest = patch("PyQt6.QtWidgets.QMessageBox.question")
        self.mock_info = self.patch_info.start()
        self.mock_warn = self.patch_warn.start()
        self.mock_crit = self.patch_crit.start()
        self.mock_quest = self.patch_quest.start()

        self.mock_safety = MagicMock(spec=SafetyEngine)
        self.mock_safety.user_whitelist = ["protected_custom"]
        self.mock_safety.is_safelisted.return_value = (False, "")

        self.mock_detector = MagicMock(spec=SystemDetector)
        self.mock_backup_mgr = MagicMock(spec=BackupManager)
        self.mock_backup_mgr.backup_dir = "/tmp/backups"
        self.mock_restore_mgr = MagicMock(spec=RestoreManager)
        self.mock_cleaner = MagicMock(spec=SafeCleaner)
        self.mock_scanner = MagicMock(spec=ConfigScanner)
        self.mock_cache = MagicMock(spec=CacheCleaner)
        self.mock_cache.is_root = False
        self.mock_pkg = MagicMock(spec=PackageManager)
        self.mock_resetter = MagicMock(spec=AppResetter)
        self.mock_logger = MagicMock(spec=AuditLogger)
        self.mock_logger.in_memory_records = []
        self.mock_logger.get_recent_logs.return_value = [
            {"timestamp": "2026-10-29 10:00:00", "level": "INFO", "message": "Initialized"}
        ]

    def tearDown(self):
        self.patch_info.stop()
        self.patch_warn.stop()
        self.patch_crit.stop()
        self.patch_quest.stop()

    def test_workers_execution(self):
        # 1. ScanWorker
        self.mock_scanner.scan_all.return_value = []
        scan_w = ScanWorker(self.mock_scanner)
        scan_w.run()

        # 2. CleanWorker
        res = CleanResult()
        self.mock_cleaner.clean_items.return_value = (res, "Done")
        clean_w = CleanWorker(self.mock_cleaner, [], False, True)
        clean_w.run()

        # 3. PackageScanWorker
        self.mock_pkg.scan_all_suggestions.return_value = []
        pkg_w = PackageScanWorker(self.mock_pkg)
        pkg_w.run()

        # 4. CacheCleanWorker
        cat = CacheCategory("id", "name", "desc", False, [])
        self.mock_cache.clean_category.return_value = (100, 1, "Cleaned")
        cache_w = CacheCleanWorker(self.mock_cache, cat)
        cache_w.run()

        # 5. AppResetWorker
        prof = AppResetProfile("id", "name", "desc", [])
        self.mock_resetter.reset_app.return_value = (True, "/b.tar.gz", "Reset")
        reset_w = AppResetWorker(self.mock_resetter, prof)
        reset_w.run()

        # 6. RestoreWorker
        res_r = RestoreResult()
        self.mock_restore_mgr.restore.return_value = (res_r, "Restored")
        rest_w = RestoreWorker(self.mock_restore_mgr, "/b.tar.gz")
        rest_w.run()

    def test_scanner_tab_ui_and_filtering(self):
        tab = ScannerTab(self.mock_scanner, self.mock_cleaner, self.mock_safety)

        # Mock scanned items
        i1 = ScanItem("/p1", "asunder", "config", True, 1000, 1, 10.0, "CONFIRMED_ORPHAN", "Orphan", is_selected=True)
        i2 = ScanItem("/p2", "cura-lulzbot", "config", True, 2000, 1, 10.0, "PROBABLE_ORPHAN", "Probable", is_selected=False)
        i3 = ScanItem("/p3", "firefox", "config", True, 3000, 1, 10.0, "ACTIVE_APP", "Active", is_selected=False)
        i4 = ScanItem("/p4", "dconf", "config", True, 4000, 1, 10.0, "PROTECTED", "Protected", is_selected=False)

        tab.scanned_items = [i1, i2, i3, i4]
        tab._populate_tree()

        self.assertEqual(tab.tree.topLevelItemCount(), 4)

        # Check selection buttons
        tab._select_all()
        self.assertTrue(i1.is_selected)
        self.assertTrue(i2.is_selected)
        self.assertTrue(i3.is_selected)
        self.assertFalse(i4.is_selected)  # Protected item cannot be selected!

        tab._select_none()
        self.assertFalse(i1.is_selected)

        tab._select_orphans_only()
        self.assertTrue(i1.is_selected)
        self.assertFalse(i2.is_selected)

        # Filter by search text
        tab.search_input.setText("asunder")
        tab._apply_filters()
        self.assertFalse(tab.tree.topLevelItem(0).isHidden())
        self.assertTrue(tab.tree.topLevelItem(1).isHidden())

        # Filter by dropdown (Confirmed Orphans Only = index 1)
        tab.search_input.clear()
        tab.status_filter.setCurrentIndex(1)
        tab._apply_filters()
        self.assertFalse(tab.tree.topLevelItem(0).isHidden())
        self.assertTrue(tab.tree.topLevelItem(2).isHidden())

    def test_cache_tab_ui(self):
        cat1 = CacheCategory("thumb", "Thumbnails", "Thumb cache", False, ["/p"], size_bytes=5000)
        self.mock_cache.scan_categories.return_value = [cat1]

        tab = CacheTab(self.mock_cache)
        tab.scan_caches()

        self.assertEqual(tab.table.rowCount(), 1)
        self.assertIn("Thumbnails", tab.table.item(0, 1).text())
        self.assertIn("Total Detectable Cache", tab.lbl_total_cache.text())

    def test_package_tab_ui(self):
        s1 = PackageSuggestion("orphan-pkg", "1.0", "1.fc44", "x86_64", 1000, "Summary", "unneeded_dep", "Reason", is_protected=False, is_selected=True)
        s2 = PackageSuggestion("kernel", "7.2.13", "200.fc44", "x86_64", 5000, "Kernel", "old_kernel", "Running", is_protected=True, is_selected=False)

        tab = PackageTab(self.mock_pkg)
        tab.suggestions = [s1, s2]
        tab._populate_table()

        self.assertEqual(tab.table.rowCount(), 2)
        # s1 checkbox enabled, s2 checkbox disabled
        chk1 = tab.table.item(0, 0)
        chk2 = tab.table.item(1, 0)
        self.assertTrue(chk1.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        self.assertFalse(chk2.flags() & Qt.ItemFlag.ItemIsUserCheckable)

    def test_app_reset_tab_ui(self):
        prof = AppResetProfile("firefox", "Mozilla Firefox", "Browser", ["/home/user/.mozilla/firefox"], size_bytes=50000, file_count=10, is_installed=True)
        self.mock_resetter.discover_reset_profiles.return_value = [prof]

        tab = AppResetTab(self.mock_resetter)
        tab.load_profiles()

        self.assertEqual(tab.list_widget.count(), 1)
        self.assertIn("Mozilla Firefox", tab.lbl_app_name.text())
        self.assertIn("/home/user/.mozilla/firefox", tab.txt_paths.toPlainText())
        self.assertTrue(tab.btn_reset.isEnabled())

    def test_restore_tab_ui(self):
        meta = BackupMetadata("backup_1", "/backups/b1.tar.gz", "/backups/b1.log", "2026-10-29", "user", 2, 4000)
        self.mock_backup_mgr.list_backups.return_value = [meta]
        self.mock_restore_mgr.get_archive_items.return_value = [
            {"id": "item_0001", "name": "fake_app", "original_path": "/home/user/.config/fake_app", "formatted_size": "4 KB", "reason": "Orphan"}
        ]

        tab = RestoreTab(self.mock_backup_mgr, self.mock_restore_mgr)
        tab.load_backups()

        self.assertEqual(tab.backup_list.count(), 1)
        self.assertIn("backup_1", tab.lbl_backup_info.text())
        self.assertEqual(tab.tree_items.topLevelItemCount(), 1)
        self.assertTrue(tab.btn_restore_selected.isEnabled())
        self.assertTrue(tab.btn_restore_all.isEnabled())

    def test_logs_tab_ui(self):
        tab = LogsTab(self.mock_logger)
        self.assertEqual(tab.table.rowCount(), 1)

        # Trigger event listener
        tab._on_log_event("2026-10-29 10:01:00", "WARNING", "Something warned")
        self.assertEqual(tab.table.rowCount(), 2)

    def test_settings_tab_ui(self):
        tab = SettingsTab(self.mock_safety)
        self.assertEqual(tab.whitelist_list.count(), 1)
        self.assertEqual(tab.whitelist_list.item(0).text(), "protected_custom")

        # Test add input
        tab.txt_whitelist_input.setText("new_item")
        tab._add_to_whitelist()
        self.mock_safety.add_user_whitelist.assert_called_with("new_item")

    def test_dry_run_default_in_all_tabs(self):
        # 1. Scanner Tab
        scanner_tab = ScannerTab(self.mock_scanner, self.mock_cleaner, self.mock_safety)
        self.assertTrue(scanner_tab.chk_dry_run.isChecked(), "Scanner Tab dry run must be checked by default")
        self.assertIn("Simulate Clean (Dry Run)", scanner_tab.btn_clean.text())
        scanner_tab.chk_dry_run.setChecked(False)
        self.assertIn("Clean Selected Items", scanner_tab.btn_clean.text())

        # 2. Cache Tab
        cache_tab = CacheTab(self.mock_cache)
        self.assertTrue(cache_tab.chk_dry_run.isChecked(), "Cache Tab dry run must be checked by default")
        self.assertIn("Simulate Cache Purge (Dry Run)", cache_tab.btn_clean_all.text())
        cache_tab.chk_dry_run.setChecked(False)
        self.assertIn("Purge Selected Caches", cache_tab.btn_clean_all.text())

        # 3. App Reset Tab
        reset_tab = AppResetTab(self.mock_resetter)
        self.assertTrue(reset_tab.chk_dry_run.isChecked(), "App Reset Tab dry run must be checked by default")
        self.assertIn("Simulate Reset (Dry Run)", reset_tab.btn_reset.text())
        reset_tab.chk_dry_run.setChecked(False)
        self.assertIn("Reset Application", reset_tab.btn_reset.text())

    def test_main_window_navigation(self):
        win = MainWindow(
            scanner=self.mock_scanner,
            cleaner=self.mock_cleaner,
            safety=self.mock_safety,
            backup_mgr=self.mock_backup_mgr,
            restore_mgr=self.mock_restore_mgr,
            cache_cleaner=self.mock_cache,
            pkg_mgr=self.mock_pkg,
            app_resetter=self.mock_resetter,
            auto_scan_on_nav=False,
        )
        self.assertEqual(win.stack.count(), 7)

        # Test sidebar switches
        win.sidebar.setCurrentRow(1)
        self.assertEqual(win.stack.currentIndex(), 1)
        win.sidebar.setCurrentRow(4)
        self.assertEqual(win.stack.currentIndex(), 4)


if __name__ == "__main__":
    unittest.main()

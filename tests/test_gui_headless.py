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
from confclean.gui.tab_scanner import RpmDiffDialog, ScannerTab
from confclean.gui.tab_settings import ElevationWorker, SettingsTab
from confclean.gui.workers import (
    AppResetWorker,
    ArchiveInspectWorker,
    BackupListWorker,
    CacheCleanWorker,
    CleanWorker,
    PackageRemovalWorker,
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

        # 7. BackupListWorker
        self.mock_backup_mgr.list_backups.return_value = []
        list_w = BackupListWorker(self.mock_backup_mgr)
        list_w.run()

        # 8. ArchiveInspectWorker
        self.mock_restore_mgr.get_archive_items.return_value = []
        inspect_w = ArchiveInspectWorker(self.mock_restore_mgr, "/b.tar.gz")
        inspect_w.run()

        # 9. PackageRemovalWorker
        with patch("subprocess.run") as mock_sub_run:
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Removed"
            mock_res.stderr = ""
            mock_sub_run.return_value = mock_res
            rem_w = PackageRemovalWorker(["echo", "done"])
            rem_w.run()

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

    def test_restore_tab_async_loading_and_guards(self):
        meta = BackupMetadata("backup_1", "/backups/b1.tar.gz", "/backups/b1.log", "2026-10-29", "user", 2, 4000)
        tab = RestoreTab(self.mock_backup_mgr, self.mock_restore_mgr)

        # 1. Simulate already loading guard
        tab.is_loading = True
        tab.load_backups()
        self.assertEqual(tab.backup_list.count(), 0)

        # 2. Simulate worker completion
        tab._on_backups_loaded([meta])
        self.assertFalse(tab.is_loading)
        self.assertEqual(tab.backup_list.count(), 1)

        # 3. Simulate archive inspection completion
        items = [{"id": "item_1", "name": "app", "original_path": "/etc/app", "formatted_size": "2 KB", "reason": "Orphan"}]
        tab._on_archive_inspected("/backups/b1.tar.gz", items)
        self.assertEqual(tab.tree_items.topLevelItemCount(), 1)
        self.assertTrue(tab.btn_restore_selected.isEnabled())

        # 4. Simulate worker failure
        tab._on_backups_failed("Simulated I/O failure")
        self.assertFalse(tab.is_loading)
        self.assertIn("Simulated I/O failure", tab.lbl_backup_info.text())

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

        # Verify copyright notice under architecture & safety rules
        labels = [w.text() for w in tab.findChildren(QLabel)]
        self.assertTrue(any("BuildDesignCreate.com" in txt for txt in labels))

    def test_elevation_worker(self):
        # 1. Success case
        mock_proc_success = MagicMock()
        mock_proc_success.stdout.readline.return_value = "CONFCLEAN_ELEVATED_READY\n"
        with patch("subprocess.Popen", return_value=mock_proc_success):
            worker = ElevationWorker(["pkexec", "env", "python3", "main.py"])
            success_slot = MagicMock()
            worker.elevation_succeeded.connect(success_slot)
            worker.run()
            success_slot.assert_called_once()

        # 2. Cancelled case (code 126 or 127)
        mock_proc_cancel = MagicMock()
        mock_proc_cancel.stdout.readline.return_value = ""
        mock_proc_cancel.wait.return_value = 126
        mock_proc_cancel.returncode = 126
        mock_proc_cancel.stderr.read.return_value = "Not authorized"
        with patch("subprocess.Popen", return_value=mock_proc_cancel):
            worker = ElevationWorker(["pkexec", "env", "python3", "main.py"])
            failed_slot = MagicMock()
            worker.elevation_failed.connect(failed_slot)
            worker.run()
            failed_slot.assert_called_once_with("cancelled")

        # 3. Process failure case
        mock_proc_fail = MagicMock()
        mock_proc_fail.stdout.readline.return_value = ""
        mock_proc_fail.wait.return_value = 1
        mock_proc_fail.returncode = 1
        mock_proc_fail.stderr.read.return_value = "Fatal error initializing display"
        with patch("subprocess.Popen", return_value=mock_proc_fail):
            worker = ElevationWorker(["pkexec", "env", "python3", "main.py"])
            failed_slot = MagicMock()
            worker.elevation_failed.connect(failed_slot)
            worker.run()
            failed_slot.assert_called_once_with("Fatal error initializing display")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_settings_tab_elevation_logic(self, mock_subproc_run, mock_which):
        from PyQt6.QtWidgets import QMessageBox

        mock_which.return_value = "/usr/bin/pkexec"
        tab = SettingsTab(self.mock_safety)
        self.assertTrue(hasattr(tab, "btn_elevate"))

        # User confirms question prompt
        self.mock_quest.return_value = QMessageBox.StandardButton.Yes

        with patch.object(ElevationWorker, "start") as mock_worker_start:
            tab._relaunch_as_root()
            mock_subproc_run.assert_called_once_with(
                ["xhost", "+SI:localuser:root"], capture_output=True, timeout=2, check=False
            )
            self.assertFalse(tab.btn_elevate.isEnabled())
            self.assertEqual(tab.btn_elevate.text(), "Waiting for authorization...")
            mock_worker_start.assert_called_once()

        # Test failure handler restores button
        tab._on_elevation_failed("cancelled")
        self.assertTrue(tab.btn_elevate.isEnabled())
        self.assertIn("Relaunch as Root", tab.btn_elevate.text())

        # Test success handler invokes QApplication.quit
        with patch("PyQt6.QtWidgets.QApplication.quit") as mock_quit:
            tab._on_elevation_succeeded()
            mock_quit.assert_called_once()

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

        # Test auto-scan on navigating to Package Manager tab when list is blank
        win.auto_scan_on_nav = True
        with patch.object(win.tab_packages, "start_package_scan") as mock_pkg_scan:
            win._on_nav_changed(2)
            mock_pkg_scan.assert_called_once()

    @patch("confclean.gui.tab_scanner.get_rpm_diff")
    def test_rpm_diff_dialog(self, mock_diff):
        mock_diff.return_value = (
            "/etc/test.conf",
            "/etc/test.conf.rpmnew",
            "--- /etc/test.conf\n+++ /etc/test.conf.rpmnew\n@@ -1,1 +1,1 @@\n-old_line\n+new_line\n context_line",
        )
        dialog = RpmDiffDialog("/etc/test.conf.rpmnew")
        self.assertIn("test.conf.rpmnew", dialog.windowTitle())
        html = dialog.text_view.toHtml()
        self.assertIn("old_line", html)
        self.assertIn("new_line", html)

        # Test clipboard copy
        with patch.object(QApplication, "clipboard") as mock_clip:
            mock_cb_instance = MagicMock()
            mock_clip.return_value = mock_cb_instance
            dialog._copy_diff("diff content")
            mock_cb_instance.setText.assert_called_with("diff content")

    @patch.object(ScannerTab, "_show_rpm_diff")
    def test_scanner_tab_rpm_diff_double_click(self, mock_show_diff):
        tab = ScannerTab(self.mock_scanner, self.mock_cleaner, self.mock_safety)
        item_rpm = ScanItem(
            "/etc/app.conf.rpmnew",
            "app.conf.rpmnew",
            "RPM Backup",
            False,
            100,
            1,
            10.0,
            "CONFIRMED_ORPHAN",
            "RPM new template",
        )
        item_normal = ScanItem(
            "/home/u/.config/app",
            "app",
            "config",
            True,
            100,
            1,
            10.0,
            "CONFIRMED_ORPHAN",
            "Orphan",
        )
        tab.scanned_items = [item_rpm, item_normal]
        tab._populate_tree()

        tree_item_rpm = tab.tree.topLevelItem(0)
        tree_item_normal = tab.tree.topLevelItem(1)

        tab._on_item_double_clicked(tree_item_rpm, 0)
        mock_show_diff.assert_called_once_with("/etc/app.conf.rpmnew")

        mock_show_diff.reset_mock()
        tab._on_item_double_clicked(tree_item_normal, 0)
        mock_show_diff.assert_not_called()

    def test_scanner_tab_broken_desktop_entry(self):
        tab = ScannerTab(self.mock_scanner, self.mock_cleaner, self.mock_safety)
        item_desktop = ScanItem(
            "/home/user/.local/share/applications/deleted-app.desktop",
            "deleted-app.desktop",
            "Broken Desktop",
            False,
            250,
            1,
            10.0,
            "CONFIRMED_ORPHAN",
            "Target executable /usr/bin/deleted-app no longer exists",
        )
        tab.scanned_items = [item_desktop]
        tab._populate_tree()

        self.assertEqual(tab.tree.topLevelItemCount(), 1)
        tree_item = tab.tree.topLevelItem(0)
        self.assertEqual(tree_item.text(1), "deleted-app.desktop")
        self.assertEqual(tree_item.text(2), "🔴 Orphan")
        self.assertEqual(tree_item.text(3), "Broken Desktop")

    def test_package_tab_flatpak_snap_and_batch_removal(self):
        s_flatpak = PackageSuggestion(
            name="org.gnome.Platform//45",
            version="45",
            release="",
            arch="x86_64",
            size_bytes=500 * 1024 * 1024,
            summary="Unused runtime",
            category="flatpak_unused",
            reason="Unused runtime",
            is_protected=False,
            is_selected=True,
        )
        s_snap = PackageSuggestion(
            name="core20 (rev 1822)",
            version="rev 1822",
            release="",
            arch="",
            size_bytes=60 * 1024 * 1024,
            summary="Disabled revision",
            category="snap_unused",
            reason="Disabled revision",
            is_protected=False,
            is_selected=True,
        )
        tab = PackageTab(self.mock_pkg)
        tab.suggestions = [s_flatpak, s_snap]
        tab._populate_table()

        self.assertEqual(tab.table.rowCount(), 2)
        self.assertEqual(tab.table.item(0, 4).text(), "Flatpak Runtime")
        self.assertEqual(tab.table.item(1, 4).text(), "Snap Revision")

        # Test batch removal call
        from PyQt6.QtWidgets import QMessageBox
        self.mock_quest.return_value = QMessageBox.StandardButton.Yes
        self.mock_pkg.get_removal_command.return_value = ["flatpak", "uninstall", "--unused", "-y"]
        with patch.object(PackageRemovalWorker, "start") as mock_worker_start:
            tab._remove_selected_packages()
            self.mock_pkg.get_removal_command.assert_called_once_with([s_flatpak, s_snap])
            self.assertEqual(tab.progress_bar.maximum(), 0)  # Indeterminate activity bar
            self.assertFalse(tab.progress_bar.isHidden())
            mock_worker_start.assert_called_once()

        # Test completion and automatic package re-analysis
        with patch.object(tab, "start_package_scan") as mock_reanalyze:
            tab._on_removal_finished(0, "Success")
            self.assertTrue(tab.progress_bar.isHidden())
            mock_reanalyze.assert_called_once()


if __name__ == "__main__":
    unittest.main()

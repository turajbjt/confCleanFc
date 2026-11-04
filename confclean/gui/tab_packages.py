"""
DNF and RPM Package Optimizer Tab for ConfClean FC.
Identifies unneeded dependencies (autoremove) and old kernels while strictly protecting the running kernel.
"""

import subprocess
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from confclean.core.cache_cleaner import CacheCleaner
from confclean.core.package_manager import PackageManager, PackageSuggestion
from confclean.core.selinux_manager import SELinuxManager
from confclean.gui.workers import PackageRemovalWorker, PackageScanWorker


class PackageTab(QWidget):
    """View for inspecting and removing orphaned RPM packages, managing package cache, and SELinux policies."""

    def __init__(
        self,
        pkg_mgr: PackageManager,
        selinux_mgr: Optional[SELinuxManager] = None,
        cache_cleaner: Optional[CacheCleaner] = None,
    ):
        super().__init__()
        self.pkg_mgr = pkg_mgr
        self.selinux_mgr = selinux_mgr or SELinuxManager()
        self.cache_cleaner = cache_cleaner or CacheCleaner()
        self.suggestions: List[PackageSuggestion] = []
        self.worker: Optional[PackageScanWorker] = None
        self.removal_worker: Optional[PackageRemovalWorker] = None

        self._init_ui()
        self._refresh_selinux_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header card
        header_card = QFrame()
        header_card.setProperty("class", "card")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)

        desc_lbl = QLabel(
            "Manage RPM dependencies, retired packages, older kernels, Flatpak runtimes, DNF download cache, and SELinux policies. "
            "The currently booted kernel and backup kernel are strictly protected."
        )
        desc_lbl.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        h_layout.addWidget(desc_lbl)

        h_layout.addStretch()

        self.btn_clean_cache = QPushButton("🧹 Purge DNF Cache")
        self.btn_clean_cache.setToolTip("Purge downloaded RPM packages, metadata, and PackageKit cache")
        self.btn_clean_cache.clicked.connect(self._purge_package_cache)
        h_layout.addWidget(self.btn_clean_cache)

        self.btn_refresh = QPushButton("🔍 Analyze Packages")
        self.btn_refresh.setProperty("class", "primary")
        self.btn_refresh.clicked.connect(self.start_package_scan)
        h_layout.addWidget(self.btn_refresh)

        layout.addWidget(header_card)

        # Filter and Search Bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter packages by name...")
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.txt_search, stretch=2)

        self.cat_filter = QComboBox()
        self.cat_filter.addItems(
            [
                "All Categories",
                "Retired Packages",
                "Orphan Dependencies",
                "Old Kernels",
                "Duplicate Versions",
                "Flatpak Runtimes",
                "Snap Revisions",
            ]
        )
        self.cat_filter.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.cat_filter, stretch=1)

        self.btn_select_all = QPushButton("☑️ Select All")
        self.btn_select_all.clicked.connect(self._select_all_visible)
        filter_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("⬜ Deselect All")
        self.btn_deselect_all.clicked.connect(self._deselect_all_visible)
        filter_layout.addWidget(self.btn_deselect_all)

        layout.addLayout(filter_layout)

        # Package Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["", "Package Name", "Version", "Size", "Category", "Status / Reason"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_table_item_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table, stretch=1)

        # Bottom card
        bottom_card = QFrame()
        bottom_card.setProperty("class", "card")
        b_layout = QHBoxLayout(bottom_card)
        b_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_summary = QLabel("Ready to scan packages.")
        self.lbl_summary.setStyleSheet("font-weight: bold; color: #99c1f1;")
        b_layout.addWidget(self.lbl_summary)

        b_layout.addStretch()

        self.btn_remove = QPushButton("📦 Remove Selected Packages")
        self.btn_remove.setProperty("class", "destructive")
        self.btn_remove.clicked.connect(self._remove_selected_packages)
        b_layout.addWidget(self.btn_remove)

        layout.addWidget(bottom_card)

        # SELinux System Maintenance Card
        selinux_card = QFrame()
        selinux_card.setProperty("class", "card")
        sl_layout = QVBoxLayout(selinux_card)
        sl_layout.setContentsMargins(12, 10, 12, 10)
        sl_layout.setSpacing(8)

        sl_header = QHBoxLayout()
        sl_title = QLabel("🛡️ SELinux Policy & File Context Maintenance")
        sl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        sl_header.addWidget(sl_title)
        sl_header.addStretch()

        self.btn_refresh_selinux = QPushButton("🔄 Refresh")
        self.btn_refresh_selinux.clicked.connect(self._refresh_selinux_ui)
        sl_header.addWidget(self.btn_refresh_selinux)
        sl_layout.addLayout(sl_header)

        sl_desc = QLabel(
            "Fix security file contexts and SELinux policies across system directories. "
            "Scheduling 'fixfiles -B onboot' relabels files created or modified since last boot "
            "during next system startup without performing an excessively slow full-disk scan."
        )
        sl_desc.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        sl_layout.addWidget(sl_desc)

        # Status and Actions row
        sl_status_row = QHBoxLayout()
        self.lbl_selinux_status = QLabel("SELinux: Checking status...")
        self.lbl_selinux_status.setStyleSheet("font-size: 13px;")
        sl_status_row.addWidget(self.lbl_selinux_status)
        sl_status_row.addStretch()

        self.btn_fix_selinux = QPushButton("🛡️ Fix SELinux on Next Boot (sudo fixfiles -B onboot)")
        self.btn_fix_selinux.setProperty("class", "primary")
        self.btn_fix_selinux.clicked.connect(self._schedule_selinux_fix)
        sl_status_row.addWidget(self.btn_fix_selinux)

        self.btn_cancel_selinux = QPushButton("❌ Cancel Scheduled Relabel")
        self.btn_cancel_selinux.setProperty("class", "destructive")
        self.btn_cancel_selinux.setVisible(False)
        self.btn_cancel_selinux.clicked.connect(self._cancel_selinux_fix)
        sl_status_row.addWidget(self.btn_cancel_selinux)

        sl_layout.addLayout(sl_status_row)
        layout.addWidget(selinux_card)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

    def start_package_scan(self):
        """Starts background package scan."""
        if self.worker is not None and self.worker.isRunning():
            return

        self.btn_refresh.setEnabled(False)
        self.btn_remove.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Querying DNF package database...")

        self.worker = PackageScanWorker(self.pkg_mgr)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, msg: str, cur: int, total: int):
        self.progress_label.setText(msg)
        if total > 0:
            self.progress_bar.setValue(int((cur / total) * 100))

    def _on_finished(self, suggestions: List[PackageSuggestion]):
        self.suggestions = suggestions
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_refresh.setEnabled(True)
        self.btn_remove.setEnabled(True)
        self._populate_table()

    def _on_failed(self, error: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_refresh.setEnabled(True)
        self.btn_remove.setEnabled(True)
        QMessageBox.critical(self, "Package Query Error", f"Failed to query packages: {error}")

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.suggestions))

        for row, s in enumerate(self.suggestions):
            # Column 0: Checkbox
            chk = QTableWidgetItem()
            if s.is_protected:
                chk.setFlags(chk.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Unchecked)
            else:
                chk.setFlags(chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Checked if s.is_selected else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, chk)

            # Column 1: Name
            name_item = QTableWidgetItem(s.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            # Column 2: Version
            ver_item = QTableWidgetItem(s.version)
            ver_item.setFlags(ver_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, ver_item)

            # Column 3: Size
            size_item = QTableWidgetItem(s.formatted_size)
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, size_item)

            # Column 4: Category
            if s.category == "repo_orphan":
                cat_display = "Retired Package"
            elif s.category == "flatpak_unused":
                cat_display = "Flatpak Runtime"
            elif s.category == "snap_unused":
                cat_display = "Snap Revision"
            elif s.category == "old_kernel":
                cat_display = "Old Kernel"
            elif s.category == "unneeded_dep":
                cat_display = "Orphan Dependency"
            elif s.category == "duplicate":
                cat_display = "Duplicate Version"
            else:
                cat_display = s.category.replace("_", " ").title()
            cat_item = QTableWidgetItem(cat_display)
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 4, cat_item)

            # Column 5: Status / Reason
            reason_item = QTableWidgetItem(s.reason)
            reason_item.setFlags(reason_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if s.is_protected:
                reason_item.setForeground(QColor("#79c0ff"))
                name_item.setForeground(QColor("#79c0ff"))
            else:
                reason_item.setForeground(QColor("#ff7b72"))
                name_item.setForeground(QColor("#ff7b72"))
            self.table.setItem(row, 5, reason_item)

        self.table.blockSignals(False)
        self.table.resizeColumnToContents(1)
        self._apply_filters()
        self._update_selected_summary()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            row = item.row()
            if 0 <= row < len(self.suggestions):
                s = self.suggestions[row]
                if not s.is_protected:
                    s.is_selected = (item.checkState() == Qt.CheckState.Checked)
                    self._update_selected_summary()

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        filter_idx = self.cat_filter.currentIndex()
        # 0: All, 1: Retired, 2: Orphan, 3: Kernel, 4: Duplicate, 5: Flatpak, 6: Snap

        for row in range(self.table.rowCount()):
            if row < len(self.suggestions):
                s = self.suggestions[row]
                matches_search = not query or (query in s.name.lower() or query in s.summary.lower())
                matches_cat = True
                if filter_idx == 1:
                    matches_cat = (s.category == "repo_orphan")
                elif filter_idx == 2:
                    matches_cat = (s.category == "unneeded_dep")
                elif filter_idx == 3:
                    matches_cat = (s.category == "old_kernel")
                elif filter_idx == 4:
                    matches_cat = (s.category == "duplicate")
                elif filter_idx == 5:
                    matches_cat = (s.category == "flatpak_unused")
                elif filter_idx == 6:
                    matches_cat = (s.category == "snap_unused")

                self.table.setRowHidden(row, not (matches_search and matches_cat))

        self._update_selected_summary()

    def _select_all_visible(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row) and row < len(self.suggestions):
                s = self.suggestions[row]
                if not s.is_protected:
                    s.is_selected = True
                    chk = self.table.item(row, 0)
                    if chk:
                        chk.setCheckState(Qt.CheckState.Checked)
        self.table.blockSignals(False)
        self._update_selected_summary()

    def _deselect_all_visible(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row) and row < len(self.suggestions):
                s = self.suggestions[row]
                if not s.is_protected:
                    s.is_selected = False
                    chk = self.table.item(row, 0)
                    if chk:
                        chk.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_selected_summary()

    def _update_selected_summary(self):
        total_items = len(self.suggestions)
        selected = [s for s in self.suggestions if not s.is_protected and s.is_selected]
        selected_bytes = sum(s.size_bytes for s in selected)
        size_mb = selected_bytes / (1024 * 1024)

        visible_count = sum(1 for r in range(self.table.rowCount()) if not self.table.isRowHidden(r))
        if visible_count < total_items:
            self.lbl_summary.setText(
                f"Showing {visible_count} of {total_items} packages ({len(selected)} selected, {size_mb:.2f} MB removable)."
            )
        else:
            self.lbl_summary.setText(
                f"Found {total_items} packages ({len(selected)} selected, {size_mb:.2f} MB removable)."
            )

    def _remove_selected_packages(self):
        selected_pkgs: List[PackageSuggestion] = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                s = self.suggestions[row]
                if not s.is_protected:
                    selected_pkgs.append(s)

        if not selected_pkgs:
            QMessageBox.information(self, "No Selection", "Please select at least one package to remove.")
            return

        cmd = self.pkg_mgr.get_removal_command(selected_pkgs)
        cmd_str = " ".join(cmd)

        msg = (
            f"You have selected {len(selected_pkgs)} package(s) for removal.\n\n"
            f"Command to execute:\n{cmd_str}\n\n"
            f"Do you want to proceed with package removal?"
        )

        reply = QMessageBox.question(
            self,
            "Confirm Package Removal",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Disable interactive controls while removal runs
        self.btn_refresh.setEnabled(False)
        self.btn_remove.setEnabled(False)
        self.table.setEnabled(False)

        # Show activity bar (indeterminate pulsing mode)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Removing selected packages... Please authenticate if prompted.")
        self.lbl_summary.setText("Removal in progress... Please follow any authentication prompts.")

        # Start removal worker in background
        self.removal_worker = PackageRemovalWorker(cmd)
        self.removal_worker.finished.connect(self._on_removal_finished)
        self.removal_worker.failed.connect(self._on_removal_failed)
        self.removal_worker.start()

    def _on_removal_finished(self, returncode: int, output: str):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.table.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.btn_remove.setEnabled(True)

        if returncode == 0:
            msg = (
                "Package removal process completed successfully!\n\n"
                "Click OK to re-analyze installed packages."
            )
            QMessageBox.information(self, "Package Removal Complete", msg)
        else:
            detail = output.strip() if output.strip() else f"Process exited with status code {returncode}."
            if len(detail) > 400:
                detail = detail[:400] + "..."
            msg = (
                f"Package removal process did not complete cleanly (exit code {returncode}).\n\n"
                f"Details:\n{detail}\n\n"
                "Click OK to re-analyze installed packages."
            )
            QMessageBox.warning(self, "Package Removal Incomplete or Cancelled", msg)

        # Re-analyze packages to update list upon confirmation
        self.start_package_scan()

    def _on_removal_failed(self, error: str):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.table.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.btn_remove.setEnabled(True)
        QMessageBox.critical(self, "Execution Error", f"Failed to execute package removal: {error}")

    def _purge_package_cache(self):
        """Purges DNF and PackageKit download caches directly from Package tab."""
        cats = [c for c in self.cache_cleaner.scan_categories() if c.category_id == "dnf_cache"]
        if not cats:
            QMessageBox.information(self, "Package Cache", "No package cache found.")
            return

        cat = cats[0]
        reply = QMessageBox.question(
            self,
            "Purge Package Cache",
            f"Are you sure you want to clean DNF and PackageKit package caches ({cat.formatted_size})?\n\n"
            "This will safely remove downloaded RPM packages, solv files, and expired metadata. "
            "No installed software will be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            reclaimed, count, msg = self.cache_cleaner.clean_category(cat, dry_run=False)
            QMessageBox.information(
                self,
                "Package Cache Purged",
                f"Successfully cleaned package cache!\n\nReclaimed: {reclaimed / (1024*1024):.1f} MB ({count} items removed)",
            )

    def _refresh_selinux_ui(self):
        """Refreshes SELinux status badge and action button states."""
        st = self.selinux_mgr.get_status()
        is_supported = self.selinux_mgr.is_selinux_supported()
        is_scheduled = st["autorelabel_scheduled"]

        if not is_supported:
            self.lbl_selinux_status.setText("SELinux: <b>Not Installed / Unsupported</b>")
            self.btn_fix_selinux.setEnabled(False)
            self.btn_cancel_selinux.setVisible(False)
            return

        mode = st["mode"]
        policy = st["policy"]
        if is_scheduled:
            flags = st["autorelabel_flags"] or "active"
            status_txt = (
                f"SELinux: <b>{mode}</b> ({policy}) | "
                f"<span style='color: #f6c177; font-weight: bold;'>⚠️ Relabel Scheduled on Next Boot ({flags})</span>"
            )
            self.btn_cancel_selinux.setVisible(True)
            self.btn_cancel_selinux.setEnabled(True)
            self.btn_fix_selinux.setText("🛡️ Re-Schedule Relabel on Next Boot")
        else:
            status_txt = (
                f"SELinux: <b>{mode}</b> ({policy}) | "
                f"<span style='color: #9ece6a;'>✓ Normal Boot (No relabel pending)</span>"
            )
            self.btn_cancel_selinux.setVisible(False)
            self.btn_fix_selinux.setText("🛡️ Fix SELinux on Next Boot (sudo fixfiles -B onboot)")

        self.lbl_selinux_status.setText(status_txt)
        self.btn_fix_selinux.setEnabled(st["fixfiles_available"])

    def _schedule_selinux_fix(self):
        """Schedules fixfiles -B onboot for next system startup."""
        if not self.selinux_mgr.is_selinux_supported():
            QMessageBox.critical(
                self,
                "SELinux Unavailable",
                "The 'fixfiles' utility is not installed. Please install 'policycoreutils' to enable SELinux maintenance.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm SELinux Relabel on Next Boot",
            "This will schedule 'fixfiles -B onboot'.\n\n"
            "During the next system startup, the system will verify and fix SELinux security contexts "
            "for files created or modified since last boot without doing a slow full disk relabel.\n\n"
            "Proceed with scheduling?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success, msg = self.selinux_mgr.schedule_onboot_fix(boottime_only=True, use_pkexec=True)
        if success:
            QMessageBox.information(self, "SELinux Relabel Scheduled", msg)
        else:
            QMessageBox.critical(self, "SELinux Relabel Error", msg)

        self._refresh_selinux_ui()

    def _cancel_selinux_fix(self):
        """Cancels a scheduled on-boot SELinux relabel."""
        reply = QMessageBox.question(
            self,
            "Cancel SELinux Relabel",
            "Are you sure you want to cancel the scheduled SELinux relabel for the next boot?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success, msg = self.selinux_mgr.cancel_onboot_fix(use_pkexec=True)
        if success:
            QMessageBox.information(self, "SELinux Relabel Cancelled", msg)
        else:
            QMessageBox.warning(self, "Error", msg)

        self._refresh_selinux_ui()

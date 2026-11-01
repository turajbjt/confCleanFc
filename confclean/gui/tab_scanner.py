"""
Orphan Configuration Scanner Tab for ConfClean FC.
Provides interactive inspection, filtering, selection, and safe cleanup of leftover settings.
"""

import os
import subprocess
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from confclean.core.cleaner import SafeCleaner
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ConfigScanner, ScanItem, get_rpm_diff
from confclean.gui.workers import CleanWorker, ScanWorker


class RpmDiffDialog(QDialog):
    """Dialog displaying a syntax-highlighted unified diff between active and RPM config files."""

    def __init__(self, rpm_path: str, parent=None):
        super().__init__(parent)
        self.rpm_path = rpm_path
        self.setWindowTitle(f"Configuration Diff — {os.path.basename(rpm_path)}")
        self.resize(850, 550)
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Compute diff
        active_path, rpm_path_out, diff_text = get_rpm_diff(rpm_path)

        # Header info card
        header_card = QFrame()
        header_card.setProperty("class", "card")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(4)

        title_lbl = QLabel("<b>Unified Diff Comparison</b>")
        title_lbl.setStyleSheet("font-size: 14px; color: #79c0ff;")
        h_layout.addWidget(title_lbl)

        p1_lbl = QLabel(f"<b>Active Config:</b> <code>{active_path or 'Not Found'}</code>")
        p1_lbl.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        h_layout.addWidget(p1_lbl)

        p2_lbl = QLabel(f"<b>RPM Template:</b> <code>{rpm_path}</code>")
        p2_lbl.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        h_layout.addWidget(p2_lbl)

        layout.addWidget(header_card)

        # Monospace Text Viewer with diff coloring
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Monospace", 10))
        self._set_colored_diff(diff_text)
        layout.addWidget(self.text_view, stretch=1)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Copy Diff")
        btn_copy.clicked.connect(lambda: self._copy_diff(diff_text))
        btn_layout.addWidget(btn_copy)

        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "primary")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _copy_diff(self, text: str):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            QMessageBox.information(self, "Copied", "Diff copied to clipboard.")

    def _set_colored_diff(self, diff_text: str):
        import html
        html_lines = []
        for line in diff_text.splitlines():
            escaped = html.escape(line)
            if line.startswith("+++") or line.startswith("---"):
                html_lines.append(f"<span style='color: #8b949e; font-weight: bold;'>{escaped}</span>")
            elif line.startswith("@@"):
                html_lines.append(f"<span style='color: #d2a8ff; font-weight: bold;'>{escaped}</span>")
            elif line.startswith("+"):
                html_lines.append(f"<span style='color: #7ee787; background-color: #0d2818;'>{escaped}</span>")
            elif line.startswith("-"):
                html_lines.append(f"<span style='color: #ff7b72; background-color: #3b1219;'>{escaped}</span>")
            else:
                html_lines.append(f"<span style='color: #c9d1d9;'>{escaped}</span>")

        self.text_view.setHtml("<pre style='margin: 0; line-height: 1.4;'>" + "<br>".join(html_lines) + "</pre>")


class ScannerTab(QWidget):
    """View for scanning and cleaning orphaned application configurations."""

    status_changed = pyqtSignal()  # Emitted when stats or items change

    def __init__(self, scanner: ConfigScanner, cleaner: SafeCleaner, safety: SafetyEngine):
        super().__init__()
        self.scanner = scanner
        self.cleaner = cleaner
        self.safety = safety

        self.scanned_items: List[ScanItem] = []
        self.scan_worker: Optional[ScanWorker] = None
        self.clean_worker: Optional[CleanWorker] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Top Control & Filter Bar
        filter_card = QFrame()
        filter_card.setProperty("class", "card")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(10, 8, 10, 8)

        self.btn_rescan = QPushButton("🔍 Scan System")
        self.btn_rescan.setProperty("class", "primary")
        self.btn_rescan.clicked.connect(self.start_scan)
        filter_layout.addWidget(self.btn_rescan)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by application name or path...")
        self.search_input.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_input, stretch=2)

        self.status_filter = QComboBox()
        self.status_filter.addItems(
            ["Show All", "Confirmed Orphans Only", "Probable Orphans", "Active Applications", "Protected Safelist"]
        )
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.status_filter)

        layout.addWidget(filter_card)

        # Main Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "Name", "Status", "Category", "Size", "Modified", "Evidence / Reason"])
        self.tree.setSortingEnabled(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemChanged.connect(self._on_item_checked)

        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.tree, stretch=1)

        # Bottom Action Bar
        bottom_card = QFrame()
        bottom_card.setProperty("class", "card")
        bottom_layout = QHBoxLayout(bottom_card)
        bottom_layout.setContentsMargins(12, 10, 12, 10)

        # Selection helpers
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.clicked.connect(self._select_all)
        bottom_layout.addWidget(self.btn_select_all)

        self.btn_select_none = QPushButton("Select None")
        self.btn_select_none.clicked.connect(self._select_none)
        bottom_layout.addWidget(self.btn_select_none)

        self.btn_select_orphans = QPushButton("Select Only Orphans")
        self.btn_select_orphans.clicked.connect(self._select_orphans_only)
        bottom_layout.addWidget(self.btn_select_orphans)

        bottom_layout.addSpacing(20)

        # Safety Checkboxes
        self.chk_backup = QCheckBox("Create Safety Backup Archive before deleting")
        self.chk_backup.setChecked(True)
        self.chk_backup.setToolTip("Compresses and archives all targeted files into .tar.gz with manifest before deletion.")
        bottom_layout.addWidget(self.chk_backup)

        self.chk_dry_run = QCheckBox("Dry Run (Simulation)")
        self.chk_dry_run.setChecked(True)
        self.chk_dry_run.setToolTip("Simulate the cleaning process without modifying or deleting any files (ON by default).")
        self.chk_dry_run.toggled.connect(self._on_dry_run_toggled)
        bottom_layout.addWidget(self.chk_dry_run)

        bottom_layout.addStretch()

        # Stats summary
        self.lbl_selected_stats = QLabel("Selected: 0 items (0 B)")
        self.lbl_selected_stats.setStyleSheet("font-weight: bold; color: #99c1f1; margin-right: 12px;")
        bottom_layout.addWidget(self.lbl_selected_stats)

        # Clean Button (Initialized in Dry Run mode by default)
        self.btn_clean = QPushButton("🔍 Simulate Clean (Dry Run)")
        self.btn_clean.setProperty("class", "primary")
        self.btn_clean.clicked.connect(self.start_clean)
        bottom_layout.addWidget(self.btn_clean)

        layout.addWidget(bottom_card)

        # Progress Indicator Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

    def _on_dry_run_toggled(self, checked: bool):
        """Updates clean button appearance and label based on dry-run state."""
        if checked:
            self.btn_clean.setText("🔍 Simulate Clean (Dry Run)")
            self.btn_clean.setProperty("class", "primary")
        else:
            self.btn_clean.setText("🗑️ Clean Selected Items")
            self.btn_clean.setProperty("class", "destructive")
        if self.btn_clean.style():
            self.btn_clean.style().unpolish(self.btn_clean)
            self.btn_clean.style().polish(self.btn_clean)

    def start_scan(self):
        """Launches background scan."""
        self.btn_rescan.setEnabled(False)
        self.btn_clean.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Scanning configuration directories...")

        self.scan_worker = ScanWorker(self.scanner)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.failed.connect(self._on_scan_failed)
        self.scan_worker.start()

    def _on_scan_progress(self, msg: str, cur: int, total: int):
        self.progress_label.setText(msg)
        if total > 0:
            self.progress_bar.setValue(int((cur / total) * 100))

    def _on_scan_finished(self, items: List[ScanItem]):
        self.scanned_items = items
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_rescan.setEnabled(True)
        self.btn_clean.setEnabled(True)
        self._populate_tree()
        self.status_changed.emit()

    def _on_scan_failed(self, error: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_rescan.setEnabled(True)
        self.btn_clean.setEnabled(True)
        QMessageBox.critical(self, "Scan Error", f"Failed to scan system: {error}")

    def _populate_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()

        for item in self.scanned_items:
            tree_item = QTreeWidgetItem()
            # Column 0: Checkbox
            if item.status == "PROTECTED":
                tree_item.setFlags(tree_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                tree_item.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                tree_item.setCheckState(
                    0, Qt.CheckState.Checked if item.is_selected else Qt.CheckState.Unchecked
                )

            # Column 1: Name
            tree_item.setText(1, item.name)
            tree_item.setToolTip(1, item.path)

            # Column 2: Status Badge
            tree_item.setText(2, self._format_status_badge(item.status))

            # Column 3: Category
            tree_item.setText(3, item.category)

            # Column 4: Size
            tree_item.setText(4, item.formatted_size)
            tree_item.setTextAlignment(4, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Column 5: Date
            tree_item.setText(5, item.formatted_date)

            # Column 6: Reason
            tree_item.setText(6, item.reason)

            # Styling colors per status
            if item.status == "CONFIRMED_ORPHAN":
                tree_item.setForeground(1, QColor("#ff7b72"))
                tree_item.setForeground(2, QColor("#ff7b72"))
            elif item.status == "PROBABLE_ORPHAN":
                tree_item.setForeground(1, QColor("#f5c211"))
                tree_item.setForeground(2, QColor("#f5c211"))
            elif item.status == "ACTIVE_APP":
                tree_item.setForeground(1, QColor("#7ee787"))
                tree_item.setForeground(2, QColor("#7ee787"))
            elif item.status == "PROTECTED":
                tree_item.setForeground(1, QColor("#79c0ff"))
                tree_item.setForeground(2, QColor("#79c0ff"))

            tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
            self.tree.addTopLevelItem(tree_item)

        self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(1)
        self._apply_filters()
        self._update_selected_stats()

    def _format_status_badge(self, status: str) -> str:
        if status == "CONFIRMED_ORPHAN":
            return "🔴 Orphan"
        elif status == "PROBABLE_ORPHAN":
            return "🟡 Review"
        elif status == "ACTIVE_APP":
            return "🟢 Active"
        elif status == "PROTECTED":
            return "🔒 Protected"
        return status

    def _apply_filters(self):
        search_text = self.search_input.text().lower().strip()
        filter_mode = self.status_filter.currentIndex()

        for idx in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(idx)
            scan_item: ScanItem = item.data(0, Qt.ItemDataRole.UserRole)
            if not scan_item:
                continue

            matches_search = (
                not search_text
                or search_text in scan_item.name.lower()
                or search_text in scan_item.path.lower()
                or search_text in scan_item.reason.lower()
            )

            matches_status = True
            if filter_mode == 1:  # Confirmed Orphans
                matches_status = (scan_item.status == "CONFIRMED_ORPHAN")
            elif filter_mode == 2:  # Probable
                matches_status = (scan_item.status == "PROBABLE_ORPHAN")
            elif filter_mode == 3:  # Active
                matches_status = (scan_item.status == "ACTIVE_APP")
            elif filter_mode == 4:  # Protected
                matches_status = (scan_item.status == "PROTECTED")

            item.setHidden(not (matches_search and matches_status))

    def _on_item_checked(self, item: QTreeWidgetItem, column: int):
        if column == 0:
            scan_item: ScanItem = item.data(0, Qt.ItemDataRole.UserRole)
            if scan_item:
                scan_item.is_selected = (item.checkState(0) == Qt.CheckState.Checked)
            self._update_selected_stats()

    def _update_selected_stats(self):
        selected_count = 0
        selected_bytes = 0
        for it in self.scanned_items:
            if it.is_selected and it.status != "PROTECTED":
                selected_count += 1
                selected_bytes += it.size_bytes

        size_str = f"{selected_bytes} B"
        if selected_bytes >= 1024 * 1024 * 1024:
            size_str = f"{selected_bytes / (1024*1024*1024):.2f} GB"
        elif selected_bytes >= 1024 * 1024:
            size_str = f"{selected_bytes / (1024*1024):.2f} MB"
        elif selected_bytes >= 1024:
            size_str = f"{selected_bytes / 1024:.2f} KB"

        self.lbl_selected_stats.setText(f"Selected: {selected_count} items ({size_str})")

    def _select_all(self):
        self.tree.blockSignals(True)
        for idx in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(idx)
            if not item.isHidden():
                scan_item: ScanItem = item.data(0, Qt.ItemDataRole.UserRole)
                if scan_item and scan_item.status != "PROTECTED":
                    item.setCheckState(0, Qt.CheckState.Checked)
                    scan_item.is_selected = True
        self.tree.blockSignals(False)
        self._update_selected_stats()

    def _select_none(self):
        self.tree.blockSignals(True)
        for idx in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(idx)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            scan_item: ScanItem = item.data(0, Qt.ItemDataRole.UserRole)
            if scan_item:
                scan_item.is_selected = False
        self.tree.blockSignals(False)
        self._update_selected_stats()

    def _select_orphans_only(self):
        self.tree.blockSignals(True)
        for idx in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(idx)
            scan_item: ScanItem = item.data(0, Qt.ItemDataRole.UserRole)
            if scan_item:
                if scan_item.status == "CONFIRMED_ORPHAN":
                    item.setCheckState(0, Qt.CheckState.Checked)
                    scan_item.is_selected = True
                else:
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    scan_item.is_selected = False
        self.tree.blockSignals(False)
        self._update_selected_stats()

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return

        scan_item: ScanItem = item.data(0, Qt.ItemDataRole.UserRole)
        if not scan_item:
            return

        menu = QMenu(self)

        # Diff viewer for RPM upgrade artifacts (.rpmnew / .rpmsave)
        if scan_item.path.endswith(".rpmnew") or scan_item.path.endswith(".rpmsave"):
            act_diff = QAction("🔍 View Diff with Active Config", self)
            act_diff.triggered.connect(lambda: self._show_rpm_diff(scan_item.path))
            menu.addAction(act_diff)
            menu.addSeparator()

        act_open = QAction("📂 Open in File Manager", self)
        act_open.triggered.connect(lambda: self._open_in_file_manager(scan_item.path))
        menu.addAction(act_open)

        act_copy = QAction("📋 Copy Path", self)
        act_copy.triggered.connect(lambda: self._copy_path(scan_item.path))
        menu.addAction(act_copy)

        menu.addSeparator()

        act_whitelist = QAction("🛡️ Add to Whitelist (Protect Forever)", self)
        act_whitelist.triggered.connect(lambda: self._whitelist_item(scan_item))
        menu.addAction(act_whitelist)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _on_item_double_clicked(self, item, column):
        scan_item: ScanItem = item.data(0, Qt.ItemDataRole.UserRole)
        if scan_item and (scan_item.path.endswith(".rpmnew") or scan_item.path.endswith(".rpmsave")):
            self._show_rpm_diff(scan_item.path)

    def _show_rpm_diff(self, path: str):
        dialog = RpmDiffDialog(path, parent=self)
        dialog.exec()

    def _open_in_file_manager(self, path: str):
        target = path if os.path.isdir(path) else os.path.dirname(path)
        try:
            subprocess.Popen(["xdg-open", target])
        except Exception:
            pass

    def _copy_path(self, path: str):
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(path)

    def _whitelist_item(self, item: ScanItem):
        self.safety.add_user_whitelist(item.name)
        QMessageBox.information(
            self,
            "Added to Whitelist",
            f"'{item.name}' has been added to your custom whitelist and will never be flagged for deletion.",
        )
        self.start_scan()

    def start_clean(self):
        """Starts cleanup workflow."""
        items_to_clean = [it for it in self.scanned_items if it.is_selected and it.status != "PROTECTED"]
        if not items_to_clean:
            QMessageBox.information(self, "No Selection", "Please select at least one item to clean.")
            return

        total_bytes = sum(i.size_bytes for i in items_to_clean)
        size_mb = total_bytes / (1024 * 1024)
        is_dry_run = self.chk_dry_run.isChecked()
        do_backup = self.chk_backup.isChecked()

        # Confirmation dialog
        title = "Dry Run Simulation" if is_dry_run else "Confirm Cleaning"
        msg = (
            f"You have selected {len(items_to_clean)} items ({size_mb:.2f} MB).\n\n"
            f"Safety Backup: {'ENABLED (Recommended)' if do_backup else 'DISABLED'}\n"
            f"Mode: {'SIMULATION ONLY (No files deleted)' if is_dry_run else 'PERMANENT CLEAN'}\n\n"
            f"Are you sure you want to proceed?"
        )

        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_rescan.setEnabled(False)
        self.btn_clean.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Preparing cleanup...")

        self.clean_worker = CleanWorker(
            cleaner=self.cleaner,
            items=items_to_clean,
            create_backup=do_backup,
            dry_run=is_dry_run,
        )
        self.clean_worker.progress.connect(self._on_clean_progress)
        self.clean_worker.finished.connect(self._on_clean_finished)
        self.clean_worker.failed.connect(self._on_clean_failed)
        self.clean_worker.start()

    def _on_clean_progress(self, msg: str, cur: int, total: int):
        self.progress_label.setText(msg)
        if total > 0:
            self.progress_bar.setValue(int((cur / total) * 100))

    def _on_clean_finished(self, result, summary: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_rescan.setEnabled(True)
        self.btn_clean.setEnabled(True)

        QMessageBox.information(self, "Cleanup Complete", summary)
        # Rescan after actual deletion
        if not result.is_dry_run:
            self.start_scan()

    def _on_clean_failed(self, error: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_rescan.setEnabled(True)
        self.btn_clean.setEnabled(True)
        QMessageBox.critical(self, "Clean Failed", f"An error occurred during cleaning:\n{error}")

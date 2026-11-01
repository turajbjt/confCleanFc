"""
DNF and RPM Package Optimizer Tab for ConfClean FC.
Identifies unneeded dependencies (autoremove) and old kernels while strictly protecting the running kernel.
"""

import subprocess
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from confclean.core.package_manager import PackageManager, PackageSuggestion
from confclean.gui.workers import PackageRemovalWorker, PackageScanWorker


class PackageTab(QWidget):
    """View for inspecting and removing orphaned or unused RPM packages."""

    def __init__(self, pkg_mgr: PackageManager):
        super().__init__()
        self.pkg_mgr = pkg_mgr
        self.suggestions: List[PackageSuggestion] = []
        self.worker: Optional[PackageScanWorker] = None
        self.removal_worker: Optional[PackageRemovalWorker] = None

        self._init_ui()

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
            "Detect unneeded RPM dependencies, older kernel versions, unused Flatpak runtimes, and disabled Snap revisions. "
            "The currently booted kernel and backup kernel are strictly protected."
        )
        desc_lbl.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        h_layout.addWidget(desc_lbl)

        h_layout.addStretch()

        self.btn_refresh = QPushButton("🔍 Analyze Packages")
        self.btn_refresh.setProperty("class", "primary")
        self.btn_refresh.clicked.connect(self.start_package_scan)
        h_layout.addWidget(self.btn_refresh)

        layout.addWidget(header_card)

        # Package Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["", "Package Name", "Version", "Size", "Category", "Status / Reason"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

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
        self.table.setRowCount(len(self.suggestions))
        total_removable_bytes = 0

        for row, s in enumerate(self.suggestions):
            # Column 0: Checkbox
            chk = QTableWidgetItem()
            if s.is_protected:
                chk.setFlags(chk.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Unchecked)
            else:
                chk.setFlags(chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Checked if s.is_selected else Qt.CheckState.Unchecked)
                total_removable_bytes += s.size_bytes
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
            if s.category == "flatpak_unused":
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

        size_mb = total_removable_bytes / (1024 * 1024)
        self.lbl_summary.setText(f"Found {len(self.suggestions)} packages ({size_mb:.2f} MB removable).")
        self.table.resizeColumnToContents(1)

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

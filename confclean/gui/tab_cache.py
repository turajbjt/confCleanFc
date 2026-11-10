"""
Cache and Junk Cleaner Tab for ConfClean FC.
Provides controls to clean thumbnails, trash, coredumps, DNF caches, and journals.
"""

from typing import List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
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

from confclean.core.cache_cleaner import CacheCategory, CacheCleaner
from confclean.gui.workers import CacheCleanWorker


class CacheTab(QWidget):
    """View for discovering and clearing cache and system junk."""

    def __init__(self, cache_cleaner: CacheCleaner):
        super().__init__()
        self.cache_cleaner = cache_cleaner
        self.categories: List[CacheCategory] = []
        self.clean_worker: Optional[CacheCleanWorker] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header description card
        header_card = QFrame()
        header_card.setProperty("class", "card")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(12, 10, 12, 10)

        desc_lbl = QLabel(
            "Clean leftover application caches, thumbnails, trash, crash dumps, and DNF metadata safely."
        )
        desc_lbl.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        header_layout.addWidget(desc_lbl)

        header_layout.addStretch()

        self.btn_rescan = QPushButton("🔄 Refresh Cache Stats")
        self.btn_rescan.clicked.connect(self.scan_caches)
        header_layout.addWidget(self.btn_rescan)

        layout.addWidget(header_card)

        # Cache Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["", "Category", "Size", "Privilege", "Description"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table, stretch=1)

        # Bottom Bar
        bottom_card = QFrame()
        bottom_card.setProperty("class", "card")
        bottom_layout = QHBoxLayout(bottom_card)
        bottom_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_total_cache = QLabel("Total Cache: 0 B")
        self.lbl_total_cache.setStyleSheet("font-weight: bold; font-size: 14px; color: #99c1f1;")
        bottom_layout.addWidget(self.lbl_total_cache)

        bottom_layout.addStretch()

        self.chk_dry_run = QCheckBox("Dry Run (Simulation)")
        self.chk_dry_run.setChecked(True)
        self.chk_dry_run.setToolTip("Simulate cache purging without deleting files (ON by default).")
        self.chk_dry_run.toggled.connect(self._on_dry_run_toggled)
        bottom_layout.addWidget(self.chk_dry_run)

        self.btn_clean_all = QPushButton("🔍 Simulate Cache Purge (Dry Run)")
        self.btn_clean_all.setProperty("class", "primary")
        self.btn_clean_all.clicked.connect(self._clean_selected_caches)
        bottom_layout.addWidget(self.btn_clean_all)

        layout.addWidget(bottom_card)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def scan_caches(self):
        """Scans cache categories and repopulates table."""
        self.categories = self.cache_cleaner.scan_categories()
        self.table.setRowCount(len(self.categories))

        total_bytes = 0

        for row, cat in enumerate(self.categories):
            total_bytes += cat.size_bytes

            can_clean = not cat.requires_root or self.cache_cleaner.is_root
            tooltip = "Root privileges required. Relaunch ConfClean FC as root via pkexec to clean this cache." if not can_clean else ""

            # Column 0: Checkbox
            chk_item = QTableWidgetItem()
            if not can_clean:
                chk_item.setFlags(chk_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable & ~Qt.ItemFlag.ItemIsEnabled)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
                chk_item.setToolTip(tooltip)
            else:
                chk_item.setFlags(chk_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk_item.setCheckState(
                    Qt.CheckState.Checked if cat.is_selected else Qt.CheckState.Unchecked
                )
            self.table.setItem(row, 0, chk_item)

            # Column 1: Name
            name_item = QTableWidgetItem(cat.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not can_clean:
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                name_item.setForeground(QColor("#6e7681"))
                name_item.setToolTip(tooltip)
            self.table.setItem(row, 1, name_item)

            # Column 2: Size
            size_item = QTableWidgetItem(cat.formatted_size)
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if not can_clean:
                size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                size_item.setForeground(QColor("#6e7681"))
                size_item.setToolTip(tooltip)
            self.table.setItem(row, 2, size_item)

            # Column 3: Privilege requirement
            priv_text = "🔒 Root Required" if cat.requires_root else "User Level"
            priv_item = QTableWidgetItem(priv_text)
            priv_item.setFlags(priv_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not can_clean:
                priv_item.setFlags(priv_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                priv_item.setForeground(QColor("#8b5e5e"))
                priv_item.setToolTip(tooltip)
            else:
                priv_item.setForeground(Qt.GlobalColor.darkGreen if not cat.requires_root else QColor("#99c1f1"))
            self.table.setItem(row, 3, priv_item)

            # Column 4: Description
            desc_text = cat.description
            if not can_clean:
                desc_text += " [Disabled: Requires root privileges]"
            desc_item = QTableWidgetItem(desc_text)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not can_clean:
                desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                desc_item.setForeground(QColor("#6e7681"))
                desc_item.setToolTip(tooltip)
            self.table.setItem(row, 4, desc_item)

        size_mb = total_bytes / (1024 * 1024)
        self.lbl_total_cache.setText(f"Total Detectable Cache: {size_mb:.2f} MB")

    def _on_dry_run_toggled(self, checked: bool):
        """Updates purge button appearance based on dry-run state."""
        if checked:
            self.btn_clean_all.setText("🔍 Simulate Cache Purge (Dry Run)")
            self.btn_clean_all.setProperty("class", "primary")
        else:
            self.btn_clean_all.setText("🧹 Purge Selected Caches")
            self.btn_clean_all.setProperty("class", "destructive")
        if self.btn_clean_all.style():
            self.btn_clean_all.style().unpolish(self.btn_clean_all)
            self.btn_clean_all.style().polish(self.btn_clean_all)

    def _clean_selected_caches(self):
        selected_cats = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                cat = self.categories[row]
                if cat.requires_root and not self.cache_cleaner.is_root:
                    continue
                selected_cats.append(cat)

        if not selected_cats:
            QMessageBox.information(self, "No Selection", "Please check at least one cache category to clean.")
            return

        is_dry_run = self.chk_dry_run.isChecked()
        total_bytes = sum(c.size_bytes for c in selected_cats)
        title = "Dry Run Simulation" if is_dry_run else "Confirm Cache Purge"
        msg = (
            f"Mode: {'SIMULATION ONLY (No files deleted)' if is_dry_run else 'PERMANENT PURGE'}\n\n"
            f"Are you sure you want to {'simulate purging' if is_dry_run else 'clean'} {len(selected_cats)} cache categories "
            f"({total_bytes / (1024*1024):.2f} MB)?"
        )

        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        reclaimed_total = 0
        for cat in selected_cats:
            reclaimed, count, msg = self.cache_cleaner.clean_category(cat, dry_run=is_dry_run)
            reclaimed_total += reclaimed

        summary_title = "Simulation Complete" if is_dry_run else "Cache Purged"
        summary_msg = (
            f"[DRY RUN] Simulation complete: {reclaimed_total / (1024*1024):.2f} MB would be reclaimed."
            if is_dry_run
            else f"Successfully cleaned caches! Reclaimed: {reclaimed_total / (1024*1024):.2f} MB"
        )
        QMessageBox.information(self, summary_title, summary_msg)
        if not is_dry_run:
            self.scan_caches()

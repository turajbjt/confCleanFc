"""
Restore and Backup Management Tab for ConfClean FC.
Enables inspecting past backups and restoring files either selectively or completely.
"""

import os
import subprocess
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from confclean.core.backup_manager import BackupManager, BackupMetadata
from confclean.core.restore_manager import RestoreManager, RestoreResult
from confclean.gui.workers import RestoreWorker


class RestoreTab(QWidget):
    """View for browsing and restoring pre-clean backup archives."""

    def __init__(self, backup_mgr: BackupManager, restore_mgr: RestoreManager):
        super().__init__()
        self.backup_mgr = backup_mgr
        self.restore_mgr = restore_mgr
        self.backups: List[BackupMetadata] = []
        self.current_backup: Optional[BackupMetadata] = None
        self.worker: Optional[RestoreWorker] = None

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
            "Every clean or reset operation creates an archived backup. "
            "You can restore files either selectively or in their entirety."
        )
        desc_lbl.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        h_layout.addWidget(desc_lbl)

        h_layout.addStretch()

        self.btn_open_folder = QPushButton("📂 Open Backup Folder")
        self.btn_open_folder.clicked.connect(self._open_backup_dir)
        h_layout.addWidget(self.btn_open_folder)

        self.btn_refresh = QPushButton("🔄 Refresh Backups")
        self.btn_refresh.clicked.connect(self.load_backups)
        h_layout.addWidget(self.btn_refresh)

        layout.addWidget(header_card)

        # Main Split View (Backups on left, archived contents on right)
        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)

        # Left: Backup Archives List
        left_frame = QFrame()
        left_frame.setProperty("class", "card")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(10, 10, 10, 10)

        left_layout.addWidget(QLabel("Available Backup Archives:"))
        self.backup_list = QListWidget()
        self.backup_list.currentItemChanged.connect(self._on_backup_selected)
        left_layout.addWidget(self.backup_list)

        self.btn_delete_backup = QPushButton("🗑️ Delete Selected Archive")
        self.btn_delete_backup.setEnabled(False)
        self.btn_delete_backup.clicked.connect(self._delete_current_backup)
        left_layout.addWidget(self.btn_delete_backup)

        split_layout.addWidget(left_frame, stretch=1)

        # Right: Archive Contents & Selective Restore
        right_frame = QFrame()
        right_frame.setProperty("class", "card")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(12, 12, 12, 12)

        self.lbl_backup_info = QLabel("Select a backup archive from the left.")
        self.lbl_backup_info.setStyleSheet("font-weight: bold; color: #99c1f1; font-size: 14px;")
        right_layout.addWidget(self.lbl_backup_info)

        # Tree of items inside backup
        self.tree_items = QTreeWidget()
        self.tree_items.setHeaderLabels(["", "Item Name", "Original Path", "Size", "Reason"])
        self.tree_items.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_items.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_items.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.tree_items.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_items.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.tree_items, stretch=1)

        # Restore Options and Buttons
        action_layout = QHBoxLayout()

        self.chk_overwrite = QCheckBox("Overwrite existing files on conflict")
        self.chk_overwrite.setChecked(True)
        action_layout.addWidget(self.chk_overwrite)

        action_layout.addStretch()

        self.btn_restore_selected = QPushButton("↩️ Restore Selected Items")
        self.btn_restore_selected.setProperty("class", "primary")
        self.btn_restore_selected.setEnabled(False)
        self.btn_restore_selected.clicked.connect(self._restore_selected)
        action_layout.addWidget(self.btn_restore_selected)

        self.btn_restore_all = QPushButton("↩️ Restore Entire Backup")
        self.btn_restore_all.setEnabled(False)
        self.btn_restore_all.clicked.connect(self._restore_entire)
        action_layout.addWidget(self.btn_restore_all)

        right_layout.addLayout(action_layout)

        split_layout.addWidget(right_frame, stretch=2)
        layout.addLayout(split_layout, stretch=1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

    def load_backups(self):
        """Loads and lists backups from disk."""
        self.backups = self.backup_mgr.list_backups()
        self.backup_list.clear()

        for b in self.backups:
            item_text = f"{b.backup_id}\n{b.created_at} | {b.formatted_size}"
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.ItemDataRole.UserRole, b)
            self.backup_list.addItem(list_item)

        if self.backups:
            self.backup_list.setCurrentRow(0)
        else:
            self.lbl_backup_info.setText("No backup archives found.")
            self.tree_items.clear()
            self.btn_delete_backup.setEnabled(False)
            self.btn_restore_selected.setEnabled(False)
            self.btn_restore_all.setEnabled(False)

    def _on_backup_selected(self, current: Optional[QListWidgetItem], previous):
        if not current:
            self.current_backup = None
            self.btn_delete_backup.setEnabled(False)
            self.btn_restore_selected.setEnabled(False)
            self.btn_restore_all.setEnabled(False)
            return

        b: BackupMetadata = current.data(Qt.ItemDataRole.UserRole)
        self.current_backup = b
        self.lbl_backup_info.setText(
            f"Archive: {b.backup_id}  |  Created: {b.created_at}  |  Size: {b.formatted_size}"
        )
        self.btn_delete_backup.setEnabled(True)
        self.btn_restore_selected.setEnabled(True)
        self.btn_restore_all.setEnabled(True)

        # Populate tree items from manifest
        self._populate_archive_items(b.archive_path)

    def _populate_archive_items(self, archive_path: str):
        self.tree_items.clear()
        items = self.restore_mgr.get_archive_items(archive_path)

        for it in items:
            tree_item = QTreeWidgetItem()
            tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            tree_item.setCheckState(0, Qt.CheckState.Checked)

            tree_item.setText(1, it.get("name", "Unknown"))
            tree_item.setText(2, it.get("original_path", ""))
            tree_item.setText(3, it.get("formatted_size", ""))
            tree_item.setText(4, it.get("reason", ""))
            tree_item.setData(0, Qt.ItemDataRole.UserRole, it)

            self.tree_items.addTopLevelItem(tree_item)

    def _open_backup_dir(self):
        try:
            subprocess.Popen(["xdg-open", self.backup_mgr.backup_dir])
        except Exception:
            pass

    def _delete_current_backup(self):
        if not self.current_backup:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete Backup",
            f"Are you sure you want to permanently delete backup '{self.current_backup.backup_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.backup_mgr.delete_backup(self.current_backup.backup_id)
            self.load_backups()

    def _restore_selected(self):
        if not self.current_backup:
            return

        selected_ids = []
        for idx in range(self.tree_items.topLevelItemCount()):
            item = self.tree_items.topLevelItem(idx)
            if item.checkState(0) == Qt.CheckState.Checked:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and "id" in data:
                    selected_ids.append(data["id"])

        if not selected_ids:
            QMessageBox.information(self, "No Selection", "Please check at least one item to restore.")
            return

        self._execute_restore(selected_ids=selected_ids)

    def _restore_entire(self):
        if not self.current_backup:
            return
        self._execute_restore(selected_ids=None)

    def _execute_restore(self, selected_ids: Optional[List[str]]):
        b = self.current_backup
        overwrite = self.chk_overwrite.isChecked()

        item_str = f"{len(selected_ids)} items" if selected_ids else "all items"
        msg = (
            f"Restore {item_str} from backup '{b.backup_id}'?\n\n"
            f"Files will be restored to their original locations.\n"
            f"Overwrite Conflicts: {'YES' if overwrite else 'NO (Skip)'}\n\n"
            f"Proceed with restoration?"
        )

        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_restore_selected.setEnabled(False)
        self.btn_restore_all.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Restoring files...")

        self.worker = RestoreWorker(
            restore_mgr=self.restore_mgr,
            archive_path=b.archive_path,
            selected_ids=selected_ids,
            destination_override=None,
            overwrite=overwrite,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, msg: str, cur: int, total: int):
        self.progress_label.setText(msg)
        if total > 0:
            self.progress_bar.setValue(int((cur / total) * 100))

    def _on_finished(self, res: RestoreResult, summary: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_restore_selected.setEnabled(True)
        self.btn_restore_all.setEnabled(True)

        QMessageBox.information(self, "Restore Finished", summary)

    def _on_failed(self, error: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_restore_selected.setEnabled(True)
        self.btn_restore_all.setEnabled(True)
        QMessageBox.critical(self, "Restore Error", f"Failed to restore: {error}")

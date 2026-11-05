"""
App Reset Tab for ConfClean FC.
Enables resetting individual applications back to fresh install defaults with automatic backups.
"""

import os
from typing import List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from confclean.core.app_resetter import AppResetProfile, AppResetter
from confclean.gui.workers import AppResetWorker, ProfileDiscoverWorker


class AppResetTab(QWidget):
    """View for restoring applications to clean out-of-the-box defaults."""

    def __init__(self, app_resetter: AppResetter):
        super().__init__()
        self.app_resetter = app_resetter
        self.profiles: List[AppResetProfile] = []
        self.current_profile: Optional[AppResetProfile] = None
        self.worker: Optional[AppResetWorker] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header description
        header_card = QFrame()
        header_card.setProperty("class", "card")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)

        desc_lbl = QLabel(
            "Reset an application to its clean install state without inheriting corrupted or old settings.\n"
            "An automatic pre-reset safety backup is always created so you can undo at any time."
        )
        desc_lbl.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        h_layout.addWidget(desc_lbl)

        h_layout.addStretch()

        self.btn_refresh = QPushButton("🔄 Refresh App List")
        self.btn_refresh.clicked.connect(self.load_profiles)
        h_layout.addWidget(self.btn_refresh)

        layout.addWidget(header_card)

        # Main Split View (List on left, details on right)
        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)

        # Left: App List
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_profile_selected)
        split_layout.addWidget(self.list_widget, stretch=1)

        # Right: Details & Reset Action
        details_frame = QFrame()
        details_frame.setProperty("class", "card")
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(12)

        self.lbl_app_name = QLabel("Select an Application")
        self.lbl_app_name.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        details_layout.addWidget(self.lbl_app_name)

        self.lbl_app_desc = QLabel("")
        self.lbl_app_desc.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        self.lbl_app_desc.setWordWrap(True)
        details_layout.addWidget(self.lbl_app_desc)

        self.lbl_app_stats = QLabel("")
        self.lbl_app_stats.setStyleSheet("font-weight: bold; color: #99c1f1;")
        details_layout.addWidget(self.lbl_app_stats)

        details_layout.addWidget(QLabel("Directories to be wiped:"))
        self.txt_paths = QTextEdit()
        self.txt_paths.setReadOnly(True)
        self.txt_paths.setStyleSheet("background-color: #1e1e1e; font-family: monospace; font-size: 12px;")
        details_layout.addWidget(self.txt_paths, stretch=1)

        # Dry Run Option
        action_row = QHBoxLayout()
        self.chk_dry_run = QCheckBox("Dry Run (Simulation)")
        self.chk_dry_run.setChecked(True)
        self.chk_dry_run.setToolTip("Simulate app reset without modifying or deleting files (ON by default).")
        self.chk_dry_run.toggled.connect(self._on_dry_run_toggled)
        action_row.addWidget(self.chk_dry_run)
        action_row.addStretch()
        details_layout.addLayout(action_row)

        # Reset button (Initialized in Dry Run simulation mode)
        self.btn_reset = QPushButton("🔍 Simulate Reset (Dry Run)")
        self.btn_reset.setProperty("class", "primary")
        self.btn_reset.setEnabled(False)
        self.btn_reset.clicked.connect(self._start_reset)
        details_layout.addWidget(self.btn_reset)

        split_layout.addWidget(details_frame, stretch=2)
        layout.addLayout(split_layout, stretch=1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

    def load_profiles(self, sync: bool = False):
        """Discovers applications with configurations."""
        if hasattr(self, "discover_worker") and self.discover_worker and self.discover_worker.isRunning():
            return

        # Synchronous fallback for headless unit tests or explicitly requested sync
        if sync or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.profiles = self.app_resetter.discover_reset_profiles()
            self._populate_profiles()
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Discovering application configuration profiles...")

        self.discover_worker = ProfileDiscoverWorker(self.app_resetter)
        self.discover_worker.finished.connect(self._on_profiles_discovered)
        self.discover_worker.failed.connect(self._on_profiles_failed)
        self.discover_worker.start()

    def _on_profiles_discovered(self, profiles: List[AppResetProfile]):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.profiles = profiles
        self._populate_profiles()

    def _on_profiles_failed(self, error: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        QMessageBox.warning(self, "Discovery Error", f"Failed to discover application profiles: {error}")

    def _populate_profiles(self):
        self.list_widget.clear()
        for prof in self.profiles:
            item = QListWidgetItem(f"{prof.name} ({prof.formatted_size})")
            item.setData(Qt.ItemDataRole.UserRole, prof)
            self.list_widget.addItem(item)

        if self.profiles:
            self.list_widget.setCurrentRow(0)

    def _on_profile_selected(self, current: Optional[QListWidgetItem], previous):
        if not current:
            self.current_profile = None
            self.btn_reset.setEnabled(False)
            return

        prof: AppResetProfile = current.data(Qt.ItemDataRole.UserRole)
        self.current_profile = prof
        self.lbl_app_name.setText(prof.name)
        self.lbl_app_desc.setText(prof.description)
        self.lbl_app_stats.setText(f"Disk Usage: {prof.formatted_size} ({prof.file_count} files)")
        self.txt_paths.setPlainText("\n".join(prof.target_paths))
        self.btn_reset.setEnabled(True)

    def _on_dry_run_toggled(self, checked: bool):
        """Updates reset button appearance and text based on dry-run state."""
        if checked:
            self.btn_reset.setText("🔍 Simulate Reset (Dry Run)")
            self.btn_reset.setProperty("class", "primary")
        else:
            self.btn_reset.setText("🔄 Reset Application to Factory Defaults")
            self.btn_reset.setProperty("class", "destructive")
        if self.btn_reset.style():
            self.btn_reset.style().unpolish(self.btn_reset)
            self.btn_reset.style().polish(self.btn_reset)

    def _start_reset(self):
        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            return
        if not self.current_profile:
            return

        prof = self.current_profile
        is_dry_run = self.chk_dry_run.isChecked()
        title = "Dry Run Simulation" if is_dry_run else "Confirm App Reset"
        msg = (
            f"Mode: {'SIMULATION ONLY (No files deleted)' if is_dry_run else 'PERMANENT RESET'}\n\n"
            f"Reset '{prof.name}' to fresh install defaults?\n\n"
            f"All configuration, cookies, local state, and cache for this app will be wiped.\n"
            f"A pre-reset backup will be automatically saved to your backups folder.\n\n"
            f"Do you want to proceed?"
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

        self.btn_reset.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText(f"{'Simulating reset for' if is_dry_run else 'Resetting'} {prof.name}...")

        self.worker = AppResetWorker(self.app_resetter, prof, dry_run=is_dry_run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, msg: str, cur: int, total: int):
        self.progress_label.setText(msg)
        if total > 0:
            self.progress_bar.setValue(int((cur / total) * 100))

    def _on_finished(self, ok: bool, b_path: str, msg: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_reset.setEnabled(True)

        if ok:
            QMessageBox.information(
                self,
                "Reset Succeeded",
                f"{msg}\n\nBackup saved at:\n{b_path}",
            )
            self.load_profiles()
        else:
            QMessageBox.critical(self, "Reset Error", msg)

    def _on_failed(self, error: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_reset.setEnabled(True)
        QMessageBox.critical(self, "Reset Error", f"Failed to reset application: {error}")

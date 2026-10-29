"""
Settings and Safelist Management Tab for ConfClean FC.
Enables configuring custom whitelist entries, backup retention, and root elevation.
"""

import os
import sys
import subprocess
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from confclean.core.safelist import SafetyEngine


class SettingsTab(QWidget):
    """View for managing custom whitelists, root privileges, and tool settings."""

    def __init__(self, safety: SafetyEngine):
        super().__init__()
        self.safety = safety
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 1. Privileges Card
        priv_card = QFrame()
        priv_card.setProperty("class", "card")
        p_layout = QHBoxLayout(priv_card)
        p_layout.setContentsMargins(14, 12, 14, 12)

        is_root = (os.geteuid() == 0)
        user_name = os.environ.get("USER", "root" if is_root else "user")
        status_text = (
            f"Current Execution Mode: <b>{'Root / System-wide Administrator' if is_root else f'User Mode ({user_name})'}</b>"
        )
        lbl_priv = QLabel(status_text)
        lbl_priv.setStyleSheet("font-size: 14px;")
        p_layout.addWidget(lbl_priv)

        p_layout.addStretch()

        if not is_root:
            self.btn_elevate = QPushButton("🛡️ Relaunch as Root (Elevate via pkexec)")
            self.btn_elevate.setProperty("class", "primary")
            self.btn_elevate.clicked.connect(self._relaunch_as_root)
            p_layout.addWidget(self.btn_elevate)

        layout.addWidget(priv_card)

        # 2. Whitelist Management Card
        wl_card = QFrame()
        wl_card.setProperty("class", "card")
        wl_layout = QVBoxLayout(wl_card)
        wl_layout.setContentsMargins(14, 12, 14, 12)
        wl_layout.setSpacing(10)

        wl_title = QLabel("Custom Protected Whitelist (Never Clean):")
        wl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
        wl_layout.addWidget(wl_title)

        wl_desc = QLabel(
            "Add folder names, absolute file paths, or wildcard patterns (e.g. 'my_custom_app*') "
            "that ConfClean FC must never delete under any circumstance."
        )
        wl_desc.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        wl_layout.addWidget(wl_desc)

        # Input and Add button
        add_layout = QHBoxLayout()
        self.txt_whitelist_input = QLineEdit()
        self.txt_whitelist_input.setPlaceholderText("Enter folder name, absolute path, or pattern...")
        add_layout.addWidget(self.txt_whitelist_input, stretch=2)

        self.btn_add_whitelist = QPushButton("➕ Add to Whitelist")
        self.btn_add_whitelist.clicked.connect(self._add_to_whitelist)
        add_layout.addWidget(self.btn_add_whitelist)

        wl_layout.addLayout(add_layout)

        # List of whitelisted items
        self.whitelist_list = QListWidget()
        wl_layout.addWidget(self.whitelist_list, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_remove_whitelist = QPushButton("Remove Selected Whitelist Entry")
        self.btn_remove_whitelist.clicked.connect(self._remove_from_whitelist)
        btn_row.addWidget(self.btn_remove_whitelist)
        btn_row.addStretch()
        wl_layout.addLayout(btn_row)

        layout.addWidget(wl_card, stretch=1)

        # 3. About & Safety Architecture Card
        about_card = QFrame()
        about_card.setProperty("class", "card")
        ab_layout = QVBoxLayout(about_card)
        ab_layout.setContentsMargins(14, 12, 14, 12)

        ab_title = QLabel("ConfClean FC - Architecture & Safety Rules")
        ab_title.setStyleSheet("font-weight: bold; color: #ffffff;")
        ab_layout.addWidget(ab_title)

        ab_text = QLabel(
            "• Optimized specifically for Fedora Linux (Workstation & Silverblue) and RPM distros (RHEL, Rocky, CentOS).\n"
            "• Every cleanup or app reset creates a compressed .tar.gz archive with a complete JSON manifest.\n"
            "• Core desktop environments (GNOME/KDE), audio/video plumbing (PipeWire), security keys (GPG/SSH/PKI), and running kernels are ironclad protected."
        )
        ab_text.setStyleSheet("color: #a0a0a0; font-size: 12px; line-height: 1.4;")
        ab_layout.addWidget(ab_text)

        layout.addWidget(about_card)

        self._refresh_whitelist_ui()

    def _refresh_whitelist_ui(self):
        self.whitelist_list.clear()
        for p in self.safety.user_whitelist:
            self.whitelist_list.addItem(p)

    def _add_to_whitelist(self):
        item = self.txt_whitelist_input.text().strip()
        if not item:
            return
        if self.safety.add_user_whitelist(item):
            self.txt_whitelist_input.clear()
            self._refresh_whitelist_ui()
            QMessageBox.information(self, "Whitelist Updated", f"Added '{item}' to custom whitelist.")

    def _remove_from_whitelist(self):
        cur = self.whitelist_list.currentItem()
        if not cur:
            return
        text = cur.text()
        if self.safety.remove_user_whitelist(text):
            self._refresh_whitelist_ui()
            QMessageBox.information(self, "Whitelist Updated", f"Removed '{text}' from custom whitelist.")

    def _relaunch_as_root(self):
        reply = QMessageBox.question(
            self,
            "Elevate Privileges",
            "This will restart ConfClean FC as root via pkexec to enable system-wide cleaning.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            script_path = os.path.abspath(sys.argv[0])
            try:
                subprocess.Popen(["pkexec", "python3", script_path])
                sys.exit(0)
            except Exception as e:
                QMessageBox.critical(self, "Elevation Failed", f"Could not launch via pkexec: {e}")

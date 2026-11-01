"""
Settings and Safelist Management Tab for ConfClean FC.
Enables configuring custom whitelist entries, backup retention, and root elevation.
"""

import os
import sys
import shutil
import subprocess
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
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


class ElevationWorker(QThread):
    """Monitors asynchronous pkexec launch and waits for child GUI readiness handshake."""

    elevation_failed = pyqtSignal(str)
    elevation_succeeded = pyqtSignal()

    def __init__(self, cmd, parent=None):
        super().__init__(parent)
        self.cmd = cmd

    def run(self):
        try:
            proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # Read first line from stdout (blocks until child flushes CONFCLEAN_ELEVATED_READY or terminates)
            line = proc.stdout.readline()
            if "CONFCLEAN_ELEVATED_READY" in line:
                self.elevation_succeeded.emit()
                return

            # Process exited or failed before displaying its GUI window
            proc.wait()
            stderr_out = proc.stderr.read().strip()
            if proc.returncode in (126, 127) or "not authorized" in stderr_out.lower() or "dismissed" in stderr_out.lower():
                self.elevation_failed.emit("cancelled")
            elif stderr_out:
                self.elevation_failed.emit(stderr_out)
            else:
                self.elevation_failed.emit(f"Process exited with code {proc.returncode}")
        except Exception as e:
            self.elevation_failed.emit(str(e))


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

        # Copyright footer
        lbl_copyright = QLabel('© <a href="https://builddesigncreate.com" style="color: #727b84; text-decoration: none;">BuildDesignCreate.com</a>')
        lbl_copyright.setOpenExternalLinks(True)
        lbl_copyright.setStyleSheet("color: #727b84; font-size: 11px; margin-top: 6px;")
        lbl_copyright.setAlignment(Qt.AlignmentFlag.AlignRight)
        ab_layout.addWidget(lbl_copyright)

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
        if os.geteuid() == 0:
            QMessageBox.information(
                self,
                "Already Elevated",
                "ConfClean FC is already running with root / administrative privileges.",
            )
            return

        pkexec_bin = shutil.which("pkexec")
        if not pkexec_bin:
            QMessageBox.critical(
                self,
                "Elevation Unavailable",
                "The 'pkexec' utility was not found. Please install the polkit package to use privilege elevation.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Elevate Privileges",
            "This will restart ConfClean FC as root via pkexec to enable system-wide cleaning.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Grant local root access to XWayland / X11 server
        try:
            subprocess.run(["xhost", "+SI:localuser:root"], capture_output=True, timeout=2, check=False)
        except Exception:
            pass

        env_bin = shutil.which("env") or "/usr/bin/env"
        env_vars = []
        for var in ["DISPLAY", "XAUTHORITY"]:
            val = os.environ.get(var)
            if val:
                env_vars.append(f"{var}={val}")

        if not any(v.startswith("DISPLAY=") for v in env_vars):
            env_vars.append("DISPLAY=:0")

        # In Wayland, root cannot connect to user's wayland-0 socket.
        # Force Qt to use XCB backend to connect to XWayland via DISPLAY.
        env_vars.append("QT_QPA_PLATFORM=xcb")

        script_path = os.path.abspath(sys.argv[0])
        target_cmd = [sys.executable, script_path, "--gui", "--elevated-child"]
        cmd = [pkexec_bin, env_bin] + env_vars + target_cmd

        if hasattr(self, "btn_elevate"):
            self.btn_elevate.setEnabled(False)
            self.btn_elevate.setText("Waiting for authorization...")

        self._elevation_worker = ElevationWorker(cmd, self)
        self._elevation_worker.elevation_succeeded.connect(self._on_elevation_succeeded)
        self._elevation_worker.elevation_failed.connect(self._on_elevation_failed)
        self._elevation_worker.start()

    def _on_elevation_succeeded(self):
        QApplication.quit()

    def _on_elevation_failed(self, error_msg: str):
        if hasattr(self, "btn_elevate"):
            self.btn_elevate.setEnabled(True)
            self.btn_elevate.setText("🛡️ Relaunch as Root (Elevate via pkexec)")

        if error_msg != "cancelled":
            QMessageBox.critical(
                self,
                "Elevation Failed",
                f"Could not launch elevated instance:\n\n{error_msg}",
            )

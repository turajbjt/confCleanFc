"""
Audit Logs Tab for ConfClean FC.
Provides real-time event broadcasting, search filtering, and log file export.
"""

import os
import subprocess
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from confclean.core.logger import AuditLogger


class LogsTab(QWidget):
    """View for viewing live and persistent audit logs."""

    def __init__(self, logger: AuditLogger):
        super().__init__()
        self.logger = logger
        self._init_ui()
        self.logger.add_listener(self._on_log_event)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header card with search & actions
        header_card = QFrame()
        header_card.setProperty("class", "card")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(10, 8, 10, 8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search log messages or filter by action...")
        self.search_input.textChanged.connect(self.refresh_logs)
        h_layout.addWidget(self.search_input, stretch=2)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.clicked.connect(self.refresh_logs)
        h_layout.addWidget(self.btn_refresh)

        self.btn_open_file = QPushButton("📄 Open Log File")
        self.btn_open_file.clicked.connect(self._open_log_file)
        h_layout.addWidget(self.btn_open_file)

        self.btn_export = QPushButton("💾 Export Logs")
        self.btn_export.clicked.connect(self._export_logs)
        h_layout.addWidget(self.btn_export)

        layout.addWidget(header_card)

        # Log Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Level", "Message"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table, stretch=1)
        self.refresh_logs()

    def _on_log_event(self, timestamp: str, level: str, message: str):
        query = self.search_input.text().lower().strip()
        if query and query not in message.lower() and query not in level.lower():
            return

        row = self.table.rowCount()
        self.table.insertRow(row)

        ts_item = QTableWidgetItem(timestamp)
        ts_item.setFlags(ts_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, ts_item)

        lvl_item = QTableWidgetItem(level)
        lvl_item.setFlags(lvl_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if level == "ERROR":
            lvl_item.setForeground(Qt.GlobalColor.red)
        elif level == "WARNING":
            lvl_item.setForeground(Qt.GlobalColor.yellow)
        else:
            lvl_item.setForeground(Qt.GlobalColor.cyan)
        self.table.setItem(row, 1, lvl_item)

        msg_item = QTableWidgetItem(message)
        msg_item.setFlags(msg_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 2, msg_item)

        self.table.scrollToBottom()

    def refresh_logs(self):
        query = self.search_input.text().lower().strip()
        records = self.logger.get_recent_logs(limit=500, query=query)
        self.table.setRowCount(len(records))

        for row, rec in enumerate(records):
            ts_item = QTableWidgetItem(rec["timestamp"])
            ts_item.setFlags(ts_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, ts_item)

            lvl_item = QTableWidgetItem(rec["level"])
            lvl_item.setFlags(lvl_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if rec["level"] == "ERROR":
                lvl_item.setForeground(Qt.GlobalColor.red)
            elif rec["level"] == "WARNING":
                lvl_item.setForeground(Qt.GlobalColor.yellow)
            else:
                lvl_item.setForeground(Qt.GlobalColor.cyan)
            self.table.setItem(row, 1, lvl_item)

            msg_item = QTableWidgetItem(rec["message"])
            msg_item.setFlags(msg_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, msg_item)

        self.table.scrollToBottom()

    def _open_log_file(self):
        log_path = self.logger.log_file
        if os.path.isfile(log_path):
            try:
                subprocess.Popen(["xdg-open", log_path])
            except Exception:
                pass
        else:
            QMessageBox.information(self, "Log File", f"Log file does not exist yet at {log_path}")

    def _export_logs(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "Export Audit Logs", "confclean_audit_log.txt", "Text Files (*.txt)")
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    for rec in self.logger.in_memory_records:
                        f.write(f"[{rec['timestamp']}] [{rec['level']}] {rec['message']}\n")
                QMessageBox.information(self, "Logs Exported", f"Successfully exported logs to {save_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export logs: {e}")

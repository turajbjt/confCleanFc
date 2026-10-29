"""
Unified Audit Logger for ConfClean FC.
Logs every scan, backup creation, deletion, package action, and restoration.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Callable, List, Optional


class AuditLogger:
    """Manages persistent disk logs and real-time GUI event broadcasting."""

    _instance = None

    @classmethod
    def reset_instance(cls):
        """Resets singleton instance for clean test execution."""
        if cls._instance is not None:
            if hasattr(cls._instance, "logger"):
                for handler in cls._instance.logger.handlers[:]:
                    handler.close()
                    cls._instance.logger.removeHandler(handler)
        cls._instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AuditLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_dir: Optional[str] = None):
        if self._initialized:
            return

        if os.geteuid() == 0:
            default_dir = "/var/log/confclean-fc"
        else:
            default_dir = os.path.expanduser("~/.local/share/confclean-fc/logs")

        self.log_dir = log_dir or default_dir
        self.log_file = os.path.join(self.log_dir, "confclean.log")
        self.listeners: List[Callable[[str, str, str], None]] = []
        self.in_memory_records: List[dict] = []

        try:
            os.makedirs(self.log_dir, exist_ok=True)
        except OSError:
            # Fallback to /tmp if permissions fail
            self.log_dir = "/tmp/confclean-fc-logs"
            self.log_file = os.path.join(self.log_dir, "confclean.log")
            os.makedirs(self.log_dir, exist_ok=True)

        self._setup_logger()
        self._initialized = True

    def _setup_logger(self):
        self.logger = logging.getLogger("ConfCleanFC")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        # File Handler
        try:
            fh = logging.FileHandler(self.log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            fh.setFormatter(file_formatter)
            self.logger.addHandler(fh)
        except OSError:
            pass

        # Console Handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        console_formatter = logging.Formatter("[ConfClean] [%(levelname)s] %(message)s")
        ch.setFormatter(console_formatter)
        self.logger.addHandler(ch)

    def add_listener(self, callback: Callable[[str, str, str], None]):
        """Registers a callback(timestamp, level, message) for real-time GUI display."""
        if callback not in self.listeners:
            self.listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, str, str], None]):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def _broadcast(self, level: str, message: str):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {"timestamp": now_str, "level": level, "message": message}
        self.in_memory_records.append(record)
        if len(self.in_memory_records) > 2000:
            self.in_memory_records.pop(0)

        for callback in self.listeners:
            try:
                callback(now_str, level, message)
            except Exception:
                pass

    def info(self, message: str):
        self.logger.info(message)
        self._broadcast("INFO", message)

    def warning(self, message: str):
        self.logger.warning(message)
        self._broadcast("WARNING", message)

    def error(self, message: str):
        self.logger.error(message)
        self._broadcast("ERROR", message)

    def audit_event(
        self,
        action: str,
        target_path: str,
        size_bytes: int = 0,
        status: str = "SUCCESS",
        backup_archive: Optional[str] = None,
        details: str = "",
    ):
        """Standardized audit log entry for deletions, backups, and restores."""
        size_str = f"{size_bytes} bytes"
        if size_bytes >= 1024 * 1024:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
        elif size_bytes >= 1024:
            size_str = f"{size_bytes / 1024:.2f} KB"

        msg_parts = [
            f"AUDIT | Action: {action.upper()}",
            f"Target: '{target_path}'",
            f"Size: {size_str}",
            f"Status: {status}",
        ]
        if backup_archive:
            msg_parts.append(f"Backup: '{os.path.basename(backup_archive)}'")
        if details:
            msg_parts.append(f"Note: {details}")

        full_msg = " | ".join(msg_parts)
        self.info(full_msg)

    def get_recent_logs(self, limit: int = 500, query: str = "") -> List[dict]:
        """Returns recent log entries optionally matching query filter."""
        results = []
        q = query.lower().strip()
        for rec in reversed(self.in_memory_records):
            if not q or q in rec["message"].lower() or q in rec["level"].lower():
                results.append(rec)
                if len(results) >= limit:
                    break
        return list(reversed(results))


def get_logger() -> AuditLogger:
    """Convenience getter for singleton AuditLogger."""
    return AuditLogger()

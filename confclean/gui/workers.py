"""
Asynchronous QThread workers for ConfClean FC.
Ensures smooth, non-blocking UI during scanning, backups, deletions, and restores.
"""

from typing import List, Optional, Set
from PyQt6.QtCore import QThread, pyqtSignal

from confclean.core.app_resetter import AppResetProfile, AppResetter
from confclean.core.backup_manager import BackupManager, BackupMetadata
from confclean.core.cache_cleaner import CacheCategory, CacheCleaner
from confclean.core.cleaner import CleanResult, SafeCleaner
from confclean.core.package_manager import PackageManager, PackageSuggestion
from confclean.core.restore_manager import RestoreManager, RestoreResult
from confclean.core.scanner import ConfigScanner, ScanItem

_ACTIVE_WORKERS: Set[QThread] = set()


class BaseWorker(QThread):
    """
    Base worker ensuring QThread references are retained globally in memory
    while executing, preventing premature Python garbage collection and Qt C++ crashes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        for sig_name in ("finished", "failed", "elevation_succeeded", "elevation_failed"):
            if hasattr(self, sig_name):
                try:
                    getattr(self, sig_name).connect(self._on_worker_completed)
                except Exception:
                    pass

    def start(self, priority: QThread.Priority = QThread.Priority.InheritPriority):
        _ACTIVE_WORKERS.add(self)
        super().start(priority)

    def _on_worker_completed(self, *args):
        _ACTIVE_WORKERS.discard(self)


class ScanWorker(BaseWorker):
    """Worker for asynchronous configuration directory scanning."""

    progress = pyqtSignal(str, int, int)  # status_msg, current, total
    finished = pyqtSignal(list)  # List[ScanItem]
    failed = pyqtSignal(str)

    def __init__(self, scanner: ConfigScanner):
        super().__init__()
        self.scanner = scanner

    def run(self):
        try:
            items = self.scanner.scan_all(
                progress_callback=lambda msg, cur, tot: self.progress.emit(msg, cur, tot)
            )
            self.finished.emit(items)
        except Exception as e:
            self.failed.emit(str(e))


class CleanWorker(BaseWorker):
    """Worker for asynchronous file cleaning with pre-backup."""

    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(object, str)  # CleanResult, summary_msg
    failed = pyqtSignal(str)

    def __init__(self, cleaner: SafeCleaner, items: List[ScanItem], create_backup: bool, dry_run: bool):
        super().__init__()
        self.cleaner = cleaner
        self.items = items
        self.create_backup = create_backup
        self.dry_run = dry_run

    def run(self):
        try:
            result, summary = self.cleaner.clean_items(
                self.items,
                create_backup=self.create_backup,
                dry_run=self.dry_run,
                progress_callback=lambda msg, cur, tot: self.progress.emit(msg, cur, tot),
            )
            self.finished.emit(result, summary)
        except Exception as e:
            self.failed.emit(str(e))


class PackageScanWorker(BaseWorker):
    """Worker for DNF package and kernel suggestion queries."""

    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list)  # List[PackageSuggestion]
    failed = pyqtSignal(str)

    def __init__(self, pkg_mgr: PackageManager):
        super().__init__()
        self.pkg_mgr = pkg_mgr

    def run(self):
        try:
            suggestions = self.pkg_mgr.scan_all_suggestions(
                progress_callback=lambda msg, cur, tot: self.progress.emit(msg, cur, tot)
            )
            self.finished.emit(suggestions)
        except Exception as e:
            self.failed.emit(str(e))


class CacheCleanWorker(BaseWorker):
    """Worker for purging cache categories."""

    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(int, int, str)  # bytes_reclaimed, items_removed, msg
    failed = pyqtSignal(str)

    def __init__(self, cache_cleaner: CacheCleaner, category: CacheCategory, dry_run: bool = True):
        super().__init__()
        self.cache_cleaner = cache_cleaner
        self.category = category
        self.dry_run = dry_run

    def run(self):
        try:
            b, c, msg = self.cache_cleaner.clean_category(
                self.category,
                dry_run=self.dry_run,
                progress_callback=lambda msg, cur, tot: self.progress.emit(msg, cur, tot),
            )
            self.finished.emit(b, c, msg)
        except Exception as e:
            self.failed.emit(str(e))


class AppResetWorker(BaseWorker):
    """Worker for resetting application to factory defaults."""

    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(bool, str, str)  # ok, backup_path, msg
    failed = pyqtSignal(str)

    def __init__(self, resetter: AppResetter, profile: AppResetProfile, dry_run: bool = True):
        super().__init__()
        self.resetter = resetter
        self.profile = profile
        self.dry_run = dry_run

    def run(self):
        try:
            ok, b_path, msg = self.resetter.reset_app(
                self.profile,
                create_backup=True,
                dry_run=self.dry_run,
                progress_callback=lambda msg, cur, tot: self.progress.emit(msg, cur, tot),
            )
            self.finished.emit(ok, b_path or "", msg)
        except Exception as e:
            self.failed.emit(str(e))


class RestoreWorker(BaseWorker):
    """Worker for restoring backup archives."""

    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(object, str)  # RestoreResult, summary_msg
    failed = pyqtSignal(str)

    def __init__(
        self,
        restore_mgr: RestoreManager,
        archive_path: str,
        selected_ids: Optional[List[str]] = None,
        destination_override: Optional[str] = None,
        overwrite: bool = True,
    ):
        super().__init__()
        self.restore_mgr = restore_mgr
        self.archive_path = archive_path
        self.selected_ids = selected_ids
        self.destination_override = destination_override
        self.overwrite = overwrite

    def run(self):
        try:
            res, summary = self.restore_mgr.restore(
                self.archive_path,
                selected_item_ids=self.selected_ids,
                destination_override=self.destination_override,
                overwrite_existing=self.overwrite,
                progress_callback=lambda msg, cur, tot: self.progress.emit(msg, cur, tot),
            )
            self.finished.emit(res, summary)
        except Exception as e:
            self.failed.emit(str(e))


class BackupListWorker(BaseWorker):
    """Worker for asynchronously discovering and listing backup archives."""

    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list)  # List[BackupMetadata]
    failed = pyqtSignal(str)

    def __init__(self, backup_mgr: BackupManager):
        super().__init__()
        self.backup_mgr = backup_mgr

    def run(self):
        try:
            backups = self.backup_mgr.list_backups()
            self.finished.emit(backups)
        except Exception as e:
            self.failed.emit(str(e))


class ArchiveInspectWorker(BaseWorker):
    """Worker for asynchronously inspecting items inside a backup archive."""

    finished = pyqtSignal(str, list)  # archive_path, List[dict]
    failed = pyqtSignal(str, str)     # archive_path, error_msg

    def __init__(self, restore_mgr: RestoreManager, archive_path: str):
        super().__init__()
        self.restore_mgr = restore_mgr
        self.archive_path = archive_path

    def run(self):
        try:
            items = self.restore_mgr.get_archive_items(self.archive_path)
            self.finished.emit(self.archive_path, items)
        except Exception as e:
            self.failed.emit(self.archive_path, str(e))


class PackageRemovalWorker(BaseWorker):
    """Worker for executing package removal commands asynchronously in background."""

    finished = pyqtSignal(int, str)  # returncode, output
    failed = pyqtSignal(str)

    def __init__(self, cmd: List[str]):
        super().__init__()
        self.cmd = cmd

    def run(self):
        import subprocess

        try:
            res = subprocess.run(
                self.cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            out = res.stdout or ""
            err = res.stderr or ""
            combined = (out + "\n" + err).strip()
            self.finished.emit(res.returncode, combined)
        except Exception as e:
            self.failed.emit(str(e))


class SELinuxWorker(BaseWorker):
    """Worker for executing SELinux fix/cancel operations asynchronously without blocking GUI."""

    finished = pyqtSignal(bool, str)  # success, message
    failed = pyqtSignal(str)

    def __init__(self, action: str, selinux_mgr, parent=None):
        super().__init__(parent)
        self.action = action  # "schedule" or "cancel"
        self.selinux_mgr = selinux_mgr

    def run(self):
        try:
            if self.action == "schedule":
                success, msg = self.selinux_mgr.schedule_onboot_fix(boottime_only=True, use_pkexec=True)
            elif self.action == "cancel":
                success, msg = self.selinux_mgr.cancel_onboot_fix(use_pkexec=True)
            else:
                success, msg = False, f"Unknown action: {self.action}"
            self.finished.emit(success, msg)
        except Exception as e:
            self.failed.emit(str(e))


class ProfileDiscoverWorker(BaseWorker):
    """Worker for asynchronously discovering applications with configurations."""

    finished = pyqtSignal(list)  # List[AppResetProfile]
    failed = pyqtSignal(str)

    def __init__(self, resetter: AppResetter):
        super().__init__()
        self.resetter = resetter

    def run(self):
        try:
            profiles = self.resetter.discover_reset_profiles()
            self.finished.emit(profiles)
        except Exception as e:
            self.failed.emit(str(e))


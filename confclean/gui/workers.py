"""
Asynchronous QThread workers for ConfClean FC.
Ensures smooth, non-blocking UI during scanning, backups, deletions, and restores.
"""

from typing import List, Optional
from PyQt6.QtCore import QThread, pyqtSignal

from confclean.core.app_resetter import AppResetProfile, AppResetter
from confclean.core.cache_cleaner import CacheCategory, CacheCleaner
from confclean.core.cleaner import CleanResult, SafeCleaner
from confclean.core.package_manager import PackageManager, PackageSuggestion
from confclean.core.restore_manager import RestoreManager, RestoreResult
from confclean.core.scanner import ConfigScanner, ScanItem


class ScanWorker(QThread):
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


class CleanWorker(QThread):
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


class PackageScanWorker(QThread):
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


class CacheCleanWorker(QThread):
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


class AppResetWorker(QThread):
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


class RestoreWorker(QThread):
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

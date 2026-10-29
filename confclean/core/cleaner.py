"""
Safe Cleaning Engine for ConfClean FC.
Executes deletions strictly according to safelist verification, pre-deletion backups,
dry-run checks, and audit logging.
"""

import os
import shutil
from typing import Callable, List, Optional, Tuple

from confclean.core.backup_manager import BackupManager
from confclean.core.logger import get_logger
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ScanItem


class CleanResult:
    """Stores the outcome of a clean operation."""

    def __init__(self):
        self.deleted_items: List[ScanItem] = []
        self.failed_items: List[Tuple[ScanItem, str]] = []
        self.blocked_items: List[Tuple[ScanItem, str]] = []
        self.total_reclaimed_bytes: int = 0
        self.backup_archive_path: Optional[str] = None
        self.backup_log_path: Optional[str] = None
        self.is_dry_run: bool = False

    @property
    def formatted_reclaimed_size(self) -> str:
        size = float(self.total_reclaimed_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"


class SafeCleaner:
    """Executes safe cleaning workflows with mandatory checks."""

    def __init__(
        self,
        safety: Optional[SafetyEngine] = None,
        backup_mgr: Optional[BackupManager] = None,
    ):
        self.safety = safety or SafetyEngine()
        self.backup_mgr = backup_mgr or BackupManager()
        self.logger = get_logger()

    def clean_items(
        self,
        items: List[ScanItem],
        create_backup: bool = True,
        dry_run: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Tuple[CleanResult, str]:
        """
        Executes safe deletion of the given items.
        Returns:
            (CleanResult, summary_message: str)
        """
        result = CleanResult()
        result.is_dry_run = dry_run

        if not items:
            return result, "No items provided for cleaning"

        # 1. Filter and enforce absolute safelist verification
        safe_candidates: List[ScanItem] = []
        for it in items:
            is_prot, reason = self.safety.is_safelisted(it.path)
            if is_prot:
                self.logger.warning(f"BLOCKED deletion attempt on protected path: {it.path} ({reason})")
                result.blocked_items.append((it, f"Protected by Safelist: {reason}"))
            else:
                safe_candidates.append(it)

        if not safe_candidates:
            return result, "All selected items are protected by the safelist. No items deleted."

        # 2. Dry run handling
        if dry_run:
            self.logger.info(f"DRY RUN: Simulating deletion for {len(safe_candidates)} items")
            for it in safe_candidates:
                result.deleted_items.append(it)
                result.total_reclaimed_bytes += it.size_bytes
                self.logger.info(f"[DRY-RUN WOULD DELETE] {it.path} ({it.formatted_size})")

            summary = (
                f"Dry run complete: {len(result.deleted_items)} items would be cleaned "
                f"({result.formatted_reclaimed_size} reclaimable)."
            )
            return result, summary

        # 3. Create Backup Archive first (if requested)
        if create_backup:
            self.logger.info("Creating pre-deletion safety backup archive...")
            if progress_callback:
                progress_callback("Creating pre-deletion backup archive...", 0, len(safe_candidates))

            ok, arch_path, log_p, b_msg = self.backup_mgr.create_backup(
                safe_candidates,
                label="pre_clean",
                progress_callback=progress_callback,
            )
            if not ok:
                err_msg = f"ABORTED: Pre-deletion backup creation failed! No files were deleted. Reason: {b_msg}"
                self.logger.error(err_msg)
                return result, err_msg

            result.backup_archive_path = arch_path
            result.backup_log_path = log_p
            self.logger.info(f"Backup created at: {arch_path}")

        # 4. Perform Deletions
        total = len(safe_candidates)
        for idx, it in enumerate(safe_candidates):
            if progress_callback:
                progress_callback(f"Cleaning {it.name}...", idx + 1, total)

            if not os.path.exists(it.path) and not os.path.islink(it.path):
                # Path already gone
                continue

            try:
                # Double check safety before unlinking
                is_prot, _ = self.safety.is_safelisted(it.path)
                if is_prot:
                    continue

                if os.path.isdir(it.path) and not os.path.islink(it.path):
                    shutil.rmtree(it.path)
                else:
                    os.remove(it.path)

                result.deleted_items.append(it)
                result.total_reclaimed_bytes += it.size_bytes

                self.logger.audit_event(
                    action="DELETED",
                    target_path=it.path,
                    size_bytes=it.size_bytes,
                    status="SUCCESS",
                    backup_archive=result.backup_archive_path,
                    details=f"Reason: {it.reason}",
                )

            except Exception as e:
                err_str = f"Error deleting {it.path}: {e}"
                self.logger.error(err_str)
                result.failed_items.append((it, str(e)))

        summary = (
            f"Cleanup finished: {len(result.deleted_items)} items deleted "
            f"({result.formatted_reclaimed_size} reclaimed), {len(result.failed_items)} errors, "
            f"{len(result.blocked_items)} protected."
        )
        self.logger.info(summary)
        return result, summary

"""
Selective and Complete Restore Engine for ConfClean FC.
Restores backed up configurations, directories, and files to their original
or custom locations safely, handling conflicts and permissions.
"""

import json
import os
import shutil
import tarfile
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.logger import get_logger


class RestoreResult:
    """Summary of a restore operation."""

    def __init__(self):
        self.restored_items: List[str] = []
        self.skipped_items: List[str] = []
        self.failed_items: List[Tuple[str, str]] = []
        self.total_bytes_restored: int = 0

    @property
    def success(self) -> bool:
        return len(self.failed_items) == 0 and len(self.restored_items) > 0


class RestoreManager:
    """Handles parsing backup contents and executing selective/whole restores."""

    def __init__(self):
        self.logger = get_logger()

    def get_archive_items(self, archive_path: str) -> List[dict]:
        """Reads and returns the list of item dictionaries from manifest.json inside archive or disk companion."""
        if not os.path.isfile(archive_path):
            return []

        # 1. Fast check for companion manifest on disk (<1ms)
        manifest_disk_path = None
        if archive_path.endswith(".tar.gz"):
            manifest_disk_path = archive_path[:-7] + ".manifest.json"
        elif archive_path.endswith(".tgz"):
            manifest_disk_path = archive_path[:-4] + ".manifest.json"

        if manifest_disk_path and os.path.isfile(manifest_disk_path):
            try:
                with open(manifest_disk_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("items", [])
            except Exception as e:
                self.logger.warning(f"Could not read companion manifest {manifest_disk_path}: {e}")

        # 2. Extract from tarball streaming without full getmembers()
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                manifest_file = None
                for m in tar:
                    if m.name == "manifest.json":
                        manifest_file = tar.extractfile(m)
                        break

                if manifest_file:
                    data = json.load(manifest_file)
                    # Cache companion manifest to disk for instant future queries
                    if manifest_disk_path:
                        try:
                            with open(manifest_disk_path, "w", encoding="utf-8") as f_out:
                                json.dump(data, f_out, indent=2)
                        except OSError:
                            pass
                    return data.get("items", [])
        except Exception as e:
            self.logger.error(f"Failed to read archive items from {archive_path}: {e}")

        return []

    def restore(
        self,
        archive_path: str,
        selected_item_ids: Optional[List[str]] = None,
        destination_override: Optional[str] = None,
        overwrite_existing: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Tuple[RestoreResult, str]:
        """
        Executes restore of selected items (or all items if selected_item_ids is None).
        Returns:
            (RestoreResult, message: str)
        """
        result = RestoreResult()
        if not os.path.isfile(archive_path):
            return result, f"Backup archive not found: {archive_path}"

        items = self.get_archive_items(archive_path)
        if not items:
            return result, "No items found in backup manifest"

        # Filter items if specific IDs requested
        if selected_item_ids:
            target_ids = set(selected_item_ids)
            items_to_restore = [item for item in items if item.get("id") in target_ids]
        else:
            items_to_restore = items

        if not items_to_restore:
            return result, "No matching items selected for restore"

        self.logger.info(
            f"Starting restore of {len(items_to_restore)} items from '{os.path.basename(archive_path)}'"
        )

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                all_members = {m.name: m for m in tar.getmembers()}
                total = len(items_to_restore)

                for idx, item in enumerate(items_to_restore):
                    orig_path = item.get("original_path", "")
                    archive_relpath = item.get("archive_relpath", "")
                    item_name = item.get("name", os.path.basename(orig_path))

                    if progress_callback:
                        progress_callback(f"Restoring {item_name}...", idx + 1, total)

                    if not orig_path or not archive_relpath:
                        result.failed_items.append((item_name, "Invalid item manifest"))
                        continue

                    # Determine target path
                    if destination_override:
                        target_path = os.path.join(destination_override, os.path.basename(orig_path))
                    else:
                        target_path = orig_path

                    # Handle conflicts
                    if os.path.exists(target_path):
                        if not overwrite_existing:
                            self.logger.info(f"Skipping existing item during restore: {target_path}")
                            result.skipped_items.append(target_path)
                            continue
                        else:
                            # Safely replace existing
                            try:
                                if os.path.isdir(target_path) and not os.path.islink(target_path):
                                    shutil.rmtree(target_path)
                                else:
                                    os.remove(target_path)
                            except OSError as e:
                                err_msg = f"Failed to remove existing file before restore: {e}"
                                self.logger.error(err_msg)
                                result.failed_items.append((target_path, err_msg))
                                continue

                    # Create parent directories
                    parent_dir = os.path.dirname(target_path)
                    try:
                        os.makedirs(parent_dir, exist_ok=True)
                    except OSError as e:
                        err_msg = f"Failed to create directory {parent_dir}: {e}"
                        self.logger.error(err_msg)
                        result.failed_items.append((target_path, err_msg))
                        continue

                    # Extract all members belonging to this item
                    item_members = [
                        m for name, m in all_members.items()
                        if name == archive_relpath or name.startswith(archive_relpath.rstrip("/") + "/")
                    ]

                    if not item_members:
                        result.failed_items.append((target_path, "Archived files missing from tarball"))
                        continue

                    try:
                        # Extract members adjusting arcname to target_path
                        for m in item_members:
                            rel_sub = os.path.relpath(m.name, archive_relpath)
                            if rel_sub == ".":
                                member_dest = target_path
                            else:
                                member_dest = os.path.join(target_path, rel_sub)

                            if m.isdir():
                                os.makedirs(member_dest, exist_ok=True)
                            elif m.isreg():
                                os.makedirs(os.path.dirname(member_dest), exist_ok=True)
                                fileobj = tar.extractfile(m)
                                if fileobj:
                                    with open(member_dest, "wb") as out_f:
                                        shutil.copyfileobj(fileobj, out_f)
                                    result.total_bytes_restored += m.size
                            elif m.issym():
                                os.makedirs(os.path.dirname(member_dest), exist_ok=True)
                                if os.path.lexists(member_dest):
                                    os.remove(member_dest)
                                os.symlink(m.linkname, member_dest)

                        result.restored_items.append(target_path)
                        self.logger.audit_event(
                            action="RESTORE",
                            target_path=target_path,
                            size_bytes=item.get("size_bytes", 0),
                            status="SUCCESS",
                            backup_archive=archive_path,
                            details=f"Restored to {'custom location' if destination_override else 'original location'}",
                        )

                    except Exception as e:
                        err_msg = f"Extraction failed: {e}"
                        self.logger.error(err_msg)
                        result.failed_items.append((target_path, err_msg))

            summary = (
                f"Restore completed: {len(result.restored_items)} restored, "
                f"{len(result.skipped_items)} skipped, {len(result.failed_items)} errors."
            )
            self.logger.info(summary)
            return result, summary

        except Exception as e:
            err_msg = f"Failed to process archive for restore: {e}"
            self.logger.error(err_msg)
            return result, err_msg

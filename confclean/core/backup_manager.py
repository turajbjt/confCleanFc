"""
Pre-Deletion Backup Manager for ConfClean FC.
Safely compresses items targeted for deletion into structured .tar.gz archives
with JSON manifests and companion deletion audit logs.
"""

import json
import os
import shutil
import tarfile
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.logger import get_logger
from confclean.core.scanner import ScanItem, get_path_stats


class BackupMetadata:
    """Metadata container for an individual backup archive."""

    def __init__(
        self,
        backup_id: str,
        archive_path: str,
        log_path: str,
        created_at: str,
        user: str,
        item_count: int,
        total_size_bytes: int,
        manifest_data: Optional[dict] = None,
    ):
        self.backup_id = backup_id
        self.archive_path = archive_path
        self.log_path = log_path
        self.created_at = created_at
        self.user = user
        self.item_count = item_count
        self.total_size_bytes = total_size_bytes
        self.manifest_data = manifest_data or {}

    @property
    def formatted_size(self) -> str:
        size = float(self.total_size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"


class BackupManager:
    """Handles creation, verification, and discovery of backup archives."""

    def __init__(self, backup_dir: Optional[str] = None):
        self.logger = get_logger()
        if backup_dir:
            self.backup_dir = backup_dir
        elif os.geteuid() == 0:
            self.backup_dir = "/var/backups/confclean-fc"
        else:
            self.backup_dir = os.path.expanduser("~/.local/share/confclean-fc/backups")

        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except OSError:
            self.backup_dir = "/tmp/confclean-fc-backups"
            os.makedirs(self.backup_dir, exist_ok=True)

    def list_backups(self) -> List[BackupMetadata]:
        """Discovers and parses all existing backup archives in backup_dir."""
        results: List[BackupMetadata] = []
        if not os.path.isdir(self.backup_dir):
            return results

        try:
            for entry in sorted(os.listdir(self.backup_dir), reverse=True):
                if entry.endswith(".tar.gz") and entry.startswith("confclean_backup_"):
                    archive_path = os.path.join(self.backup_dir, entry)
                    base_id = entry[:-7]  # remove .tar.gz
                    log_path = os.path.join(self.backup_dir, f"{base_id}.log")

                    meta = self._read_archive_manifest(archive_path, base_id, log_path)
                    if meta:
                        results.append(meta)
        except OSError as e:
            self.logger.error(f"Failed to list backups: {e}")

        return results

    def _read_archive_manifest(self, archive_path: str, backup_id: str, log_path: str) -> Optional[BackupMetadata]:
        """Extracts and parses manifest directly from companion manifest or archive without full extraction."""
        manifest_disk_path = os.path.join(self.backup_dir, f"{backup_id}.manifest.json")

        # 1. Fast path: Read companion JSON manifest from disk (<1ms)
        if os.path.isfile(manifest_disk_path):
            try:
                with open(manifest_disk_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return BackupMetadata(
                        backup_id=data.get("backup_id", backup_id),
                        archive_path=archive_path,
                        log_path=log_path,
                        created_at=data.get("created_at", "Unknown"),
                        user=data.get("user", "Unknown"),
                        item_count=data.get("total_items", len(data.get("items", []))),
                        total_size_bytes=data.get("total_size_bytes", os.path.getsize(archive_path)),
                        manifest_data=data,
                    )
            except Exception as e:
                self.logger.warning(f"Could not read companion manifest {manifest_disk_path}: {e}")

        # 2. Archive streaming search (avoids tar.getmembers() exhaustive list creation)
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                manifest_file = None
                for member in tar:
                    if member.name == "manifest.json":
                        manifest_file = tar.extractfile(member)
                        break

                if manifest_file:
                    data = json.load(manifest_file)
                    # Cache companion manifest to disk for instant future reads
                    try:
                        with open(manifest_disk_path, "w", encoding="utf-8") as f_cache:
                            json.dump(data, f_cache, indent=2)
                    except OSError:
                        pass

                    return BackupMetadata(
                        backup_id=data.get("backup_id", backup_id),
                        archive_path=archive_path,
                        log_path=log_path,
                        created_at=data.get("created_at", "Unknown"),
                        user=data.get("user", "Unknown"),
                        item_count=data.get("total_items", len(data.get("items", []))),
                        total_size_bytes=data.get("total_size_bytes", os.path.getsize(archive_path)),
                        manifest_data=data,
                    )
        except Exception as e:
            self.logger.warning(f"Could not read manifest from {archive_path}: {e}")

        # 3. Fallback if manifest is missing or damaged
        try:
            stat = os.stat(archive_path)
            dt = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            return BackupMetadata(
                backup_id=backup_id,
                archive_path=archive_path,
                log_path=log_path,
                created_at=dt,
                user="unknown",
                item_count=0,
                total_size_bytes=stat.st_size,
            )
        except OSError:
            return None

    def create_backup(
        self,
        items_to_backup: List[ScanItem],
        label: str = "pre_clean",
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        Creates a .tar.gz archive and companion log file for the specified items.
        Returns:
            (success: bool, archive_path: Optional[str], log_path: Optional[str], message: str)
        """
        if not items_to_backup:
            return False, None, None, "No items selected for backup"

        # Check total size and available disk space
        total_size = sum(item.size_bytes for item in items_to_backup)
        try:
            stat_vfs = shutil.disk_usage(self.backup_dir)
            # Ensure at least 1.5x of estimated size plus 100MB is free
            required_free = int(total_size * 1.5) + (100 * 1024 * 1024)
            if stat_vfs.free < required_free:
                return (
                    False,
                    None,
                    None,
                    f"Insufficient free disk space in backup directory. Free: {stat_vfs.free // (1024*1024)} MB, Required: {required_free // (1024*1024)} MB",
                )
        except OSError:
            pass

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"confclean_backup_{timestamp}"
        archive_name = f"{backup_id}.tar.gz"
        archive_path = os.path.join(self.backup_dir, archive_name)
        log_name = f"{backup_id}.log"
        log_path = os.path.join(self.backup_dir, log_name)
        manifest_name = f"{backup_id}.manifest.json"
        manifest_disk_path = os.path.join(self.backup_dir, manifest_name)

        manifest = {
            "backup_id": backup_id,
            "label": label,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": time.time(),
            "user": os.environ.get("USER", "root"),
            "total_items": len(items_to_backup),
            "total_size_bytes": total_size,
            "items": [],
        }

        log_lines = [
            "=" * 70,
            f" ConfClean FC - Pre-Clean Backup & Deletion Manifest Log",
            f" Backup Archive: {archive_name}",
            f" Date: {manifest['created_at']} | User: {manifest['user']}",
            f" Total Target Items: {len(items_to_backup)} | Estimated Size: {total_size / (1024*1024):.2f} MB",
            "=" * 70,
            "",
            "Archived Items Slated for Deletion:",
        ]

        # Pre-build item metadata so manifest can be placed at the very front of the archive
        items_meta = []
        for idx, item in enumerate(items_to_backup):
            item_id = f"item_{idx + 1:04d}"
            archive_relpath = f"data/{item_id}/{os.path.basename(item.path)}"
            mode_str = "0755"
            try:
                st = os.stat(item.path)
                mode_str = oct(st.st_mode)[-4:]
            except OSError:
                pass

            manifest_item = {
                "id": item_id,
                "name": item.name,
                "original_path": item.path,
                "category": item.category,
                "is_directory": item.is_directory,
                "size_bytes": item.size_bytes,
                "formatted_size": item.formatted_size,
                "archive_relpath": archive_relpath,
                "permissions": mode_str,
                "reason": item.reason,
            }
            manifest["items"].append(manifest_item)
            items_meta.append((item, archive_relpath))

            log_lines.append(
                f"[{idx+1:03d}] DELETED_TARGET: {item.path} ({item.formatted_size})\n"
                f"      Category: {item.category} | Type: {'Directory' if item.is_directory else 'File'}\n"
                f"      Reason: {item.reason}\n"
                f"      Archive Location: {archive_relpath}\n"
            )

        self.logger.info(f"Initiating pre-clean backup for {len(items_to_backup)} items into {archive_path}")

        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                # 1. Place manifest.json as FIRST entry in the archive for instant header lookup
                import io

                manifest_json_bytes = json.dumps(manifest, indent=2).encode("utf-8")
                tarinfo = tarfile.TarInfo(name="manifest.json")
                tarinfo.size = len(manifest_json_bytes)
                tarinfo.mtime = time.time()
                tar.addfile(tarinfo, io.BytesIO(manifest_json_bytes))

                # 2. Add each item to the archive
                total_items = len(items_to_backup)
                for idx, (item, archive_relpath) in enumerate(items_meta):
                    if progress_callback:
                        progress_callback(f"Backing up {item.name}...", idx + 1, total_items)

                    if os.path.exists(item.path):
                        tar.add(item.path, arcname=archive_relpath, recursive=True)

            # Write companion JSON manifest on disk for instant reading (<1ms)
            with open(manifest_disk_path, "w", encoding="utf-8") as f_manifest:
                json.dump(manifest, f_manifest, indent=2)

            # Write companion human-readable .log file on disk
            log_lines.append("-" * 70)
            log_lines.append(f"Backup archive created successfully at: {archive_path}")
            log_lines.append(f"Archive file size: {os.path.getsize(archive_path) / (1024*1024):.2f} MB")
            log_lines.append("=" * 70)

            with open(log_path, "w", encoding="utf-8") as f_log:
                f_log.write("\n".join(log_lines) + "\n")

            self.logger.audit_event(
                action="BACKUP_CREATED",
                target_path=archive_path,
                size_bytes=os.path.getsize(archive_path),
                status="SUCCESS",
                details=f"Contains {len(items_to_backup)} items",
            )

            return True, archive_path, log_path, f"Backup created successfully: {archive_name}"

        except Exception as e:
            self.logger.error(f"Failed to create backup archive: {e}")
            if os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except OSError:
                    pass
            if os.path.exists(manifest_disk_path):
                try:
                    os.remove(manifest_disk_path)
                except OSError:
                    pass
            return False, None, None, f"Backup creation failed: {e}"

    def delete_backup(self, backup_id: str) -> bool:
        """Deletes a backup archive and its corresponding log and manifest files."""
        archive_path = os.path.join(self.backup_dir, f"{backup_id}.tar.gz")
        log_path = os.path.join(self.backup_dir, f"{backup_id}.log")
        manifest_path = os.path.join(self.backup_dir, f"{backup_id}.manifest.json")
        try:
            if os.path.exists(archive_path):
                os.remove(archive_path)
            if os.path.exists(log_path):
                os.remove(log_path)
            if os.path.exists(manifest_path):
                os.remove(manifest_path)
            self.logger.info(f"Deleted backup archive: {backup_id}")
            return True
        except OSError as e:
            self.logger.error(f"Failed to delete backup {backup_id}: {e}")
            return False

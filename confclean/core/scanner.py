"""
Deep Configuration Scanner for ConfClean FC.
Scans user-space and system configuration directories to identify orphaned and leftover files.
"""

import os
import sys
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.detector import SystemDetector
from confclean.core.safelist import SafetyEngine


class ScanItem:
    """Represents a scanned file or directory item."""

    def __init__(
        self,
        path: str,
        name: str,
        category: str,
        is_directory: bool,
        size_bytes: int,
        file_count: int,
        last_modified: float,
        status: str,
        reason: str,
        suggested_action: str = "keep",
        is_selected: bool = False,
    ):
        self.path = path
        self.name = name
        self.category = category  # e.g. "config", "local_share", "flatpak", "dotfile", "etc"
        self.is_directory = is_directory
        self.size_bytes = size_bytes
        self.file_count = file_count
        self.last_modified = last_modified
        self.status = status  # "CONFIRMED_ORPHAN", "PROBABLE_ORPHAN", "ACTIVE_APP", "PROTECTED"
        self.reason = reason
        self.suggested_action = suggested_action  # "clean", "review", "keep"
        self.is_selected = is_selected

    @property
    def formatted_size(self) -> str:
        """Returns human-readable size string."""
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                if unit in ["B"]:
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"

    @property
    def formatted_date(self) -> str:
        """Returns human-readable last modified date string."""
        if self.last_modified <= 0:
            return "Unknown"
        try:
            return datetime.fromtimestamp(self.last_modified).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "Unknown"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "category": self.category,
            "is_directory": self.is_directory,
            "size_bytes": self.size_bytes,
            "formatted_size": self.formatted_size,
            "file_count": self.file_count,
            "last_modified": self.last_modified,
            "formatted_date": self.formatted_date,
            "status": self.status,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "is_selected": self.is_selected,
        }


def get_path_stats(path: str) -> Tuple[int, int, float]:
    """Calculates total size, file count, and most recent modified time of a path."""
    total_size = 0
    file_count = 0
    latest_mtime = 0.0

    try:
        if os.path.islink(path):
            stat = os.lstat(path)
            return stat.st_size, 1, stat.st_mtime

        if os.path.isfile(path):
            stat = os.stat(path)
            return stat.st_size, 1, stat.st_mtime

        if os.path.isdir(path):
            stat = os.stat(path)
            latest_mtime = stat.st_mtime
            for root, dirs, files in os.walk(path, followlinks=False):
                file_count += len(files)
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        fstat = os.lstat(fp)
                        total_size += fstat.st_size
                        if fstat.st_mtime > latest_mtime:
                            latest_mtime = fstat.st_mtime
                    except (OSError, PermissionError):
                        continue
            return total_size, file_count, latest_mtime
    except (OSError, PermissionError):
        pass

    return 0, 0, 0.0


class ConfigScanner:
    """Orchestrates scanning of config paths, cross-referencing with detector and safelist."""

    def __init__(self, detector: Optional[SystemDetector] = None, safety: Optional[SafetyEngine] = None):
        self.detector = detector or SystemDetector()
        self.safety = safety or SafetyEngine()

    def scan_all(
        self,
        include_user_configs: bool = True,
        include_flatpaks: bool = True,
        include_dotfiles: bool = True,
        include_system_etc: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[ScanItem]:
        """
        Executes complete scan across all configured scopes.
        Calls progress_callback(status_message, current, total) periodically.
        """
        targets = []

        user_home = os.path.expanduser("~")

        if include_user_configs:
            targets.append((os.path.join(user_home, ".config"), "User Config (~/.config)", "config"))
            targets.append((os.path.join(user_home, ".local", "share"), "User Data (~/.local/share)", "local_share"))
            targets.append((os.path.join(user_home, ".local", "state"), "User State (~/.local/state)", "local_state"))

        if include_flatpaks:
            targets.append((os.path.join(user_home, ".var", "app"), "Flatpak Data (~/.var/app)", "flatpak"))

        items: List[ScanItem] = []
        all_candidate_paths = []

        # Collect paths to scan
        for base_dir, label, category in targets:
            if not os.path.isdir(base_dir):
                continue
            try:
                for entry in sorted(os.listdir(base_dir)):
                    full_p = os.path.join(base_dir, entry)
                    all_candidate_paths.append((full_p, entry, category))
            except (OSError, PermissionError):
                continue

        # Check Home dotfiles
        if include_dotfiles and os.path.isdir(user_home):
            try:
                for entry in sorted(os.listdir(user_home)):
                    if entry.startswith(".") and entry not in [".", "..", ".config", ".local", ".var", ".cache"]:
                        full_p = os.path.join(user_home, entry)
                        all_candidate_paths.append((full_p, entry, "dotfile"))
            except (OSError, PermissionError):
                pass

        # Check /etc for .rpmsave / .rpmnew (optimized maxdepth search, skipping security/pki)
        if include_system_etc and os.path.isdir("/etc"):
            skip_subdirs = {"selinux", "pki", "security", "pam.d", "ssl", "crypto-policies"}
            try:
                for root, dirs, files in os.walk("/etc", followlinks=False):
                    # Prevent recursing too deep or into security sensitive folders
                    rel = os.path.relpath(root, "/etc")
                    depth = 0 if rel == "." else len(rel.split(os.sep))
                    if depth >= 3:
                        dirs.clear()
                        continue
                    dirs[:] = [d for d in dirs if d not in skip_subdirs]

                    for f in files:
                        if f.endswith(".rpmsave") or f.endswith(".rpmnew"):
                            fp = os.path.join(root, f)
                            all_candidate_paths.append((fp, f, "system_etc"))
            except (OSError, PermissionError):
                pass

        total = len(all_candidate_paths)

        for i, (path, name, category) in enumerate(all_candidate_paths):
            if progress_callback:
                progress_callback(f"Analyzing {name}...", i + 1, total)

            item = self._analyze_item(path, name, category)
            if item:
                items.append(item)

        return items

    def _analyze_item(self, path: str, name: str, category: str) -> Optional[ScanItem]:
        """Analyzes a single file or directory item against safety and detector engines."""
        is_dir = os.path.isdir(path) and not os.path.islink(path)

        # 1. Check Safelist
        is_safe, safe_reason = self.safety.is_safelisted(path)
        if is_safe:
            # Fast stat for protected items to prevent slow recursive walks
            size = 0
            count = 0
            mtime = 0.0
            try:
                st = os.stat(path)
                mtime = st.st_mtime
                size = st.st_size
            except OSError:
                pass
            return ScanItem(
                path=path,
                name=name,
                category=category,
                is_directory=is_dir,
                size_bytes=size,
                file_count=count,
                last_modified=mtime,
                status="PROTECTED",
                reason=safe_reason,
                suggested_action="keep",
                is_selected=False,
            )

        # 2. Handle /etc rpmsave / rpmnew
        if category == "system_etc":
            size, count, mtime = get_path_stats(path)
            if name.endswith(".rpmsave"):
                return ScanItem(
                    path=path,
                    name=name,
                    category=category,
                    is_directory=False,
                    size_bytes=size,
                    file_count=count,
                    last_modified=mtime,
                    status="CONFIRMED_ORPHAN",
                    reason="RPM orphan configuration backup left over after uninstalled package",
                    suggested_action="clean",
                    is_selected=True,
                )
            elif name.endswith(".rpmnew"):
                return ScanItem(
                    path=path,
                    name=name,
                    category=category,
                    is_directory=False,
                    size_bytes=size,
                    file_count=count,
                    last_modified=mtime,
                    status="PROBABLE_ORPHAN",
                    reason="RPM package upgrade created unmerged configuration template",
                    suggested_action="review",
                    is_selected=False,
                )

        # 3. Check App Status via Detector
        is_active, matched_target, match_type, details = self.detector.check_app_status(name)

        size, count, mtime = get_path_stats(path)

        if is_active:
            return ScanItem(
                path=path,
                name=name,
                category=category,
                is_directory=is_dir,
                size_bytes=size,
                file_count=count,
                last_modified=mtime,
                status="ACTIVE_APP",
                reason=f"Active application detected ({details})",
                suggested_action="keep",
                is_selected=False,
            )

        # Inactive application: Check if confirmed orphan vs probable orphan
        # If folder modified long ago (> 30 days) and no package exists -> Confirmed Orphan
        days_inactive = 0
        if mtime > 0:
            days_inactive = (time.time() - mtime) / 86400.0

        if days_inactive > 14:
            status = "CONFIRMED_ORPHAN"
            action = "clean"
            selected = True
            reason_text = f"Uninstalled application leftover. {details}. Inactive for {int(days_inactive)} days."
        else:
            status = "PROBABLE_ORPHAN"
            action = "review"
            selected = False
            reason_text = f"No installed package or binary found. {details}. Modified recently ({int(days_inactive)} days ago)."

        return ScanItem(
            path=path,
            name=name,
            category=category,
            is_directory=is_dir,
            size_bytes=size,
            file_count=count,
            last_modified=mtime,
            status=status,
            reason=reason_text,
            suggested_action=action,
            is_selected=selected,
        )

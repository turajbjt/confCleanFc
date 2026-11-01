"""
Deep Configuration Scanner for ConfClean FC.
Scans user-space and system configuration directories to identify orphaned and leftover files.
"""

import difflib
import os
import shlex
import shutil
import sys
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.detector import SystemDetector
from confclean.core.safelist import SafetyEngine


def get_rpm_diff(rpm_path: str) -> Tuple[Optional[str], str, str]:
    """
    Computes a unified diff between an active configuration file and its
    corresponding .rpmnew or .rpmsave file.

    Returns:
        (active_file_path, rpm_file_path, diff_content)
    """
    if not os.path.isfile(rpm_path):
        return None, rpm_path, f"Error: File '{rpm_path}' does not exist."

    # Identify corresponding active configuration file
    active_path = None
    if rpm_path.endswith(".rpmnew"):
        active_path = rpm_path[:-7]
    elif rpm_path.endswith(".rpmsave"):
        active_path = rpm_path[:-8]
    else:
        return None, rpm_path, f"Error: '{rpm_path}' is not an .rpmnew or .rpmsave file."

    if not os.path.isfile(active_path):
        return None, rpm_path, f"Active configuration file '{active_path}' does not exist on disk."

    try:
        # Check size to avoid diffing huge files (max 2MB)
        max_bytes = 2 * 1024 * 1024
        if os.path.getsize(rpm_path) > max_bytes or os.path.getsize(active_path) > max_bytes:
            return active_path, rpm_path, "Error: File exceeds 2MB limit for visual diffing."

        with open(active_path, "r", encoding="utf-8", errors="replace") as f_active:
            active_lines = f_active.readlines()

        with open(rpm_path, "r", encoding="utf-8", errors="replace") as f_rpm:
            rpm_lines = f_rpm.readlines()

        diff_lines = list(
            difflib.unified_diff(
                active_lines,
                rpm_lines,
                fromfile=f"Active: {active_path}",
                tofile=f"RPM: {rpm_path}",
                lineterm="",
            )
        )

        if not diff_lines:
            return active_path, rpm_path, "No differences found between active configuration and package template."

        return active_path, rpm_path, "\n".join(diff_lines)
    except Exception as e:
        return active_path, rpm_path, f"Error generating diff: {e}"


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
        include_broken_desktops: bool = True,
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

        # Check Broken Desktop Launchers and Autostart Entries
        if include_broken_desktops and os.path.isdir(user_home):
            desktop_dirs = [
                os.path.join(user_home, ".local", "share", "applications"),
                os.path.join(user_home, ".config", "autostart"),
            ]
            for d_path in desktop_dirs:
                if os.path.isdir(d_path):
                    try:
                        for entry in sorted(os.listdir(d_path)):
                            if entry.endswith(".desktop"):
                                full_p = os.path.join(d_path, entry)
                                all_candidate_paths.append((full_p, entry, "broken_desktop"))
                    except (OSError, PermissionError):
                        pass

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

    def _extract_exec_binary(self, line: str) -> Optional[str]:
        """Extracts the primary executable name or wrapper target from an Exec= or TryExec= line."""
        val = line.split("=", 1)[1].strip() if "=" in line else line.strip()
        if not val:
            return None
        try:
            tokens = shlex.split(val)
        except ValueError:
            tokens = val.split()
        if not tokens:
            return None

        # Skip environment variable wrappers like 'env FOO=bar binary'
        idx = 0
        if tokens[idx] == "env":
            idx += 1
            while idx < len(tokens) and "=" in tokens[idx]:
                idx += 1

        if idx >= len(tokens):
            return None

        cmd = tokens[idx]
        if cmd.startswith("%"):
            return None

        # Handle Flatpak run wrapper
        if cmd == "flatpak" and idx + 2 < len(tokens) and tokens[idx + 1] == "run":
            return f"flatpak:{tokens[idx + 2]}"

        # Handle Snap run wrapper
        if cmd == "snap" and idx + 2 < len(tokens) and tokens[idx + 1] == "run":
            return f"snap:{tokens[idx + 2]}"

        return cmd

    def _is_binary_valid(self, cmd: str) -> bool:
        """Validates whether a command, binary, flatpak, or snap exists on the system."""
        if not cmd:
            return False

        if cmd.startswith("flatpak:"):
            appid = cmd[8:].lower()
            return appid in self.detector.flatpak_apps

        if cmd.startswith("snap:"):
            snap_name = cmd[5:].lower()
            return snap_name in self.detector.snap_apps

        # Direct absolute path
        if os.path.isabs(cmd):
            return os.path.exists(cmd)

        # In system PATH or detected binaries
        if shutil.which(cmd):
            return True

        if cmd.lower() in self.detector.binaries:
            return True

        return False

    def _analyze_desktop_file(self, path: str, name: str, category: str) -> Optional[ScanItem]:
        """Analyzes a .desktop file to determine if its target executable is missing (broken)."""
        is_safe, safe_reason = self.safety.is_safelisted(path)
        size, count, mtime = get_path_stats(path)

        if is_safe:
            return ScanItem(
                path=path,
                name=name,
                category=category,
                is_directory=False,
                size_bytes=size,
                file_count=count,
                last_modified=mtime,
                status="PROTECTED",
                reason=safe_reason,
                suggested_action="keep",
                is_selected=False,
            )

        exec_cmd = None
        try_exec = None
        app_name = name
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_s = line.strip()
                    if line_s.startswith("Exec=") and exec_cmd is None:
                        exec_cmd = line_s
                    elif line_s.startswith("TryExec=") and try_exec is None:
                        try_exec = line_s
                    elif line_s.startswith("Name=") and app_name == name:
                        app_name = line_s.split("=", 1)[1].strip()
        except (OSError, PermissionError):
            return None

        if not exec_cmd and not try_exec:
            return None

        target_line = try_exec or exec_cmd
        extracted_binary = self._extract_exec_binary(target_line)
        if not extracted_binary:
            return None

        is_valid = self._is_binary_valid(extracted_binary)
        if not is_valid:
            return ScanItem(
                path=path,
                name=name,
                category=category,
                is_directory=False,
                size_bytes=size,
                file_count=count,
                last_modified=mtime,
                status="CONFIRMED_ORPHAN",
                reason=f"Broken desktop launcher: Executable '{extracted_binary}' not found on system (App: {app_name})",
                suggested_action="clean",
                is_selected=True,
            )
        else:
            return ScanItem(
                path=path,
                name=name,
                category=category,
                is_directory=False,
                size_bytes=size,
                file_count=count,
                last_modified=mtime,
                status="ACTIVE_APP",
                reason=f"Valid desktop launcher for '{extracted_binary}' (App: {app_name})",
                suggested_action="keep",
                is_selected=False,
            )

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

        # 3. Handle Broken Desktop Launchers & Autostart Entries
        if category == "broken_desktop":
            return self._analyze_desktop_file(path, name, category)

        # 4. Check App Status via Detector
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

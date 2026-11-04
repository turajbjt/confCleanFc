"""
Cache and Junk Cleaner Engine for ConfClean FC.
Identifies and cleans thumbnail caches, trash, crash dumps, build caches,
DNF caches, systemd journals, and temporary files safely.
"""

import fnmatch
import glob
import os
import re
import shutil
import subprocess
import time
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.logger import get_logger
from confclean.core.safelist import SafetyEngine


class CacheCategory:
    """Represents a category of cache or junk data."""

    def __init__(
        self,
        category_id: str,
        name: str,
        description: str,
        requires_root: bool,
        paths: List[str],
        size_bytes: int = 0,
        item_count: int = 0,
        is_selected: bool = True,
    ):
        self.category_id = category_id
        self.name = name
        self.description = description
        self.requires_root = requires_root
        self.paths = paths
        self.size_bytes = size_bytes
        self.item_count = item_count
        self.is_selected = is_selected

    @property
    def formatted_size(self) -> str:
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"


class CacheCleaner:
    """Manages discovery and safe purging of user and system junk."""

    def __init__(self, safety: Optional[SafetyEngine] = None):
        self.safety = safety or SafetyEngine()
        self.logger = get_logger()
        self.is_root = (os.geteuid() == 0)

    def _get_user_home(self) -> str:
        """
        Resolves the desktop user's home directory even when running as root via sudo or pkexec.
        """
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user and sudo_user != "root":
            try:
                import pwd
                return pwd.getpwnam(sudo_user).pw_dir
            except (KeyError, ImportError, Exception):
                pass

        pkexec_uid = os.environ.get("PKEXEC_UID")
        if pkexec_uid:
            try:
                import pwd
                return pwd.getpwuid(int(pkexec_uid)).pw_dir
            except (ValueError, KeyError, ImportError, Exception):
                pass

        return os.path.expanduser("~")

    def _get_path_size(self, path: str) -> int:
        """Calculates recursive size of a directory or file in bytes."""
        if not os.path.exists(path):
            return 0
        if os.path.islink(path) or os.path.isfile(path):
            try:
                return os.lstat(path).st_size
            except (OSError, PermissionError):
                return 0
        total = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    try:
                        total += os.lstat(os.path.join(root, f)).st_size
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return total

    def _calculate_paths_size(self, paths: List[str]) -> int:
        """Sum of sizes for a list of paths."""
        return sum(self._get_path_size(p) for p in paths)

    def _is_safe_cache_target(self, path: str) -> bool:
        """
        Verifies that a directory or file is safe to purge as cache/junk.
        Protects critical filesystem roots, credentials, and user whitelists,
        without falsely blocking designated package or system cache folders.
        """
        if not path:
            return False
        norm = os.path.abspath(path.strip())

        # Prohibit root filesystems and essential top-level dirs
        dangerous_roots = self.safety.PROTECTED_ROOT_DIRS | {
            "/tmp", "/var/tmp", "/var", "/etc", "/opt", "/srv", "/usr/local"
        }
        if norm in dangerous_roots:
            return False

        # Must have at least 2 hierarchy levels (e.g. /var/cache, /home/user/.cache)
        parts = [p for p in norm.split(os.sep) if p]
        if len(parts) < 2:
            return False

        # Prohibit security, auth, keys, SSH, GPG
        sec_keywords = ["ssh", "gnupg", "pki", "keyring", "secret", "crypto", "wallet", "token", "credentials"]
        path_lower = norm.lower()
        for part in parts:
            for kw in sec_keywords:
                if kw in part:
                    return False

        # Respect user whitelist
        for user_pat in self.safety.user_whitelist:
            pat_lower = user_pat.lower()
            base = os.path.basename(norm).lower()
            if norm == user_pat or norm.startswith(user_pat.rstrip("/") + "/"):
                return False
            if fnmatch.fnmatch(base, pat_lower):
                return False

        return True

    def _empty_directory(self, dir_path: str) -> Tuple[int, int]:
        """
        Safely removes all files and subdirectories inside dir_path,
        preserving the top-level directory and its permissions/SELinux context.
        Returns (bytes_removed: int, items_removed: int).
        """
        if not os.path.isdir(dir_path) or os.path.islink(dir_path):
            return 0, 0
        bytes_removed = 0
        items_removed = 0
        try:
            entries = os.listdir(dir_path)
        except (OSError, PermissionError) as e:
            self.logger.warning(f"Could not read directory contents of {dir_path}: {e}")
            return 0, 0

        for entry in entries:
            sub_path = os.path.join(dir_path, entry)
            try:
                sub_size = self._get_path_size(sub_path)
                if os.path.isdir(sub_path) and not os.path.islink(sub_path):
                    shutil.rmtree(sub_path)
                else:
                    os.remove(sub_path)
                bytes_removed += sub_size
                items_removed += 1
            except (OSError, PermissionError) as e:
                self.logger.warning(f"Could not remove cache entry {sub_path}: {e}")
        return bytes_removed, items_removed

    def scan_categories(self) -> List[CacheCategory]:
        """Scans all supported cache locations and measures disk usage."""
        user_home = self._get_user_home()
        categories: List[CacheCategory] = []

        # 1. User Thumbnails
        thumb_paths = [os.path.join(user_home, ".cache", "thumbnails")]
        if self.is_root and os.path.expanduser("~") != user_home:
            thumb_paths.append(os.path.join(os.path.expanduser("~"), ".cache", "thumbnails"))
        categories.append(
            self._evaluate_category(
                category_id="thumbnails",
                name="Thumbnail Cache",
                description="Cached image and video preview thumbnails generated by file managers.",
                requires_root=False,
                paths=thumb_paths,
            )
        )

        # 2. User Trash
        trash_paths = [os.path.join(user_home, ".local", "share", "Trash")]
        if self.is_root and os.path.expanduser("~") != user_home:
            trash_paths.append(os.path.join(os.path.expanduser("~"), ".local", "share", "Trash"))
        categories.append(
            self._evaluate_category(
                category_id="user_trash",
                name="Trash Bin",
                description="Files and directories moved to user trash but not yet permanently deleted.",
                requires_root=False,
                paths=trash_paths,
            )
        )

        # 3. Flatpak App Runtimes Cache
        flatpak_cache = glob.glob(os.path.join(user_home, ".var", "app", "*", "cache"))
        categories.append(
            self._evaluate_category(
                category_id="flatpak_cache",
                name="Flatpak Application Caches",
                description="Temporary runtime caches stored by Flatpak applications.",
                requires_root=False,
                paths=flatpak_cache,
            )
        )

        # 4. User Core Dumps & Crash Logs
        coredump_paths = [
            os.path.join(user_home, ".local", "share", "systemd", "coredump"),
            os.path.join(user_home, ".cache", "crash"),
        ]
        categories.append(
            self._evaluate_category(
                category_id="user_crash",
                name="User Crash Dumps",
                description="Application crash stack traces and systemd user core dumps.",
                requires_root=False,
                paths=coredump_paths,
            )
        )

        # 5. Developer & Package Build Caches (Optional default unselected)
        dev_paths = [
            os.path.join(user_home, ".cache", "pip"),
            os.path.join(user_home, ".npm", "_cacache"),
            os.path.join(user_home, ".cargo", "registry", "cache"),
        ]
        dev_cat = self._evaluate_category(
            category_id="dev_caches",
            name="Developer Build Caches (pip / npm / cargo)",
            description="Cached packages and wheels downloaded by development package tools.",
            requires_root=False,
            paths=dev_paths,
        )
        dev_cat.is_selected = False  # Keep unchecked by default for developers
        categories.append(dev_cat)

        # 6. DNF Package Manager Cache (System / Root)
        dnf_cache_paths = [
            "/var/cache/dnf",
            "/var/cache/libdnf5",
            "/var/cache/PackageKit",
            os.path.join(user_home, ".cache", "libdnf5"),
            os.path.join(user_home, ".cache", "dnf"),
        ]
        if self.is_root and os.path.expanduser("~") != user_home:
            dnf_cache_paths.extend([
                os.path.join(os.path.expanduser("~"), ".cache", "libdnf5"),
                os.path.join(os.path.expanduser("~"), ".cache", "dnf"),
            ])
        categories.append(
            self._evaluate_category(
                category_id="dnf_cache",
                name="DNF / RPM Package Cache",
                description="Downloaded RPM packages, repository metadata, PackageKit cache, and expired headers.",
                requires_root=True,
                paths=dnf_cache_paths,
            )
        )

        # 7. Systemd Journal Logs (System / Root)
        journal_paths = ["/var/log/journal"]
        if os.path.isdir("/run/log/journal"):
            journal_paths.append("/run/log/journal")
        categories.append(
            self._evaluate_category(
                category_id="systemd_journal",
                name="Systemd Journal Archives",
                description="Archived system journal logs, obsolete machine IDs, and unclosed journal files.",
                requires_root=True,
                paths=journal_paths,
            )
        )

        # 8. System Crash Reports & ABRT (System / Root)
        abrt_paths = ["/var/spool/abrt", "/var/crash"]
        categories.append(
            self._evaluate_category(
                category_id="system_crashes",
                name="System ABRT Crash Reports",
                description="Automated Bug Reporting Tool crash data and core dumps in /var/spool/abrt.",
                requires_root=True,
                paths=abrt_paths,
            )
        )

        # 9. System /tmp and /var/tmp Old Files
        categories.append(
            self._evaluate_old_tmp_category(
                category_id="system_tmp",
                name="Old Temporary Files (> 7 days)",
                description="Temporary files in /tmp and /var/tmp that have not been accessed in over a week.",
                requires_root=True,
            )
        )

        return categories

    def _evaluate_category(
        self,
        category_id: str,
        name: str,
        description: str,
        requires_root: bool,
        paths: List[str],
    ) -> CacheCategory:
        total_size = 0
        file_count = 0
        valid_paths = []

        for p in paths:
            if not os.path.exists(p):
                continue
            valid_paths.append(p)
            try:
                if os.path.isfile(p):
                    total_size += os.path.getsize(p)
                    file_count += 1
                elif os.path.isdir(p):
                    for root, dirs, files in os.walk(p):
                        file_count += len(files)
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                total_size += os.lstat(fp).st_size
                            except (OSError, PermissionError):
                                pass
            except (OSError, PermissionError):
                pass

        return CacheCategory(
            category_id=category_id,
            name=name,
            description=description,
            requires_root=requires_root,
            paths=valid_paths,
            size_bytes=total_size,
            item_count=file_count,
            is_selected=(total_size > 0 and (not requires_root or self.is_root)),
        )

    def _evaluate_old_tmp_category(
        self,
        category_id: str,
        name: str,
        description: str,
        requires_root: bool,
        tmp_dirs: Optional[List[str]] = None,
    ) -> CacheCategory:
        total_size = 0
        file_count = 0
        now = time.time()
        max_age = 7 * 86400  # 7 days
        matched_files = []
        search_dirs = tmp_dirs or ["/tmp", "/var/tmp"]

        for tmp_dir in search_dirs:
            if not os.path.isdir(tmp_dir):
                continue
            try:
                for entry in os.listdir(tmp_dir):
                    fp = os.path.join(tmp_dir, entry)
                    # Skip systemd private directories and sockets
                    if entry.startswith("systemd-private-") or os.path.islink(fp) or not os.path.exists(fp):
                        continue
                    try:
                        st = os.stat(fp)
                        if (now - st.st_atime) > max_age and (now - st.st_mtime) > max_age:
                            total_size += st.st_size
                            file_count += 1
                            matched_files.append(fp)
                    except (OSError, PermissionError):
                        continue
            except (OSError, PermissionError):
                continue

        return CacheCategory(
            category_id=category_id,
            name=name,
            description=description,
            requires_root=requires_root,
            paths=matched_files,
            size_bytes=total_size,
            item_count=file_count,
            is_selected=(total_size > 0 and (not requires_root or self.is_root)),
        )

    def clean_category(
        self,
        category: CacheCategory,
        dry_run: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Tuple[int, int, str]:
        """
        Cleans the selected cache category.
        Returns:
            (bytes_reclaimed: int, items_removed: int, message: str)
        """
        if category.requires_root and not self.is_root:
            return 0, 0, f"Cannot clean '{category.name}': Root privileges required."

        if dry_run:
            self.logger.info(
                f"DRY RUN: Simulating purge of cache category '{category.name}' ({category.formatted_size})"
            )
            return (
                category.size_bytes,
                category.item_count,
                f"[DRY RUN] Would purge {category.name} ({category.formatted_size})",
            )

        reclaimed_bytes = 0
        items_removed = 0

        self.logger.info(f"Purging cache category: '{category.name}'")

        # 1. Special handling for DNF / RPM Package Cache
        if category.category_id == "dnf_cache":
            if progress_callback:
                progress_callback("Running package manager clean tools...", 1, 2)

            # Trigger package manager clean actions across available CLI tools
            for cmd in [
                ["dnf5", "clean", "all"],
                ["dnf-3", "clean", "all"],
                ["dnf4", "clean", "all"],
                ["dnf", "clean", "all"],
                ["pkcon", "clean"],
            ]:
                bin_name = cmd[0]
                if shutil.which(bin_name):
                    try:
                        subprocess.run(cmd, capture_output=True, text=True, check=False)
                    except Exception as e:
                        self.logger.debug(f"{bin_name} clean command error: {e}")

            if progress_callback:
                progress_callback("Purging leftover package cache directories...", 2, 2)

            pre_size = self._calculate_paths_size(category.paths)
            total_dir_freed = 0

            # Empty designated cache directories (preserving the root folder and permissions)
            for p in category.paths:
                if not os.path.exists(p) or not self._is_safe_cache_target(p):
                    continue
                if os.path.isdir(p) and not os.path.islink(p):
                    b_rem, i_rem = self._empty_directory(p)
                    total_dir_freed += b_rem
                    items_removed += i_rem
                else:
                    try:
                        f_sz = self._get_path_size(p)
                        os.remove(p)
                        total_dir_freed += f_sz
                        items_removed += 1
                    except (OSError, PermissionError) as e:
                        self.logger.warning(f"Could not remove cache file {p}: {e}")

            post_size = self._calculate_paths_size(category.paths)
            reclaimed_bytes = max(total_dir_freed, pre_size - post_size)
            if reclaimed_bytes == 0 and category.size_bytes > 0:
                reclaimed_bytes = category.size_bytes
            if items_removed == 0 and category.item_count > 0:
                items_removed = category.item_count

            self.logger.audit_event(
                action="CACHE_CLEAN",
                target_path=category.name,
                size_bytes=reclaimed_bytes,
                status="SUCCESS",
                details=f"Cleaned DNF/RPM package caches, removed {items_removed} items",
            )
            return (
                reclaimed_bytes,
                items_removed,
                f"DNF and PackageKit caches cleaned ({reclaimed_bytes / (1024*1024):.1f} MB freed)",
            )

        # 2. Special handling for Systemd Journal Archives
        if category.category_id == "systemd_journal":
            if progress_callback:
                progress_callback("Rotating systemd journal...", 1, 3)

            pre_size = self._calculate_paths_size(category.paths)

            # Rotate active journals so existing logs can be safely trimmed
            try:
                subprocess.run(["journalctl", "--rotate"], capture_output=True, text=True, check=False)
            except Exception as e:
                self.logger.warning(f"journalctl --rotate failed: {e}")

            if progress_callback:
                progress_callback("Vacuuming archived journal logs...", 2, 3)

            # Vacuum journals: keep maximum 7 days and cap total archive size to 50MB
            try:
                subprocess.run(["journalctl", "--vacuum-time=7d"], capture_output=True, text=True, check=False)
                subprocess.run(["journalctl", "--vacuum-size=50M"], capture_output=True, text=True, check=False)
            except Exception as e:
                self.logger.warning(f"journalctl vacuum failed: {e}")

            if progress_callback:
                progress_callback("Purging obsolete machine-ID journals...", 3, 3)

            extra_freed = 0

            # Detect current active machine-id
            current_machine_id = ""
            for mid_path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
                if os.path.isfile(mid_path):
                    try:
                        with open(mid_path, "r", encoding="utf-8") as f:
                            val = f.read().strip()
                            if len(val) == 32 and re.fullmatch(r"[0-9a-fA-F]{32}", val):
                                current_machine_id = val
                                break
                    except Exception:
                        pass

            # Foreign / obsolete machine-ID directories in /var/log/journal
            if current_machine_id:
                for j_root in category.paths:
                    if not os.path.isdir(j_root):
                        continue
                    try:
                        for entry in os.listdir(j_root):
                            entry_path = os.path.join(j_root, entry)
                            if os.path.isdir(entry_path) and not os.path.islink(entry_path):
                                if (
                                    len(entry) == 32
                                    and re.fullmatch(r"[0-9a-fA-F]{32}", entry)
                                    and entry != current_machine_id
                                ):
                                    self.logger.info(
                                        f"Purging obsolete journal directory for past machine-id: {entry_path}"
                                    )
                                    dir_size = self._get_path_size(entry_path)
                                    try:
                                        shutil.rmtree(entry_path)
                                        extra_freed += dir_size
                                        items_removed += 1
                                    except (OSError, PermissionError) as e:
                                        self.logger.warning(f"Could not remove obsolete journal {entry_path}: {e}")
                    except (OSError, PermissionError) as e:
                        self.logger.warning(f"Could not inspect journal directory {j_root}: {e}")

            # Remove corrupted or unclosed journal archives (*.journal~)
            for j_root in category.paths:
                if not os.path.isdir(j_root):
                    continue
                try:
                    for root_d, dirs, files in os.walk(j_root):
                        for f in files:
                            if f.endswith(".journal~"):
                                fp = os.path.join(root_d, f)
                                try:
                                    f_size = self._get_path_size(fp)
                                    os.remove(fp)
                                    extra_freed += f_size
                                    items_removed += 1
                                except (OSError, PermissionError):
                                    pass
                except (OSError, PermissionError):
                    pass

            post_size = self._calculate_paths_size(category.paths)
            reclaimed_bytes = max(extra_freed, pre_size - post_size)
            if reclaimed_bytes == 0 and category.size_bytes > 0:
                reclaimed_bytes = category.size_bytes
            if items_removed == 0 and category.item_count > 0:
                items_removed = category.item_count

            self.logger.audit_event(
                action="CACHE_CLEAN",
                target_path=category.name,
                size_bytes=reclaimed_bytes,
                status="SUCCESS",
                details=f"Rotated and trimmed system journals, removed {items_removed} items",
            )
            return (
                reclaimed_bytes,
                items_removed,
                f"Systemd journals rotated and vacuumed ({reclaimed_bytes / (1024*1024):.1f} MB freed)",
            )

        # 3. Directory / file cleaning for general categories
        total_paths = len(category.paths)
        for idx, p in enumerate(category.paths):
            if progress_callback:
                progress_callback(f"Cleaning {os.path.basename(p)}...", idx + 1, total_paths)

            if not os.path.exists(p) or not self._is_safe_cache_target(p):
                continue

            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    b_rem, i_rem = self._empty_directory(p)
                    reclaimed_bytes += b_rem
                    items_removed += i_rem
                else:
                    file_size = self._get_path_size(p)
                    os.remove(p)
                    reclaimed_bytes += file_size
                    items_removed += 1
            except (OSError, PermissionError) as e:
                self.logger.warning(f"Could not purge {p}: {e}")

        if reclaimed_bytes == 0 and category.size_bytes > 0 and items_removed > 0:
            reclaimed_bytes = category.size_bytes

        self.logger.audit_event(
            action="CACHE_CLEAN",
            target_path=category.name,
            size_bytes=reclaimed_bytes,
            status="SUCCESS",
            details=f"Removed {items_removed} items",
        )

        return reclaimed_bytes, items_removed, f"Successfully cleaned {category.name}"

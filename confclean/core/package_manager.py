"""
RPM and DNF Package Optimizer for ConfClean FC.
Identifies unneeded dependencies (autoremove), old kernels, duplicate packages,
and repository orphans on Fedora, Rocky, CentOS, and RHEL.
"""

import os
import re
import shutil
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.logger import get_logger


class PackageSuggestion:
    """Represents an unneeded or orphaned RPM package suggested for removal."""

    def __init__(
        self,
        name: str,
        version: str,
        release: str,
        arch: str,
        size_bytes: int,
        summary: str,
        category: str,  # "unneeded_dep", "old_kernel", "duplicate", "repo_orphan"
        reason: str,
        is_protected: bool = False,
        is_selected: bool = False,
    ):
        self.name = name
        self.version = version
        self.release = release
        self.arch = arch
        self.size_bytes = size_bytes
        self.summary = summary
        self.category = category
        self.reason = reason
        self.is_protected = is_protected
        self.is_selected = is_selected

    @property
    def full_nevra(self) -> str:
        return f"{self.name}-{self.version}-{self.release}.{self.arch}"

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


class PackageManager:
    """Detects and safely removes unneeded packages, old kernels, and duplicates."""

    def __init__(self):
        self.logger = get_logger()
        self.dnf_bin = "dnf5" if shutil.which("dnf5") else ("dnf" if shutil.which("dnf") else "rpm")
        self.is_dnf5 = (self.dnf_bin == "dnf5")
        self.is_root = (os.geteuid() == 0)

    def scan_all_suggestions(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[PackageSuggestion]:
        """Runs package queries to identify candidate packages for cleanup."""
        suggestions: List[PackageSuggestion] = []

        if progress_callback:
            progress_callback("Scanning for unneeded dependencies...", 1, 4)
        unneeded = self._get_unneeded_packages()
        suggestions.extend(unneeded)

        if progress_callback:
            progress_callback("Scanning for old kernel packages...", 2, 4)
        old_kernels = self._get_old_kernels()
        suggestions.extend(old_kernels)

        if progress_callback:
            progress_callback("Scanning for duplicate package versions...", 3, 4)
        duplicates = self._get_duplicate_packages()
        suggestions.extend(duplicates)

        if progress_callback:
            progress_callback("Scanning complete.", 4, 4)

        return suggestions

    def _get_rpm_info_map(self) -> Dict[str, dict]:
        """Indexes installed RPM package metadata using python-rpm."""
        pkg_map = {}
        try:
            import rpm
            ts = rpm.TransactionSet()
            for h in ts.dbMatch():
                name = h["name"]
                if not name:
                    continue
                nevra = f"{name}-{h['version']}-{h['release']}.{h['arch']}"
                pkg_map[name.lower()] = {
                    "name": name,
                    "version": h["version"],
                    "release": h["release"],
                    "arch": h["arch"],
                    "size": h["size"] or 0,
                    "summary": h["summary"] or "",
                    "nevra": nevra,
                }
                pkg_map[nevra.lower()] = pkg_map[name.lower()]
        except Exception as e:
            self.logger.warning(f"Could not read RPM database via python-rpm: {e}")
        return pkg_map

    def _get_unneeded_packages(self) -> List[PackageSuggestion]:
        """Queries dnf repoquery --unneeded for leaf dependencies."""
        results: List[PackageSuggestion] = []
        if self.dnf_bin not in ["dnf5", "dnf"]:
            return results

        cmd = [self.dnf_bin, "repoquery", "--unneeded"]
        try:
            env = os.environ.copy()
            if "HOME" not in env or not os.access(env["HOME"], os.W_OK):
                env["HOME"] = "/tmp"

            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30, env=env)
            if res.returncode == 0 and res.stdout.strip():
                pkg_map = self._get_rpm_info_map()
                for line in res.stdout.splitlines():
                    raw = line.strip()
                    if not raw:
                        continue
                    # Parse package name from string e.g. "pkgname-0:1.0-1.fc44.x86_64" or "pkgname"
                    clean_name = raw.split("-0:")[0].split(":")[0]
                    # Also strip version if full string
                    base_name = re.split(r"-\d", clean_name)[0]

                    info = pkg_map.get(raw.lower()) or pkg_map.get(clean_name.lower()) or pkg_map.get(base_name.lower())
                    if info:
                        results.append(
                            PackageSuggestion(
                                name=info["name"],
                                version=info["version"],
                                release=info["release"],
                                arch=info["arch"],
                                size_bytes=info["size"],
                                summary=info["summary"],
                                category="unneeded_dep",
                                reason="Installed as dependency for removed software (autoremove candidate)",
                                is_protected=False,
                                is_selected=True,
                            )
                        )
                    else:
                        results.append(
                            PackageSuggestion(
                                name=base_name,
                                version="installed",
                                release="",
                                arch="x86_64",
                                size_bytes=0,
                                summary="Unneeded dependency package",
                                category="unneeded_dep",
                                reason="Identified by DNF as unneeded leaf package",
                                is_protected=False,
                                is_selected=True,
                            )
                        )
        except Exception as e:
            self.logger.warning(f"Error querying unneeded packages: {e}")

        return results

    def _get_old_kernels(self) -> List[PackageSuggestion]:
        """
        Identifies older installed kernels while strictly protecting:
        1. Currently running booted kernel (`uname -r`).
        2. Latest fallback kernel.
        """
        results: List[PackageSuggestion] = []
        running_kernel = ""
        try:
            running_kernel = os.uname().release
        except Exception:
            pass

        if self.dnf_bin not in ["dnf5", "dnf"]:
            return results

        cmd = [self.dnf_bin, "repoquery", "--installonly"]
        try:
            env = os.environ.copy()
            if "HOME" not in env or not os.access(env["HOME"], os.W_OK):
                env["HOME"] = "/tmp"

            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30, env=env)
            if res.returncode == 0 and res.stdout.strip():
                pkg_map = self._get_rpm_info_map()

                # Group kernel packages by version-release
                # e.g., 'kernel-core-0:7.2.13-200.fc44.x86_64'
                kernel_versions: Dict[str, List[dict]] = {}

                for line in res.stdout.splitlines():
                    raw = line.strip()
                    if not raw:
                        continue

                    # Extract version-release
                    # Match pattern like: kernel-...-0:7.2.13-200.fc44.x86_64
                    m = re.search(r":?([0-9]+\.[0-9]+\.[0-9]+-[0-9]+[a-zA-Z0-9\._]+)", raw)
                    vr = m.group(1) if m else raw

                    info = pkg_map.get(raw.lower())
                    if not info:
                        # Extract package name
                        pname = raw.split("-0:")[0]
                        info = {
                            "name": pname,
                            "version": vr,
                            "release": "",
                            "arch": "x86_64",
                            "size": 0,
                            "summary": "Kernel package",
                            "nevra": raw,
                        }

                    if vr not in kernel_versions:
                        kernel_versions[vr] = []
                    kernel_versions[vr].append(info)

                # Sort kernel versions (highest version first)
                from functools import cmp_to_key

                def ver_cmp(v1, v2):
                    # Simple tuple-based version compare
                    def parse_v(v):
                        parts = re.findall(r"\d+", v)
                        return [int(p) for p in parts]
                    p1, p2 = parse_v(v1), parse_v(v2)
                    return (p1 > p2) - (p1 < p2)

                sorted_versions = sorted(kernel_versions.keys(), key=cmp_to_key(ver_cmp), reverse=True)

                # Rules:
                # - Running kernel: ALWAYS PROTECTED
                # - Highest available kernel: ALWAYS PROTECTED
                # - Kernels beyond the top 2: CANDIDATES FOR REMOVAL
                for idx, vr in enumerate(sorted_versions):
                    pkgs = kernel_versions[vr]
                    is_running = running_kernel and (running_kernel in vr or vr in running_kernel)
                    is_latest_fallback = (idx == 0 and not is_running) or (idx == 1 and is_running)

                    if is_running:
                        for p in pkgs:
                            results.append(
                                PackageSuggestion(
                                    name=p["name"],
                                    version=p["version"],
                                    release=p["release"],
                                    arch=p["arch"],
                                    size_bytes=p["size"],
                                    summary=p["summary"],
                                    category="old_kernel",
                                    reason=f"PROTECTED: Currently running booted kernel ({running_kernel})",
                                    is_protected=True,
                                    is_selected=False,
                                )
                            )
                    elif is_latest_fallback or idx < 2:
                        for p in pkgs:
                            results.append(
                                PackageSuggestion(
                                    name=p["name"],
                                    version=p["version"],
                                    release=p["release"],
                                    arch=p["arch"],
                                    size_bytes=p["size"],
                                    summary=p["summary"],
                                    category="old_kernel",
                                    reason="SAFE KEEP: Latest fallback backup kernel",
                                    is_protected=True,
                                    is_selected=False,
                                )
                            )
                    else:
                        # Older kernel: suggest removal!
                        for p in pkgs:
                            results.append(
                                PackageSuggestion(
                                    name=p["name"],
                                    version=p["version"],
                                    release=p["release"],
                                    arch=p["arch"],
                                    size_bytes=p["size"],
                                    summary=p["summary"],
                                    category="old_kernel",
                                    reason=f"Old unused kernel ({vr}). Booted kernel is {running_kernel}.",
                                    is_protected=False,
                                    is_selected=True,
                                )
                            )

        except Exception as e:
            self.logger.warning(f"Error querying kernel packages: {e}")

        return results

    def _get_duplicate_packages(self) -> List[PackageSuggestion]:
        """Queries dnf repoquery --duplicates."""
        results: List[PackageSuggestion] = []
        if self.dnf_bin not in ["dnf5", "dnf"]:
            return results

        cmd = [self.dnf_bin, "repoquery", "--duplicates"]
        try:
            env = os.environ.copy()
            if "HOME" not in env or not os.access(env["HOME"], os.W_OK):
                env["HOME"] = "/tmp"

            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30, env=env)
            if res.returncode == 0 and res.stdout.strip():
                pkg_map = self._get_rpm_info_map()
                for line in res.stdout.splitlines():
                    raw = line.strip()
                    if not raw:
                        continue
                    info = pkg_map.get(raw.lower())
                    if info:
                        results.append(
                            PackageSuggestion(
                                name=info["name"],
                                version=info["version"],
                                release=info["release"],
                                arch=info["arch"],
                                size_bytes=info["size"],
                                summary=info["summary"],
                                category="duplicate",
                                reason="Duplicate package version installed simultaneously",
                                is_protected=False,
                                is_selected=True,
                            )
                        )
                    else:
                        base_name = re.split(r"-\d", raw.split("-0:")[0])[0]
                        results.append(
                            PackageSuggestion(
                                name=base_name,
                                version="duplicate",
                                release="",
                                arch="x86_64",
                                size_bytes=0,
                                summary="Duplicate package version",
                                category="duplicate",
                                reason="Duplicate package version installed simultaneously",
                                is_protected=False,
                                is_selected=True,
                            )
                        )
        except Exception as e:
            self.logger.warning(f"Error querying duplicate packages: {e}")

        return results

    def get_removal_command(self, packages: List[PackageSuggestion]) -> List[str]:
        """Returns the CLI command string to remove the selected packages."""
        pkg_names = [p.name for p in packages if not p.is_protected and p.is_selected]
        if not pkg_names:
            return []
        prefix = ["pkexec", self.dnf_bin] if not self.is_root else [self.dnf_bin]
        return prefix + ["remove", "-y"] + pkg_names

"""
RPM and DNF Package Optimizer for ConfClean FC.
Identifies unneeded dependencies (autoremove), old kernels, duplicate packages,
and repository orphans on Fedora, Rocky, CentOS, and RHEL.
"""

import os
import re
import shlex
import shutil
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.logger import get_logger
from confclean.core.safelist import SafetyEngine


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
        if self.release and self.arch:
            return f"{self.name}-{self.version}-{self.release}.{self.arch}"
        elif self.release:
            return f"{self.name}-{self.version}-{self.release}"
        return f"{self.name}-{self.version}"

    @property
    def removal_spec(self) -> str:
        """Returns the specific package specifier for dnf/rpm/flatpak/snap removal."""
        if self.category == "snap_unused":
            return f"{self.name} --revision={self.release}" if self.release else self.name
        elif self.category == "flatpak_unused":
            return self.name
        elif self.category in ("old_kernel", "duplicate"):
            if self.release and self.arch:
                return f"{self.name}-{self.version}-{self.release}.{self.arch}"
            elif self.release:
                return f"{self.name}-{self.version}-{self.release}"
            elif self.version and self.version not in ("installed", "duplicate"):
                return f"{self.name}-{self.version}"
        return self.name

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

    def __init__(self, safety: Optional[SafetyEngine] = None):
        self.logger = get_logger()
        self.safety = safety or SafetyEngine()
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
            progress_callback("Scanning for unneeded dependencies...", 1, 7)
        unneeded = self._get_unneeded_packages()
        suggestions.extend(unneeded)

        if progress_callback:
            progress_callback("Scanning for old kernel packages...", 2, 7)
        old_kernels = self._get_old_kernels()
        suggestions.extend(old_kernels)

        if progress_callback:
            progress_callback("Scanning for duplicate package versions...", 3, 7)
        duplicates = self._get_duplicate_packages()
        suggestions.extend(duplicates)

        if progress_callback:
            progress_callback("Scanning for retired / repo-orphan packages...", 4, 7)
        repo_orphans = self._get_repo_orphans()
        suggestions.extend(repo_orphans)

        if progress_callback:
            progress_callback("Scanning for unused Flatpak runtimes...", 5, 7)
        flatpaks = self._get_unused_flatpaks()
        suggestions.extend(flatpaks)

        if progress_callback:
            progress_callback("Scanning for disabled Snap revisions...", 6, 7)
        snaps = self._get_unused_snaps()
        suggestions.extend(snaps)

        if progress_callback:
            progress_callback("Scanning complete.", 7, 7)

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
                version = h["version"]
                release = h["release"]
                arch = h["arch"]
                epoch = str(h["epoch"]) if h["epoch"] is not None else "0"
                nevra = f"{name}-{version}-{release}.{arch}"
                envra = f"{name}-{epoch}:{version}-{release}.{arch}"
                nvr = f"{name}-{version}-{release}"
                info = {
                    "name": name,
                    "version": version,
                    "release": release,
                    "arch": arch,
                    "size": h["size"] or 0,
                    "summary": h["summary"] or "",
                    "nevra": nevra,
                }
                pkg_map[nevra.lower()] = info
                pkg_map[envra.lower()] = info
                pkg_map[nvr.lower()] = info
                if name.lower() not in pkg_map:
                    pkg_map[name.lower()] = info
        except Exception as e:
            self.logger.warning(f"Could not read RPM database via python-rpm: {e}")

        # Fallback to rpm command if python-rpm is not installed or returned empty
        if not pkg_map:
            try:
                res = subprocess.run(
                    ["rpm", "-qa", "--qf", "%{NAME}|%{VERSION}|%{RELEASE}|%{ARCH}|%{EPOCH}|%{SIZE}|%{SUMMARY}\n"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        parts = line.strip().split("|", 6)
                        if len(parts) >= 7:
                            p_name, p_version, p_release, p_arch, p_epoch, p_size, p_summary = parts
                            epoch_str = p_epoch if p_epoch and p_epoch != "(none)" else "0"
                            size_int = int(p_size) if p_size.isdigit() else 0
                            nevra = f"{p_name}-{p_version}-{p_release}.{p_arch}"
                            envra = f"{p_name}-{epoch_str}:{p_version}-{p_release}.{p_arch}"
                            nvr = f"{p_name}-{p_version}-{p_release}"
                            info = {
                                "name": p_name,
                                "version": p_version,
                                "release": p_release,
                                "arch": p_arch,
                                "size": size_int,
                                "summary": p_summary,
                                "nevra": nevra,
                            }
                            pkg_map[nevra.lower()] = info
                            pkg_map[envra.lower()] = info
                            pkg_map[nvr.lower()] = info
                            if p_name.lower() not in pkg_map:
                                pkg_map[p_name.lower()] = info
            except Exception as e:
                self.logger.warning(f"Could not read RPM database via rpm command: {e}")

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
                        pname = info["name"]
                        pver = info["version"]
                        prel = info["release"]
                        parch = info["arch"]
                        psize = info["size"]
                        psummary = info["summary"]
                        pnevra = info.get("nevra", "")
                        default_reason = "Installed as dependency for removed software (autoremove candidate)"
                    else:
                        pname = base_name
                        pver = "installed"
                        prel = ""
                        parch = "x86_64"
                        psize = 0
                        psummary = "Unneeded dependency package"
                        pnevra = ""
                        default_reason = "Identified by DNF as unneeded leaf package"

                    is_prot, prot_reason = self.safety.is_package_safelisted(pname, pnevra)
                    if is_prot:
                        is_protected = True
                        is_selected = False
                        reason = f"PROTECTED: {prot_reason}"
                    else:
                        is_protected = False
                        is_selected = True
                        reason = default_reason

                    results.append(
                        PackageSuggestion(
                            name=pname,
                            version=pver,
                            release=prel,
                            arch=parch,
                            size_bytes=psize,
                            summary=psummary,
                            category="unneeded_dep",
                            reason=reason,
                            is_protected=is_protected,
                            is_selected=is_selected,
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

                    # Normalize epoch e.g. kernel-core-0:7.2.13-200.fc44.x86_64 -> kernel-core-7.2.13-200.fc44.x86_64
                    clean = re.sub(r"-(\d+):", "-", raw)

                    info = pkg_map.get(raw.lower()) or pkg_map.get(clean.lower())
                    if not info:
                        # Extract name, version, release, arch from NEVRA: name-version-release.arch
                        m_pkg = re.match(r"^(.+?)-([0-9][^-]*)-([0-9].*)\.([^.]+)$", clean)
                        if m_pkg:
                            pname, pver, prel, parch = m_pkg.groups()
                        else:
                            m_vr = re.search(r":?([0-9]+\.[0-9]+\.[0-9]+-[0-9]+[a-zA-Z0-9\._]+)", raw)
                            vr_fallback = m_vr.group(1) if m_vr else raw
                            pname = raw.split("-0:")[0].split(":")[0]
                            pver = vr_fallback
                            prel = ""
                            parch = "x86_64"

                        info = {
                            "name": pname,
                            "version": pver,
                            "release": prel,
                            "arch": parch,
                            "size": 0,
                            "summary": "Kernel package",
                            "nevra": clean,
                        }

                    vr = f"{info['version']}-{info['release']}" if info.get("release") else info["version"]
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
                        # Older kernel: suggest removal unless safelisted by user
                        for p in pkgs:
                            nevra_str = p.get("nevra", "")
                            is_prot, prot_reason = self.safety.is_package_safelisted(p["name"], nevra_str, check_core=False)
                            if is_prot:
                                results.append(
                                    PackageSuggestion(
                                        name=p["name"],
                                        version=p["version"],
                                        release=p["release"],
                                        arch=p["arch"],
                                        size_bytes=p["size"],
                                        summary=p["summary"],
                                        category="old_kernel",
                                        reason=f"PROTECTED: {prot_reason}",
                                        is_protected=True,
                                        is_selected=False,
                                    )
                                )
                            else:
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
                    clean = re.sub(r"-(\d+):", "-", raw)
                    info = pkg_map.get(raw.lower()) or pkg_map.get(clean.lower())
                    if info:
                        pname = info["name"]
                        pver = info["version"]
                        prel = info["release"]
                        parch = info["arch"]
                        psize = info["size"]
                        psummary = info["summary"]
                        pnevra = info.get("nevra", "")
                    else:
                        m_pkg = re.match(r"^(.+?)-([0-9][^-]*)-([0-9].*)\.([^.]+)$", clean)
                        if m_pkg:
                            pname, pver, prel, parch = m_pkg.groups()
                        else:
                            pname = re.split(r"-\d", raw.split("-0:")[0])[0]
                            pver = "duplicate"
                            prel = ""
                            parch = "x86_64"
                        psize = 0
                        psummary = "Duplicate package version"
                        pnevra = clean

                    is_prot, prot_reason = self.safety.is_package_safelisted(pname, pnevra)
                    results.append(
                        PackageSuggestion(
                            name=pname,
                            version=pver,
                            release=prel,
                            arch=parch,
                            size_bytes=psize,
                            summary=psummary,
                            category="duplicate",
                            reason=f"PROTECTED: {prot_reason}" if is_prot else "Duplicate package version installed simultaneously",
                            is_protected=is_prot,
                            is_selected=not is_prot,
                        )
                    )
        except Exception as e:
            self.logger.warning(f"Error querying duplicate packages: {e}")

        return results

    def _get_unused_flatpaks(self) -> List[PackageSuggestion]:
        """Queries flatpak uninstall --unused for unreferenced runtimes gracefully."""
        results: List[PackageSuggestion] = []
        flatpak_bin = shutil.which("flatpak")
        if not flatpak_bin:
            return results

        try:
            res = subprocess.run(
                [flatpak_bin, "uninstall", "--unused"],
                input="n\n",
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if res.stdout:
                for line in res.stdout.splitlines():
                    line_s = line.strip()
                    if not line_s or "Nothing unused" in line_s or line_s.startswith("ID") or "Proceed with" in line_s:
                        continue
                    parts = line_s.split()
                    if parts and parts[0].endswith("."):
                        parts = parts[1:]
                    if len(parts) >= 2:
                        ref_id = parts[0]
                        branch = parts[1]
                        if "." in ref_id and not ref_id.startswith("["):
                            is_prot, prot_reason = self.safety.is_package_safelisted(ref_id)
                            results.append(
                                PackageSuggestion(
                                    name=ref_id,
                                    version=branch,
                                    release="",
                                    arch="",
                                    size_bytes=0,
                                    summary="Unused Flatpak runtime",
                                    category="flatpak_unused",
                                    reason=f"PROTECTED: {prot_reason}" if is_prot else "Unused Flatpak runtime left over after application removal",
                                    is_protected=is_prot,
                                    is_selected=not is_prot,
                                )
                            )
        except Exception as e:
            self.logger.warning(f"Error querying unused Flatpak runtimes: {e}")

        return results

    def _get_unused_snaps(self) -> List[PackageSuggestion]:
        """Queries snap list --all for disabled revisions and unused runtimes gracefully."""
        results: List[PackageSuggestion] = []
        snap_bin = shutil.which("snap")
        if not snap_bin:
            return results

        try:
            res = subprocess.run(
                [snap_bin, "list", "--all"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.splitlines()
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 6:
                        name = parts[0]
                        version = parts[1]
                        rev = parts[2]
                        notes = parts[-1]
                        if "disabled" in notes:
                            snap_path = f"/var/lib/snapd/snaps/{name}_{rev}.snap"
                            size = 0
                            try:
                                if os.path.isfile(snap_path):
                                    size = os.path.getsize(snap_path)
                            except OSError:
                                size = 0

                            full_spec = f"{name} --revision={rev}" if rev else name
                            is_prot, prot_reason = self.safety.is_package_safelisted(name, full_spec)
                            results.append(
                                PackageSuggestion(
                                    name=name,
                                    version=version,
                                    release=rev,
                                    arch="",
                                    size_bytes=size,
                                    summary=f"Disabled Snap revision ({notes})",
                                    category="snap_unused",
                                    reason=f"PROTECTED: {prot_reason}" if is_prot else f"Disabled Snap revision {rev} superseded by newer revision",
                                    is_protected=is_prot,
                                    is_selected=not is_prot,
                                )
                            )
        except Exception as e:
            self.logger.warning(f"Error querying disabled Snap revisions: {e}")

        return results

    def _get_repo_orphans(self) -> List[PackageSuggestion]:
        """
        Queries dnf repoquery --extras to identify installed packages that are
        no longer available in any active or enabled repository (retired packages / extras).
        """
        results: List[PackageSuggestion] = []
        if self.dnf_bin not in ["dnf5", "dnf"]:
            return results

        # Try cache-only mode (-C) first for fast execution without network roundtrips
        cmd_cache = [self.dnf_bin, "repoquery", "-C", "--extras"]
        cmd_live = [self.dnf_bin, "repoquery", "--extras"]

        env = os.environ.copy()
        if "HOME" not in env or not os.access(env["HOME"], os.W_OK):
            env["HOME"] = "/tmp"
        if "XDG_STATE_HOME" not in env or not os.access(env["XDG_STATE_HOME"], os.W_OK):
            env["XDG_STATE_HOME"] = "/tmp"
        if "XDG_CACHE_HOME" not in env or not os.access(env["XDG_CACHE_HOME"], os.W_OK):
            env["XDG_CACHE_HOME"] = "/tmp"

        res = None
        try:
            res = subprocess.run(cmd_cache, capture_output=True, text=True, check=False, timeout=30, env=env)
        except Exception:
            pass

        if not res or res.returncode != 0 or not res.stdout.strip():
            try:
                res = subprocess.run(cmd_live, capture_output=True, text=True, check=False, timeout=30, env=env)
            except Exception as e:
                self.logger.warning(f"Error querying retired packages via DNF: {e}")
                return results

        if res and res.returncode == 0 and res.stdout.strip():
            pkg_map = self._get_rpm_info_map()
            for line in res.stdout.splitlines():
                raw = line.strip()
                if not raw or "Repositories loaded" in raw or raw.startswith("Updating"):
                    continue

                clean = re.sub(r"-(\d+):", "-", raw)
                info = pkg_map.get(raw.lower()) or pkg_map.get(clean.lower())

                if info:
                    pname = info["name"]
                    pver = info["version"]
                    prel = info["release"]
                    parch = info["arch"]
                    psize = info["size"]
                    psummary = info["summary"]
                else:
                    m_pkg = re.match(r"^(.+?)-([0-9][^-]*)-([0-9].*)\.([^.]+)$", clean)
                    if m_pkg:
                        pname, pver, prel, parch = m_pkg.groups()
                    else:
                        pname = re.split(r"-\d", raw.split("-0:")[0])[0]
                        pver = "installed"
                        prel = ""
                        parch = "x86_64"
                    psize = 0
                    psummary = "Retired package (repo extra)"

                # Safety checks via SafetyEngine
                is_prot, prot_reason = self.safety.is_package_safelisted(pname, clean)
                if is_prot:
                    is_protected = True
                    is_selected = False
                    reason = f"PROTECTED: {prot_reason}"
                else:
                    is_protected = False
                    is_selected = True
                    reason = "Retired package no longer available in any enabled repository (repo orphan / extra)"

                results.append(
                    PackageSuggestion(
                        name=pname,
                        version=pver,
                        release=prel,
                        arch=parch,
                        size_bytes=psize,
                        summary=psummary,
                        category="repo_orphan",
                        reason=reason,
                        is_protected=is_protected,
                        is_selected=is_selected,
                    )
                )

        return results

    def scan_retired_packages(self) -> List[PackageSuggestion]:
        """Convenience method returning solely retired / repository-orphaned packages."""
        return self._get_repo_orphans()

    def get_removal_commands(self, packages: List[PackageSuggestion]) -> List[List[str]]:
        """Returns the list of individual raw CLI commands to remove selected packages/runtimes."""
        active_pkgs = [
            p for p in packages
            if not p.is_protected
            and p.is_selected
            and not (self.safety and self.safety.is_package_safelisted(p.name, getattr(p, "removal_spec", ""))[0])
        ]
        if not active_pkgs:
            return []

        commands: List[List[str]] = []

        # 1. RPM/DNF Packages
        dnf_targets = [
            p.removal_spec for p in active_pkgs
            if p.category in ("unneeded_dep", "old_kernel", "duplicate", "repo_orphan")
        ]
        if dnf_targets:
            commands.append([self.dnf_bin, "remove", "-y"] + dnf_targets)

        # 2. Flatpak Unused Runtimes
        flatpak_pkgs = [p for p in active_pkgs if p.category == "flatpak_unused"]
        if flatpak_pkgs and shutil.which("flatpak"):
            commands.append(["flatpak", "uninstall", "--unused", "-y"])

        # 3. Snap Disabled Revisions
        snap_pkgs = [p for p in active_pkgs if p.category == "snap_unused"]
        if snap_pkgs and shutil.which("snap"):
            for sp in snap_pkgs:
                if sp.release:
                    commands.append(["snap", "remove", sp.name, f"--revision={sp.release}"])
                else:
                    commands.append(["snap", "remove", sp.name])

        return commands

    def get_removal_command(self, packages: List[PackageSuggestion]) -> List[str]:
        """
        Returns a single unified CLI command to execute all removals.
        Elevates privileges ONCE for the entire batch via pkexec or sudo,
        preventing repeated password prompts for each entry.
        """
        cmds = self.get_removal_commands(packages)
        if not cmds:
            return []

        # If already root, run directly without privilege escalation wrappers
        if self.is_root:
            if len(cmds) == 1:
                return cmds[0]
            joined_str = " && ".join(" ".join(shlex.quote(arg) for arg in cmd) for cmd in cmds)
            return ["sh", "-c", joined_str]

        # Regular user: elevate privileges ONCE for the whole batch
        escalation = "pkexec" if shutil.which("pkexec") else ("sudo" if shutil.which("sudo") else None)

        if len(cmds) == 1:
            if escalation:
                return [escalation] + cmds[0]
            return cmds[0]

        # Multiple sub-commands (e.g. DNF + Snap, or multiple Snaps):
        # Wrap entire sequence inside a single elevated bash subshell
        joined_str = " && ".join(" ".join(shlex.quote(arg) for arg in cmd) for cmd in cmds)
        if escalation:
            return [escalation, "bash", "-c", joined_str]
        return ["sh", "-c", joined_str]

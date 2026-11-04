"""
App and Package Detector for ConfClean FC.
Detects installed RPM packages, Flatpaks, system binaries, desktop entries, and active processes.
"""

import os
import sys
import glob
import re
import shutil
import subprocess
from typing import Dict, List, Optional, Set, Tuple


class SystemDetector:
    """Detects installed packages, binaries, desktop files, and running processes."""

    # Common application name aliases and mappings to package/binary names
    COMMON_APP_MAPPINGS: Dict[str, List[str]] = {
        "code": ["code", "vscode", "visual-studio-code", "com.visualstudio.code"],
        "cursor": ["cursor", "cursor-bin"],
        "google-chrome": ["google-chrome", "google-chrome-stable", "chrome"],
        "chromium": ["chromium", "chromium-browser", "org.chromium.Chromium"],
        "brave-browser": ["brave-browser", "brave", "com.brave.Browser"],
        "firefox": ["firefox", "org.mozilla.firefox"],
        "thunderbird": ["thunderbird", "org.mozilla.Thunderbird"],
        "betterbird": ["betterbird", "eu.betterbird.Betterbird"],
        "bitwarden": ["bitwarden", "com.bitwarden.desktop"],
        "gimp": ["gimp", "org.gimp.GIMP"],
        "inkscape": ["inkscape", "org.inkscape.Inkscape"],
        "vlc": ["vlc", "org.videolan.VLC"],
        "steam": ["steam", "com.valvesoftware.Steam"],
        "discord": ["discord", "com.discordapp.Discord"],
        "slack": ["slack", "com.slack.Slack"],
        "spotify": ["spotify", "com.spotify.Client"],
        "telegram": ["telegram-desktop", "org.telegram.desktop"],
        "libreoffice": ["libreoffice", "org.libreoffice.LibreOffice"],
        "obs-studio": ["obs-studio", "com.obsproject.Studio"],
        "cura": ["cura", "ultimaker-cura", "com.ultimaker.cura"],
        "cura-lulzbot": ["cura-lulzbot"],
        "asunder": ["asunder"],
        "bleachbit": ["bleachbit", "org.bleachbit.BleachBit"],
        "virtualbox": ["virtualbox", "VirtualBox"],
        "android-studio": ["android-studio", "com.google.AndroidStudio"],
        "android open source project": ["android-studio", "android-tools", "adb"],
        "gitkraken": ["gitkraken", "com.axosoft.GitKraken"],
        "skype": ["skypeforlinux", "com.skype.Client"],
        "teams": ["teams", "teams-for-linux", "microsoft-teams"],
        "microsoft teams - preview": ["teams", "teams-for-linux"],
        "dconf": ["dconf", "dconf-editor"],
        "abrt": ["abrt", "libreport"],
        "nextcloud": ["nextcloud", "com.nextcloud.desktopclient.nextcloud"],
        "musicbrainz": ["picard", "org.musicbrainz.Picard"],
        "virt-manager": ["virt-manager", "virt-viewer"],
        "openscad": ["openscad", "org.openscad.OpenSCAD"],
        "brasero": ["brasero", "org.gnome.Brasero"],
        "zoom": ["zoom", "zoomus", "us.zoom.Zoom"],
        "audacity": ["audacity", "org.audacityteam.Audacity"],
        "krita": ["krita", "org.kde.krita"],
        "filezilla": ["filezilla", "org.filezillaproject.Filezilla"],
    }

    def __init__(self, refresh_on_init: bool = True):
        self.rpm_packages: Set[str] = set()
        self.flatpak_apps: Set[str] = set()
        self.snap_apps: Set[str] = set()
        self.binaries: Set[str] = set()
        self.desktop_files: Dict[str, Dict[str, str]] = {}
        self.desktop_execs: Set[str] = set()
        self.desktop_names: Set[str] = set()
        self.running_processes: Set[str] = set()
        self.initialized = False

        if refresh_on_init:
            self.refresh_all()

    def refresh_all(self):
        """Refreshes all detection caches."""
        self._load_rpm_packages()
        self._load_flatpak_apps()
        self._load_snap_apps()
        self._load_binaries()
        self._load_desktop_files()
        self._load_running_processes()
        self.initialized = True

    def _load_rpm_packages(self):
        """Loads all installed RPM package names using python-rpm or rpm command."""
        self.rpm_packages.clear()
        try:
            import rpm
            ts = rpm.TransactionSet()
            mi = ts.dbMatch()
            for h in mi:
                pkg_name = h["name"]
                if pkg_name:
                    self.rpm_packages.add(pkg_name.lower())
            if self.rpm_packages:
                return
        except Exception:
            pass

        # Fallback to rpm -qa if python-rpm is unavailable
        try:
            res = subprocess.run(
                ["rpm", "-qa", "--qf", "%{NAME}\\n"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    name = line.strip().lower()
                    if name:
                        self.rpm_packages.add(name)
        except Exception:
            pass

    def _load_flatpak_apps(self):
        """Loads installed Flatpak application IDs."""
        self.flatpak_apps.clear()
        try:
            res = subprocess.run(
                ["flatpak", "list", "--columns=application"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    appid = line.strip()
                    if appid and appid.lower() != "application id":
                        self.flatpak_apps.add(appid.lower())
        except Exception:
            pass

    def _load_snap_apps(self):
        """Loads installed Snap package names gracefully."""
        self.snap_apps.clear()
        if not shutil.which("snap"):
            return
        try:
            res = subprocess.run(
                ["snap", "list"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines()[1:]:
                    parts = line.split()
                    if parts:
                        self.snap_apps.add(parts[0].lower())
        except Exception:
            pass

    def _load_binaries(self):
        """Loads all executable binaries found in system PATH."""
        self.binaries.clear()
        path_env = os.environ.get("PATH", "/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin")
        search_dirs = path_env.split(":")
        home_bin = os.path.expanduser("~/.local/bin")
        if home_bin not in search_dirs:
            search_dirs.append(home_bin)

        for directory in search_dirs:
            if os.path.isdir(directory):
                try:
                    for entry in os.listdir(directory):
                        self.binaries.add(entry.lower())
                except OSError:
                    continue

    def _load_desktop_files(self):
        """Scans .desktop files to index application names and exec commands."""
        self.desktop_files.clear()
        self.desktop_execs.clear()
        self.desktop_names.clear()

        desktop_dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications"),
        ]

        for directory in desktop_dirs:
            if not os.path.isdir(directory):
                continue
            for file_name in os.listdir(directory):
                if not file_name.endswith(".desktop"):
                    continue
                file_path = os.path.join(directory, file_name)
                base_name = file_name[:-8].lower()
                self.desktop_names.add(base_name)

                entry_info = {"name": base_name, "exec": "", "path": file_path}
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("Exec="):
                                raw_exec = line[5:].strip()
                                # Extract binary name from Exec command
                                parts = raw_exec.split()
                                if parts:
                                    cmd = os.path.basename(parts[0]).lower()
                                    entry_info["exec"] = cmd
                                    self.desktop_execs.add(cmd)
                            elif line.startswith("Name=") and "title" not in entry_info:
                                entry_info["title"] = line[5:].strip()
                    self.desktop_files[base_name] = entry_info
                except OSError:
                    continue

    def _load_running_processes(self):
        """Scans /proc for currently running process names."""
        self.running_processes.clear()
        try:
            for pid_dir in glob.glob("/proc/[0-9]*"):
                comm_path = os.path.join(pid_dir, "comm")
                if os.path.isfile(comm_path):
                    try:
                        with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                            comm = f.read().strip().lower()
                            if comm:
                                self.running_processes.add(comm)
                    except OSError:
                        continue
        except Exception:
            pass

    def check_app_status(self, folder_or_file_name: str) -> Tuple[bool, str, str, str]:
        """
        Determines if an application configuration or folder is actively installed.
        Returns:
            (is_active: bool, matched_target: str, match_type: str, details: str)
        """
        raw_name = folder_or_file_name.strip()
        lower_name = raw_name.lower()

        # Clean common prefixes and suffixes (e.g. .conf, .list, dot-files)
        clean_name = re.sub(r"^\.+", "", lower_name)
        clean_name = re.sub(r"\.(conf|list|cfg|ini|desktop|json|rc)$", "", clean_name)

        # 1. Check running processes first (Active protection!)
        if clean_name in self.running_processes:
            return True, clean_name, "process", f"Active process running: {clean_name}"

        # 2. Check installed Flatpaks and Snaps
        for flatpak_id in self.flatpak_apps:
            if lower_name == flatpak_id or clean_name == flatpak_id:
                return True, flatpak_id, "flatpak", f"Installed Flatpak: {flatpak_id}"
            # Check if clean_name matches any segment or is part of reverse-DNS
            id_parts = flatpak_id.split(".")
            if any(clean_name == part.lower() for part in id_parts) or clean_name in flatpak_id:
                return True, flatpak_id, "flatpak", f"Matches Flatpak component: {flatpak_id}"

        if clean_name in self.snap_apps or lower_name in self.snap_apps:
            return True, clean_name, "snap", f"Installed Snap package: {clean_name}"

        # 3. Check known mappings
        if lower_name in self.COMMON_APP_MAPPINGS or clean_name in self.COMMON_APP_MAPPINGS:
            aliases = self.COMMON_APP_MAPPINGS.get(lower_name, []) or self.COMMON_APP_MAPPINGS.get(clean_name, [])
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in self.rpm_packages:
                    return True, alias, "rpm", f"Installed RPM package: {alias}"
                if alias_lower in self.flatpak_apps:
                    return True, alias, "flatpak", f"Installed Flatpak: {alias}"
                if alias_lower in self.binaries:
                    return True, alias, "binary", f"Binary found in PATH: {alias}"
                if alias_lower in self.desktop_execs or alias_lower in self.desktop_names:
                    return True, alias, "desktop", f"Desktop entry found: {alias}"

        # 4. Check RPM package database directly
        if clean_name in self.rpm_packages:
            return True, clean_name, "rpm", f"Installed RPM package: {clean_name}"

        # Look for version-suffixed or standard subpackage suffixes (e.g., gimp-2.0 -> gimp, vim-common -> vim)
        # But do not split on distinct app names (like cura-lulzbot)
        suffix_match = re.match(r"^([a-z0-9]+)[-_]((\d+(\.\d+)*)|(common|libs|data|core|desktop|client|server|gui|cli))$", clean_name)
        if suffix_match:
            base_word = suffix_match.group(1)
            if len(base_word) >= 3:
                if base_word in self.rpm_packages:
                    return True, base_word, "rpm", f"Matches RPM package base: {base_word}"
                if base_word in self.binaries:
                    return True, base_word, "binary", f"Base command found in PATH: {base_word}"

        # 5. Check System Executables
        if clean_name in self.binaries:
            return True, clean_name, "binary", f"Binary found in PATH: {clean_name}"

        # 6. Check Desktop Applications
        if clean_name in self.desktop_names or clean_name in self.desktop_execs:
            return True, clean_name, "desktop", f"Desktop launcher found for: {clean_name}"

        for d_name in self.desktop_names:
            if clean_name in d_name:
                return True, d_name, "desktop", f"Desktop launcher matches: {d_name}"

        # If none matched: not currently installed
        return False, "", "none", f"No installed RPM, Flatpak, or binary found for '{folder_or_file_name}'"

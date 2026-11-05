"""
Safelist and Security Engine for ConfClean FC.
Guarantees that critical system files, desktop environments, credentials,
and user-whitelisted items are never deleted.
"""

import fnmatch
import json
import os
import re
from typing import List, Set, Tuple


class SafetyEngine:
    """Rigorous safelist checks to prevent system breakage."""

    # Never delete or touch these patterns in user configuration directories
    CORE_SYSTEM_PATTERNS: List[str] = [
        # Desktop environments & session managers
        "dconf*",
        "gnome*",
        "*gsd*",
        "kde*",
        "plasma*",
        "xfce*",
        "cinnamon*",
        "mate*",
        "lxqt*",
        "sway*",
        "hyprland*",
        "session*",
        "autostart*",
        "background*",
        "monitors.xml",
        "mimeapps.list",
        "user-dirs.*",
        "environment.d*",
        "gtk-*",
        "glib-*",
        "gsettings*",
        "fontconfig*",
        "xkb*",
        "wayland*",
        "ibus*",
        "imsettings*",
        "menus*",
        "system-bus*",
        ".cache",
        # Audio, video, and hardware plumbing
        "pipewire*",
        "pulse*",
        "pulseaudio*",
        "wireplumber*",
        "alsa*",
        "sound*",
        "mesa*",
        "vulkan*",
        "dri*",
        "nvidia*",
        # System daemons and plumbing
        "systemd*",
        "dbus*",
        "polkit*",
        "NetworkManager*",
        "networkmanagement*",
        "wpa_supplicant*",
        "bluetooth*",
        "upower*",
        "power*",
        "accounts*",
        # Security, Auth, Crypto, SSH, GPG (Absolute Protection)
        "*ssh*",
        "*gnupg*",
        "*pki*",
        "*keyring*",
        "*secret*",
        "*crypto*",
        "*wallet*",
        "*password*",
        "*token*",
        "*cert*",
        # Shells and runtime environments
        ".bash*",
        ".zsh*",
        ".profile*",
        ".fish*",
        "bash*",
        "zsh*",
        "fish*",
        # Developer toolchains, version control, and configs
        ".git*",
        "git*",
        ".cargo*",
        ".rustup*",
        ".gradle*",
        ".m2*",
        ".dotnet*",
        # Package and system update managers
        "dnf*",
        "rpm*",
        "flatpak*",
        "packagekit*",
    ]

    # Directories that must never be targeted by cleaners
    PROTECTED_ROOT_DIRS: Set[str] = {
        "/",
        "/boot",
        "/usr",
        "/lib",
        "/lib64",
        "/bin",
        "/sbin",
        "/proc",
        "/sys",
        "/dev",
        "/run",
        "/home",
        "/root",
    }

    # Core /etc files that must never be modified
    PROTECTED_ETC_FILES: Set[str] = {
        "/etc/passwd",
        "/etc/shadow",
        "/etc/group",
        "/etc/gshadow",
        "/etc/fstab",
        "/etc/hosts",
        "/etc/hostname",
        "/etc/os-release",
        "/etc/fedora-release",
        "/etc/redhat-release",
        "/etc/sudoers",
        "/etc/sudoers.d",
        "/etc/security",
        "/etc/pam.d",
        "/etc/dnf/dnf.conf",
        "/etc/rpm",
        "/etc/selinux",
        "/etc/systemd",
        "/etc/resolv.conf",
        "/etc/nsswitch.conf",
        "/etc/crypttab",
        "/etc/locale.conf",
        "/etc/vconsole.conf",
    }

    # Core system packages that must never be removed
    CORE_PROTECTED_PACKAGES: Set[str] = {
        "confclean-fc",
        "confclean",
        "glibc",
        "systemd",
        "kernel",
        "kernel-core",
        "rpm",
        "dnf",
        "dnf5",
        "setup",
        "basesystem",
        "filesystem",
        "bash",
        "coreutils",
        "selinux-policy",
        "shadow-utils",
        "util-linux",
        "polkit",
    }

    def __init__(self, config_dir: str = None):
        self.config_dir = config_dir or os.path.expanduser("~/.config/confclean-fc")
        self.whitelist_file = os.path.join(self.config_dir, "custom_whitelist.json")
        self.user_whitelist: List[str] = []
        self._load_user_whitelist()

    def load_user_whitelist(self):
        """Loads or reloads user-defined custom whitelist patterns from JSON."""
        self._load_user_whitelist()

    def _load_user_whitelist(self):
        """Loads user-defined custom whitelist patterns from JSON."""
        self.user_whitelist.clear()
        if os.path.isfile(self.whitelist_file):
            try:
                with open(self.whitelist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.user_whitelist = [str(x).strip() for x in data if str(x).strip()]
            except Exception:
                pass

    def save_user_whitelist(self):
        """Saves user-defined custom whitelist patterns to JSON."""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.whitelist_file, "w", encoding="utf-8") as f:
                json.dump(self.user_whitelist, f, indent=2)
        except Exception:
            pass

    def add_user_whitelist(self, pattern: str) -> bool:
        """Adds a new custom whitelist pattern or path."""
        p = pattern.strip()
        if p and p not in self.user_whitelist:
            self.user_whitelist.append(p)
            self.save_user_whitelist()
            return True
        return False

    def remove_user_whitelist(self, pattern: str) -> bool:
        """Removes a pattern from user whitelist."""
        p = pattern.strip()
        if p in self.user_whitelist:
            self.user_whitelist.remove(p)
            self.save_user_whitelist()
            return True
        return False

    def is_safelisted(self, path_or_name: str) -> Tuple[bool, str]:
        """
        Evaluates whether a given file, folder, or name is protected.
        Returns:
            (is_protected: bool, reason: str)
        """
        raw = path_or_name.strip()
        norm_path = os.path.abspath(raw) if ("/" in raw or "\\" in raw) else raw
        basename = os.path.basename(norm_path).lower()
        clean_name = re.sub(r"^\.+", "", basename)

        # 1. System Root & Essential Protected Paths
        if norm_path in self.PROTECTED_ROOT_DIRS:
            return True, f"Critical system root directory: {norm_path}"

        for etc_prot in self.PROTECTED_ETC_FILES:
            if norm_path == etc_prot or norm_path.startswith(etc_prot + "/"):
                return True, f"Essential system configuration: {etc_prot}"

        # 2. Check User Whitelist
        for user_pat in self.user_whitelist:
            pat_lower = user_pat.lower()
            if fnmatch.fnmatch(basename, pat_lower) or fnmatch.fnmatch(clean_name, pat_lower):
                return True, f"User custom whitelist match: '{user_pat}'"
            if norm_path == user_pat or norm_path.startswith(user_pat.rstrip("/") + "/"):
                return True, f"User custom whitelist path: '{user_pat}'"

        # 3. Security, SSH, GPG, PKI, Tokens
        sec_keywords = ["ssh", "gnupg", "pki", "keyring", "secret", "crypto", "wallet", "token", "cert", "credentials"]
        path_lower = norm_path.lower()
        for kw in sec_keywords:
            if kw in basename:
                return True, f"Protected security/credential storage: '{basename}' contains '{kw}'"
            # Protect if any folder in hierarchy contains security keyword (e.g. ~/.ssh/id_rsa)
            for part in path_lower.split(os.sep):
                if kw in part:
                    return True, f"Protected security/credential storage: parent directory '{part}' contains '{kw}'"

        # 4. Core System Patterns
        for pat in self.CORE_SYSTEM_PATTERNS:
            if fnmatch.fnmatch(basename, pat.lower()) or fnmatch.fnmatch(clean_name, pat.lower()):
                return True, f"Core system/desktop component: matches pattern '{pat}'"

        return False, ""

    def is_package_safelisted(
        self,
        package_name: str,
        full_spec: str = "",
        check_core: bool = True,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether an RPM, Flatpak, or Snap package is protected by system safelist
        or user custom whitelist.
        Returns:
            (is_protected: bool, reason: str)
        """
        raw_name = (package_name or "").strip()
        if not raw_name:
            return False, ""
        name_lower = raw_name.lower()
        spec_lower = (full_spec or "").strip().lower()

        # 1. User Custom Safelist (always checked first)
        for user_pat in self.user_whitelist:
            pat_lower = user_pat.lower()
            if fnmatch.fnmatch(name_lower, pat_lower):
                return True, f"User safelist match: '{user_pat}'"
            if spec_lower and fnmatch.fnmatch(spec_lower, pat_lower):
                return True, f"User safelist match: '{user_pat}'"

        if not check_core:
            return False, ""

        # 2. ConfClean FC Application Integrity
        if name_lower in ("confclean-fc", "confclean"):
            return True, "ConfClean FC core application"

        # 3. Critical System Packages
        if name_lower in self.CORE_PROTECTED_PACKAGES or name_lower.startswith("kernel-core"):
            return True, f"Core system package ({raw_name})"

        # 4. Desktop & Plumbing System Patterns (e.g. systemd*, gnome*, pipewire*)
        for pat in self.CORE_SYSTEM_PATTERNS:
            if fnmatch.fnmatch(name_lower, pat.lower()):
                return True, f"Core system component: matches pattern '{pat}'"

        return False, ""

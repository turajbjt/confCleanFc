"""
Application Factory Reset Engine for ConfClean FC.
Safely wipes user configuration, cache, and state for specific installed apps
to restore them to fresh install defaults with automatic pre-reset backups.
"""

import glob
import os
import shutil
from typing import Callable, Dict, List, Optional, Tuple

from confclean.core.backup_manager import BackupManager
from confclean.core.detector import SystemDetector
from confclean.core.logger import get_logger
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ScanItem, get_path_stats


class AppResetProfile:
    """Represents an application that can be reset to factory defaults."""

    def __init__(
        self,
        app_id: str,
        name: str,
        description: str,
        target_paths: List[str],
        size_bytes: int = 0,
        file_count: int = 0,
        is_installed: bool = False,
    ):
        self.app_id = app_id
        self.name = name
        self.description = description
        self.target_paths = target_paths
        self.size_bytes = size_bytes
        self.file_count = file_count
        self.is_installed = is_installed

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


class AppResetter:
    """Manages discovery and factory resetting of desktop apps."""

    KNOWN_PROFILES = [
        {
            "id": "firefox",
            "name": "Mozilla Firefox",
            "desc": "Resets browser profiles, history, cookies, and local addons.",
            "patterns": ["~/.mozilla/firefox", "~/.cache/mozilla/firefox"],
        },
        {
            "id": "chrome",
            "name": "Google Chrome",
            "desc": "Resets user profiles, extensions, history, and cached web data.",
            "patterns": ["~/.config/google-chrome", "~/.cache/google-chrome"],
        },
        {
            "id": "chromium",
            "name": "Chromium",
            "desc": "Resets Chromium browser profiles, settings, and cache.",
            "patterns": ["~/.config/chromium", "~/.cache/chromium"],
        },
        {
            "id": "brave",
            "name": "Brave Browser",
            "desc": "Resets Brave shields, wallet configuration, and browser cache.",
            "patterns": ["~/.config/BraveSoftware", "~/.cache/BraveSoftware"],
        },
        {
            "id": "cursor",
            "name": "Cursor Editor",
            "desc": "Resets editor settings, extensions, keybindings, and workspace cache.",
            "patterns": ["~/.config/Cursor", "~/.cache/Cursor", "~/.cursor"],
        },
        {
            "id": "vscode",
            "name": "Visual Studio Code",
            "desc": "Resets user settings, extensions, and cached workbench state.",
            "patterns": ["~/.config/Code", "~/.cache/Code", "~/.vscode"],
        },
        {
            "id": "libreoffice",
            "name": "LibreOffice",
            "desc": "Resets word processor templates, dictionaries, and user profiles.",
            "patterns": ["~/.config/libreoffice"],
        },
        {
            "id": "gimp",
            "name": "GIMP Image Editor",
            "desc": "Resets user brushes, tool presets, color palettes, and UI layout.",
            "patterns": ["~/.config/GIMP", "~/.gimp*"],
        },
        {
            "id": "inkscape",
            "name": "Inkscape",
            "desc": "Resets vector graphics preferences, dialog state, and cache.",
            "patterns": ["~/.config/inkscape", "~/.cache/inkscape"],
        },
        {
            "id": "vlc",
            "name": "VLC Media Player",
            "desc": "Resets audio/video playback settings, codecs cache, and history.",
            "patterns": ["~/.config/vlc", "~/.cache/vlc"],
        },
        {
            "id": "discord",
            "name": "Discord",
            "desc": "Resets local Discord login state, voice configs, and cached assets.",
            "patterns": ["~/.config/discord", "~/.cache/discord"],
        },
        {
            "id": "steam",
            "name": "Steam Client Settings",
            "desc": "Resets Steam UI state, htmlcache, and client configs (keeps games).",
            "patterns": ["~/.steam/steam/config", "~/.steam/steam/htmlcache"],
        },
        {
            "id": "blender",
            "name": "Blender 3D",
            "desc": "Resets 3D viewport preferences, startup blend file, and add-ons.",
            "patterns": ["~/.config/blender"],
        },
        {
            "id": "thunderbird",
            "name": "Mozilla Thunderbird",
            "desc": "Resets email profiles, cached messages, and mail accounts.",
            "patterns": ["~/.thunderbird", "~/.cache/thunderbird"],
        },
        {
            "id": "slack",
            "name": "Slack",
            "desc": "Resets workspace session, notification settings, and cached assets.",
            "patterns": ["~/.config/Slack", "~/.cache/Slack"],
        },
        {
            "id": "nextcloud",
            "name": "Nextcloud Desktop",
            "desc": "Resets server sync connections, account logins, and preferences (keeps local files).",
            "patterns": ["~/.config/Nextcloud"],
        },
        {
            "id": "cura",
            "name": "Ultimaker Cura",
            "desc": "Resets 3D printer definitions, slicing profiles, materials, and plugin caches.",
            "patterns": ["~/.config/cura", "~/.cache/cura"],
        },
        {
            "id": "gitkraken",
            "name": "GitKraken",
            "desc": "Resets Git GUI preferences, workspace layout, and cached repositories.",
            "patterns": ["~/.config/GitKraken", "~/.cache/GitKraken"],
        },
        {
            "id": "android-studio",
            "name": "Android Studio",
            "desc": "Resets IDE user configurations, custom plugins, UI themes, and workspace caches.",
            "patterns": ["~/.config/Google/AndroidStudio*", "~/.cache/Google/AndroidStudio*"],
        },
        {
            "id": "musicbrainz",
            "name": "MusicBrainz Picard",
            "desc": "Resets audio tagger settings, plugin configs, and acoustic fingerprint cache.",
            "patterns": ["~/.config/MusicBrainz", "~/.cache/MusicBrainz"],
        },
        {
            "id": "virt-manager",
            "name": "Virtual Machine Manager",
            "desc": "Resets virt-manager UI preferences and connection list (does not delete VM disk images).",
            "patterns": ["~/.config/virt-manager"],
        },
        {
            "id": "openscad",
            "name": "OpenSCAD",
            "desc": "Resets 3D CAD editor settings, color schemes, and recently opened models.",
            "patterns": ["~/.config/OpenSCAD"],
        },
        {
            "id": "brasero",
            "name": "Brasero Disc Burner",
            "desc": "Resets optical media burning preferences and temporary disc project caches.",
            "patterns": ["~/.config/brasero", "~/.cache/brasero"],
        },
        {
            "id": "spotify",
            "name": "Spotify",
            "desc": "Resets Spotify client settings, offline song cache, and local login session.",
            "patterns": ["~/.config/spotify", "~/.cache/spotify"],
        },
        {
            "id": "zoom",
            "name": "Zoom Video Communications",
            "desc": "Resets Zoom audio/video device preferences, meeting history, and cached assets.",
            "patterns": ["~/.config/zoomus", "~/.zoom"],
        },
        {
            "id": "obs-studio",
            "name": "OBS Studio",
            "desc": "Resets streaming/recording profiles, scene collections, and video encoder presets.",
            "patterns": ["~/.config/obs-studio"],
        },
        {
            "id": "audacity",
            "name": "Audacity",
            "desc": "Resets audio editor toolbar layouts, VST/plugin scan databases, and temporary caches.",
            "patterns": ["~/.config/audacity", "~/.cache/audacity"],
        },
        {
            "id": "krita",
            "name": "Krita Digital Painting",
            "desc": "Resets drawing brushes, canvas color palettes, shortcuts, and cache.",
            "patterns": ["~/.config/krita*", "~/.cache/krita"],
        },
        {
            "id": "telegram",
            "name": "Telegram Desktop",
            "desc": "Resets local session data, media cache, and theme settings.",
            "patterns": ["~/.local/share/TelegramDesktop"],
        },
        {
            "id": "filezilla",
            "name": "FileZilla FTP Client",
            "desc": "Resets FTP client UI layout, transfer queue, and site manager preferences.",
            "patterns": ["~/.config/filezilla"],
        },
    ]

    def __init__(
        self,
        detector: Optional[SystemDetector] = None,
        backup_mgr: Optional[BackupManager] = None,
        safety: Optional[SafetyEngine] = None,
    ):
        self.detector = detector or SystemDetector()
        self.backup_mgr = backup_mgr or BackupManager()
        self.safety = safety or SafetyEngine()
        self.logger = get_logger()

    def discover_reset_profiles(self) -> List[AppResetProfile]:
        """Discovers installed applications that currently have configuration on disk."""
        profiles: List[AppResetProfile] = []

        # 1. Known Applications
        for defn in self.KNOWN_PROFILES:
            app_id = defn["id"]
            name = defn["name"]
            desc = defn["desc"]
            raw_patterns = defn["patterns"]

            resolved_paths = []
            total_size = 0
            total_count = 0

            for pat in raw_patterns:
                expanded = os.path.expanduser(pat)
                matches = glob.glob(expanded)
                for m in matches:
                    if os.path.exists(m):
                        resolved_paths.append(m)
                        s, c, _ = get_path_stats(m)
                        total_size += s
                        total_count += c

            # Check if installed or has data
            is_active, _, _, _ = self.detector.check_app_status(app_id)
            if not is_active:
                is_active, _, _, _ = self.detector.check_app_status(name)

            if resolved_paths and (is_active or total_size > 0):
                profiles.append(
                    AppResetProfile(
                        app_id=app_id,
                        name=name,
                        description=desc,
                        target_paths=resolved_paths,
                        size_bytes=total_size,
                        file_count=total_count,
                        is_installed=is_active,
                    )
                )

        # 2. Dynamic Flatpak Applications in ~/.var/app/
        flatpak_root = os.path.expanduser("~/.var/app")
        if os.path.isdir(flatpak_root):
            try:
                for entry in sorted(os.listdir(flatpak_root)):
                    flatpak_dir = os.path.join(flatpak_root, entry)
                    if os.path.isdir(flatpak_dir):
                        s, c, _ = get_path_stats(flatpak_dir)
                        profiles.append(
                            AppResetProfile(
                                app_id=f"flatpak_{entry}",
                                name=f"Flatpak: {entry}",
                                description=f"Resets sandboxed Flatpak data, cache, and preferences for {entry}.",
                                target_paths=[flatpak_dir],
                                size_bytes=s,
                                file_count=c,
                                is_installed=entry.lower() in self.detector.flatpak_apps,
                            )
                        )
            except OSError:
                pass

        return profiles

    def reset_app(
        self,
        profile: AppResetProfile,
        create_backup: bool = True,
        dry_run: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Tuple[bool, Optional[str], str]:
        """
        Safely resets an application to factory defaults.
        Automatically creates a safety backup before wiping!
        Returns:
            (success: bool, backup_archive: Optional[str], message: str)
        """
        if not profile.target_paths:
            return False, None, "No configuration paths exist for this application."

        # Convert target paths into ScanItem objects for BackupManager
        scan_items = []
        for p in profile.target_paths:
            if not os.path.exists(p):
                continue
            is_safe, reason = self.safety.is_safelisted(p)
            if is_safe:
                return False, None, f"Refusing to reset protected system component: {p} ({reason})"

            s, c, m = get_path_stats(p)
            scan_items.append(
                ScanItem(
                    path=p,
                    name=os.path.basename(p),
                    category="app_reset",
                    is_directory=os.path.isdir(p),
                    size_bytes=s,
                    file_count=c,
                    last_modified=m,
                    status="RESET_TARGET",
                    reason=f"Factory reset requested for {profile.name}",
                )
            )

        if not scan_items:
            return False, None, "No files found to reset."

        if dry_run:
            self.logger.info(f"DRY RUN: Simulating reset of {profile.name} ({profile.formatted_size})")
            return (
                True,
                None,
                f"[DRY RUN] Would reset '{profile.name}' ({profile.formatted_size}, {profile.file_count} files) across {len(scan_items)} paths. No files deleted.",
            )

        backup_archive = None
        # 1. Create safety backup
        if create_backup:
            if progress_callback:
                progress_callback("Creating safety backup before reset...", 0, len(scan_items))
            ok, arch_path, log_p, b_msg = self.backup_mgr.create_backup(
                scan_items,
                label=f"reset_{profile.app_id}",
                progress_callback=progress_callback,
            )
            if not ok:
                return False, None, f"Reset aborted: Backup creation failed ({b_msg})"
            backup_archive = arch_path

        # 2. Wipe the application configuration
        total = len(profile.target_paths)
        for idx, p in enumerate(profile.target_paths):
            if progress_callback:
                progress_callback(f"Resetting {os.path.basename(p)}...", idx + 1, total)

            if not os.path.exists(p):
                continue

            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)

                self.logger.audit_event(
                    action="APP_RESET",
                    target_path=p,
                    size_bytes=profile.size_bytes,
                    status="SUCCESS",
                    backup_archive=backup_archive,
                    details=f"Reset {profile.name} to fresh install defaults",
                )
            except Exception as e:
                err_msg = f"Failed to remove {p}: {e}"
                self.logger.error(err_msg)
                return False, backup_archive, err_msg

        return (
            True,
            backup_archive,
            f"Successfully reset '{profile.name}' to fresh install defaults! (Backup archived)",
        )

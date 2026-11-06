"""
Main GUI Application Window for ConfClean FC.
Coordinates sidebar navigation, header status, and all feature views.
"""

import os
import sys
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from confclean import __version__
from confclean.core.app_resetter import AppResetter
from confclean.core.backup_manager import BackupManager
from confclean.core.cache_cleaner import CacheCleaner
from confclean.core.cleaner import SafeCleaner
from confclean.core.detector import SystemDetector
from confclean.core.logger import get_logger
from confclean.core.package_manager import PackageManager
from confclean.core.restore_manager import RestoreManager
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ConfigScanner
from confclean.core.selinux_manager import SELinuxManager
from confclean.gui.styles import ADWAITA_DARK_STYLE
from confclean.gui.tab_apps import AppConfigsTab
from confclean.gui.tab_cache import CacheTab
from confclean.gui.tab_logs import LogsTab
from confclean.gui.tab_packages import PackageTab
from confclean.gui.tab_restore import RestoreTab
from confclean.gui.tab_settings import SettingsTab


class MainWindow(QMainWindow):
    """Primary application window with sidebar navigation."""

    def __init__(
        self,
        scanner: ConfigScanner = None,
        cleaner: SafeCleaner = None,
        safety: SafetyEngine = None,
        backup_mgr: BackupManager = None,
        restore_mgr: RestoreManager = None,
        cache_cleaner: CacheCleaner = None,
        pkg_mgr: PackageManager = None,
        app_resetter: AppResetter = None,
        selinux_mgr: SELinuxManager = None,
        auto_scan_on_nav: bool = True,
    ):
        super().__init__()
        self.setWindowTitle("ConfClean FC - Fedora & RPM System Cleaner")
        self.resize(1150, 720)
        self.setMinimumSize(900, 580)
        self.auto_scan_on_nav = auto_scan_on_nav

        # Ensure application identity and desktop file mapping for Wayland/GNOME
        app_inst = QApplication.instance()
        if app_inst:
            if not app_inst.desktopFileName():
                app_inst.setDesktopFileName("confclean-fc")
            if not app_inst.applicationName():
                app_inst.setApplicationName("confclean-fc")

        # Set window icon
        self.app_icon_path = None
        icon_candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.svg"),
            "/usr/share/confclean-fc/assets/icon.svg",
            "/usr/share/icons/hicolor/scalable/apps/confclean-fc.svg",
            "/usr/share/icons/hicolor/256x256/apps/confclean-fc.png",
        ]
        for icon_path in icon_candidates:
            if os.path.isfile(icon_path):
                self.app_icon_path = icon_path
                self.setWindowIcon(QIcon(icon_path))
                if app_inst:
                    app_inst.setWindowIcon(QIcon(icon_path))
                break

        # Initialize core engines
        self.logger = get_logger()
        self.safety = safety or SafetyEngine()
        self.detector = SystemDetector(refresh_on_init=False) if (scanner or app_resetter) else SystemDetector()
        self.backup_mgr = backup_mgr or BackupManager()
        self.restore_mgr = restore_mgr or RestoreManager()
        self.cleaner = cleaner or SafeCleaner(safety=self.safety, backup_mgr=self.backup_mgr)
        self.scanner = scanner or ConfigScanner(detector=self.detector, safety=self.safety)
        self.cache_cleaner = cache_cleaner or CacheCleaner(safety=self.safety)
        self.pkg_mgr = pkg_mgr or PackageManager(safety=self.safety)
        self.selinux_mgr = selinux_mgr or SELinuxManager()
        self.app_resetter = app_resetter or AppResetter(
            detector=self.detector,
            backup_mgr=self.backup_mgr,
            safety=self.safety,
        )

        self._init_ui()
        self.logger.info("ConfClean FC GUI initialized.")

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top Header Bar
        header = QFrame()
        header.setObjectName("header_bar")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 10, 18, 10)
        h_layout.setSpacing(10)

        # App Logo Icon left of the application title (75% larger: 42x42 px)
        logo_icon = QIcon(self.app_icon_path) if getattr(self, "app_icon_path", None) else self.windowIcon()
        if not logo_icon.isNull():
            pix = logo_icon.pixmap(42, 42)
            if not pix.isNull():
                self.lbl_logo = QLabel()
                self.lbl_logo.setObjectName("app_logo")
                self.lbl_logo.setPixmap(pix)
                self.lbl_logo.setFixedSize(42, 42)
                self.lbl_logo.setScaledContents(True)
                h_layout.addWidget(self.lbl_logo)

        title_lbl = QLabel("ConfClean FC")
        title_lbl.setObjectName("app_title")
        h_layout.addWidget(title_lbl)

        version_badge = QLabel(f"v{__version__} (Fedora)")
        version_badge.setStyleSheet("color: #787878; font-size: 11px; margin-left: 4px;")
        h_layout.addWidget(version_badge)

        h_layout.addStretch()

        # Reclaimable Space Pill
        self.lbl_reclaimable = QLabel("Reclaimable: Scan Required")
        self.lbl_reclaimable.setObjectName("pill_badge")
        h_layout.addWidget(self.lbl_reclaimable)

        # Mode Badge (Root vs User)
        is_root = (os.geteuid() == 0)
        user_name = os.environ.get("USER", "root" if is_root else "user")
        mode_pill = QLabel(f"Mode: {'Root (System Administrator)' if is_root else f'User ({user_name})'}")
        if is_root:
            mode_pill.setObjectName("pill_root")
        else:
            mode_pill.setObjectName("pill_badge")
        h_layout.addWidget(mode_pill)

        # Elevate Button if running unprivileged (Top-Right Header Action)
        if not is_root:
            self.btn_elevate = QPushButton("🛡️ Relaunch as Root (pkexec)")
            self.btn_elevate.setProperty("class", "primary")
            self.btn_elevate.setToolTip("Relaunch ConfClean FC with root / administrative privileges via pkexec")
            self.btn_elevate.clicked.connect(self._relaunch_as_root)
            h_layout.addWidget(self.btn_elevate)

        main_layout.addWidget(header)

        # Body Layout: Sidebar + Stacked Views
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left Navigation Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("nav_sidebar")
        self.sidebar.setFixedWidth(230)
        self.sidebar.setIconSize(QSize(20, 20))

        nav_items = [
            ("📱  Application Configs", "apps"),
            ("🧹  Cache & Junk", "cache"),
            ("📦  Packages & System", "packages"),
            ("🗄️  Restore & Backups", "restore"),
            ("📋  Audit Logs", "logs"),
            ("⚙️  Settings & Safelist", "settings"),
        ]

        for text, key in nav_items:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar.addItem(item)

        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        body_layout.addWidget(self.sidebar)

        # Stacked Views Widget
        self.stack = QStackedWidget()

        # 1. Unified Application Configs Tab (Leftovers + Factory Reset)
        self.tab_apps = AppConfigsTab(self.scanner, self.cleaner, self.safety, self.app_resetter)
        self.tab_apps.status_changed.connect(self._on_scanner_stats_changed)
        # Expose tab_scanner and tab_reset as direct references for backward compatibility
        self.tab_scanner = self.tab_apps.tab_scanner
        self.tab_reset = self.tab_apps.tab_reset
        self.stack.addWidget(self.tab_apps)

        # 2. Cache Tab
        self.tab_cache = CacheTab(self.cache_cleaner)
        self.stack.addWidget(self.tab_cache)

        # 3. Packages & System Tab
        self.tab_packages = PackageTab(
            self.pkg_mgr,
            selinux_mgr=self.selinux_mgr,
            cache_cleaner=self.cache_cleaner,
            safety=self.safety,
        )
        self.stack.addWidget(self.tab_packages)

        # 4. Restore Tab
        self.tab_restore = RestoreTab(self.backup_mgr, self.restore_mgr)
        self.stack.addWidget(self.tab_restore)

        # 5. Logs Tab
        self.tab_logs = LogsTab(self.logger)
        self.stack.addWidget(self.tab_logs)

        # 6. Settings Tab
        self.tab_settings = SettingsTab(self.safety)
        self.stack.addWidget(self.tab_settings)

        body_layout.addWidget(self.stack, stretch=1)
        main_layout.addLayout(body_layout)

        # Select first tab by default
        self.sidebar.setCurrentRow(0)

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        if index == 5:
            self.tab_settings.refresh_whitelist()
        elif index == 2:
            if hasattr(self.tab_packages, "_re_evaluate_protections"):
                self.tab_packages._re_evaluate_protections()
                self.tab_packages._populate_table()
        if not self.auto_scan_on_nav:
            return
        # Auto-trigger refresh for specific tabs when switched
        if index == 0:
            if not self.tab_scanner.scanned_items:
                self.tab_scanner.start_scan()
        elif index == 1 and not self.tab_cache.categories:
            self.tab_cache.scan_caches()
        elif index == 2 and not self.tab_packages.suggestions:
            self.tab_packages.start_package_scan()
        elif index == 3 and not self.tab_restore.backups:
            self.tab_restore.load_backups()

    def _on_scanner_stats_changed(self):
        orphans = [i for i in self.tab_scanner.scanned_items if i.status == "CONFIRMED_ORPHAN"]
        total_b = sum(i.size_bytes for i in orphans)
        size_mb = total_b / (1024 * 1024)
        self.lbl_reclaimable.setText(f"Reclaimable: {len(orphans)} orphans ({size_mb:.1f} MB)")

    def _relaunch_as_root(self):
        """Relaunch ConfClean FC as root via PolicyKit (pkexec)."""
        if hasattr(self, "tab_settings") and hasattr(self.tab_settings, "_relaunch_as_root"):
            self.tab_settings._relaunch_as_root()


def run_gui(ready_signal: bool = False):
    """Starts the PyQt6 GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("confclean-fc")
    app.setApplicationDisplayName("ConfClean FC")
    app.setDesktopFileName("confclean-fc")
    app.setOrganizationName("io.github.confclean_fc")
    app.setOrganizationDomain("builddesigncreate.com")
    app.setStyleSheet(ADWAITA_DARK_STYLE)

    icon_candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.svg"),
        "/usr/share/confclean-fc/assets/icon.svg",
        "/usr/share/icons/hicolor/scalable/apps/confclean-fc.svg",
        "/usr/share/icons/hicolor/256x256/apps/confclean-fc.png",
    ]
    for icon_path in icon_candidates:
        if os.path.isfile(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    window = MainWindow()
    window.show()

    if ready_signal:
        # Signal readiness to parent process waiting on pipe
        try:
            print("CONFCLEAN_ELEVATED_READY", flush=True)
            # Redirect stdout/stderr to devnull so subsequent operations aren't bound to closed pipe
            devnull = open(os.devnull, "w")
            os.dup2(devnull.fileno(), sys.stdout.fileno())
            os.dup2(devnull.fileno(), sys.stderr.fileno())
        except Exception:
            pass

    sys.exit(app.exec())

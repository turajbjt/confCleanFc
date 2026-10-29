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
from confclean.gui.styles import ADWAITA_DARK_STYLE
from confclean.gui.tab_app_reset import AppResetTab
from confclean.gui.tab_cache import CacheTab
from confclean.gui.tab_logs import LogsTab
from confclean.gui.tab_packages import PackageTab
from confclean.gui.tab_restore import RestoreTab
from confclean.gui.tab_scanner import ScannerTab
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
        auto_scan_on_nav: bool = True,
    ):
        super().__init__()
        self.setWindowTitle("ConfClean FC - Fedora & RPM System Cleaner")
        self.resize(1150, 720)
        self.setMinimumSize(900, 580)
        self.auto_scan_on_nav = auto_scan_on_nav

        # Set window icon
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.svg")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Initialize core engines
        self.logger = get_logger()
        self.safety = safety or SafetyEngine()
        self.detector = SystemDetector(refresh_on_init=False) if (scanner or app_resetter) else SystemDetector()
        self.backup_mgr = backup_mgr or BackupManager()
        self.restore_mgr = restore_mgr or RestoreManager()
        self.cleaner = cleaner or SafeCleaner(safety=self.safety, backup_mgr=self.backup_mgr)
        self.scanner = scanner or ConfigScanner(detector=self.detector, safety=self.safety)
        self.cache_cleaner = cache_cleaner or CacheCleaner(safety=self.safety)
        self.pkg_mgr = pkg_mgr or PackageManager()
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
        h_layout.setContentsMargins(18, 12, 18, 12)

        title_lbl = QLabel("ConfClean FC")
        title_lbl.setObjectName("app_title")
        h_layout.addWidget(title_lbl)

        version_badge = QLabel("v1.0.0 (Fedora)")
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
            ("🔍  Orphan Configs", "scanner"),
            ("🧹  Cache & Junk", "cache"),
            ("📦  Package Manager", "packages"),
            ("🔄  App Reset", "reset"),
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

        # 1. Scanner Tab
        self.tab_scanner = ScannerTab(self.scanner, self.cleaner, self.safety)
        self.tab_scanner.status_changed.connect(self._on_scanner_stats_changed)
        self.stack.addWidget(self.tab_scanner)

        # 2. Cache Tab
        self.tab_cache = CacheTab(self.cache_cleaner)
        self.stack.addWidget(self.tab_cache)

        # 3. Package Tab
        self.tab_packages = PackageTab(self.pkg_mgr)
        self.stack.addWidget(self.tab_packages)

        # 4. App Reset Tab
        self.tab_reset = AppResetTab(self.app_resetter)
        self.stack.addWidget(self.tab_reset)

        # 5. Restore Tab
        self.tab_restore = RestoreTab(self.backup_mgr, self.restore_mgr)
        self.stack.addWidget(self.tab_restore)

        # 6. Logs Tab
        self.tab_logs = LogsTab(self.logger)
        self.stack.addWidget(self.tab_logs)

        # 7. Settings Tab
        self.tab_settings = SettingsTab(self.safety)
        self.stack.addWidget(self.tab_settings)

        body_layout.addWidget(self.stack, stretch=1)
        main_layout.addLayout(body_layout)

        # Select first tab by default
        self.sidebar.setCurrentRow(0)

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        if not self.auto_scan_on_nav:
            return
        # Auto-trigger refresh for specific tabs when switched
        if index == 0 and not self.tab_scanner.scanned_items:
            self.tab_scanner.start_scan()
        elif index == 1 and not self.tab_cache.categories:
            self.tab_cache.scan_caches()
        elif index == 3 and not self.tab_reset.profiles:
            self.tab_reset.load_profiles()
        elif index == 4:
            self.tab_restore.load_backups()

    def _on_scanner_stats_changed(self):
        orphans = [i for i in self.tab_scanner.scanned_items if i.status == "CONFIRMED_ORPHAN"]
        total_b = sum(i.size_bytes for i in orphans)
        size_mb = total_b / (1024 * 1024)
        self.lbl_reclaimable.setText(f"Reclaimable: {len(orphans)} orphans ({size_mb:.1f} MB)")


def run_gui():
    """Starts the PyQt6 GUI application."""
    app = QApplication(sys.argv)
    app.setStyleSheet(ADWAITA_DARK_STYLE)

    window = MainWindow()
    window.show()

    # Trigger scan upon initial load
    window.tab_scanner.start_scan()

    sys.exit(app.exec())

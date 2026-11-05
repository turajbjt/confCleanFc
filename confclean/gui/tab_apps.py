"""
Unified Application Configurations & Reset Tab for ConfClean FC.
Combines Orphan Configuration Scanning (Uninstalled Apps) and
Factory Reset (Installed Apps) into a single cohesive interface.
"""

from typing import Optional
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from confclean.core.app_resetter import AppResetter
from confclean.core.cleaner import SafeCleaner
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ConfigScanner
from confclean.gui.tab_app_reset import AppResetTab
from confclean.gui.tab_scanner import ScannerTab


class AppConfigsTab(QWidget):
    """
    Unified Application Configs view containing:
      1. Leftover Configs (Uninstalled Apps)
      2. Factory Reset (Installed Apps)
    """

    status_changed = pyqtSignal()

    def __init__(
        self,
        scanner: ConfigScanner,
        cleaner: SafeCleaner,
        safety: SafetyEngine,
        app_resetter: AppResetter,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.scanner = scanner
        self.cleaner = cleaner
        self.safety = safety
        self.app_resetter = app_resetter

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Tab widget for switching between Leftovers and Factory Reset
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # 1. Leftover Configs (Uninstalled Apps)
        self.tab_scanner = ScannerTab(self.scanner, self.cleaner, self.safety)
        self.tab_scanner.status_changed.connect(self.status_changed.emit)
        self.tabs.addTab(self.tab_scanner, "🔍  Leftover Configs (Uninstalled Apps)")

        # 2. Factory Reset (Installed Apps)
        self.tab_reset = AppResetTab(self.app_resetter)
        self.tabs.addTab(self.tab_reset, "🔄  Factory Reset (Installed Apps)")

        self.tabs.currentChanged.connect(self._on_subtab_changed)
        layout.addWidget(self.tabs)

    def _on_subtab_changed(self, index: int):
        if index == 1 and not self.tab_reset.profiles:
            self.tab_reset.load_profiles()

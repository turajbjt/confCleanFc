"""
Modern Fedora Adwaita stylesheet for ConfClean FC.
Provides clean dark/light themes inspired by GNOME 45+ Adwaita design language.
"""

ADWAITA_DARK_STYLE = """
/* ConfClean FC Modern Dark Theme */

QWidget {
    background-color: #242424;
    color: #f6f8fa;
    font-family: Cantarell, "Segoe UI", Roboto, Ubuntu, sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #1e1e1e;
}

/* Sidebar / Navigation */
QListWidget#nav_sidebar {
    background-color: #1e1e1e;
    border: none;
    border-right: 1px solid #323232;
    padding-top: 8px;
    font-size: 14px;
    outline: none;
}

QListWidget#nav_sidebar::item {
    padding: 12px 16px;
    border-radius: 8px;
    margin: 3px 8px;
    color: #c0c0c0;
}

QListWidget#nav_sidebar::item:hover {
    background-color: #2d2d2d;
    color: #ffffff;
}

QListWidget#nav_sidebar::item:selected {
    background-color: #3584e4;
    color: #ffffff;
    font-weight: bold;
}

/* Header & Cards */
QFrame.card {
    background-color: #2d2d2d;
    border-radius: 10px;
    border: 1px solid #383838;
    padding: 12px;
}

QFrame#header_bar {
    background-color: #2a2a2a;
    border-bottom: 1px solid #383838;
    padding: 10px 16px;
}

QLabel#app_title {
    font-size: 18px;
    font-weight: bold;
    color: #ffffff;
}

QLabel#pill_badge {
    background-color: #383838;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 12px;
    color: #99c1f1;
}

QLabel#pill_root {
    background-color: #e01b24;
    color: #ffffff;
    font-weight: bold;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 12px;
}

/* Buttons */
QPushButton {
    background-color: #383838;
    color: #ffffff;
    border: 1px solid #484848;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #444444;
    border-color: #555555;
}

QPushButton:pressed {
    background-color: #2a2a2a;
}

QPushButton:disabled {
    background-color: #2a2a2a;
    color: #666666;
    border-color: #333333;
}

QPushButton.primary {
    background-color: #3584e4;
    border-color: #1c71d8;
    color: #ffffff;
    font-weight: bold;
}

QPushButton.primary:hover {
    background-color: #1c71d8;
}

QPushButton.destructive {
    background-color: #e01b24;
    border-color: #c01c28;
    color: #ffffff;
    font-weight: bold;
}

QPushButton.destructive:hover {
    background-color: #c01c28;
}

/* Tree & Tables */
QTreeWidget, QTableWidget {
    background-color: #242424;
    border: 1px solid #383838;
    border-radius: 8px;
    alternate-background-color: #282828;
    outline: none;
    gridline-color: #333333;
}

QTreeWidget::item, QTableWidget::item {
    padding: 6px 4px;
    border-bottom: 1px solid #2d2d2d;
}

QTreeWidget::item:hover, QTableWidget::item:hover {
    background-color: #2e3b4e;
}

QTreeWidget::item:selected, QTableWidget::item:selected {
    background-color: #1b497c;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #1e1e1e;
    color: #a0a0a0;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #3584e4;
    font-weight: bold;
    font-size: 12px;
}

/* Inputs & Search */
QLineEdit {
    background-color: #2e2e2e;
    border: 1px solid #444444;
    border-radius: 6px;
    padding: 6px 12px;
    color: #ffffff;
    font-size: 13px;
}

QLineEdit:focus {
    border: 1px solid #3584e4;
}

QComboBox {
    background-color: #2e2e2e;
    border: 1px solid #444444;
    border-radius: 6px;
    padding: 5px 12px;
    color: #ffffff;
}

QComboBox::drop-down {
    border: none;
}

QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    border: 1px solid #444444;
    selection-background-color: #3584e4;
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
    color: #f6f8fa;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #555555;
    background-color: #2e2e2e;
}

QCheckBox::indicator:checked {
    background-color: #3584e4;
    border-color: #3584e4;
}

/* Progress Bar */
QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #383838;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    height: 16px;
}

QProgressBar::chunk {
    background-color: #3584e4;
    border-radius: 5px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #1e1e1e;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #444444;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #666666;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Status Badges */
.badge-confirmed {
    color: #ff7b72;
    font-weight: bold;
}

.badge-probable {
    color: #f5c211;
    font-weight: bold;
}

.badge-active {
    color: #56d364;
    font-weight: bold;
}

.badge-protected {
    color: #79c0ff;
    font-weight: bold;
}
"""

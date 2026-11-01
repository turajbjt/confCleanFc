#!/usr/bin/env bash
# ConfClean FC - Desktop Launcher Uninstaller
set -e

APPS_DIR="${HOME}/.local/share/applications"
ICONS_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"

echo "Uninstalling ConfClean FC per-user desktop launcher..."

rm -f "${APPS_DIR}/confclean.desktop"
rm -f "${APPS_DIR}/confclean-fc.desktop"
rm -f "${ICONS_DIR}/confclean.svg"
rm -f "${ICONS_DIR}/confclean-fc.svg"

update-desktop-database "${APPS_DIR}" 2>/dev/null || true

echo "Desktop entry and application icon removed successfully."

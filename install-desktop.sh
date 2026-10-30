#!/usr/bin/env bash
# ConfClean FC - Desktop Launcher Installer
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="${HOME}/.local/share/applications"
ICONS_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"

mkdir -p "${APPS_DIR}"
mkdir -p "${ICONS_DIR}"

# Check for GUI dependency (PyQt6)
if ! python3 -c "import PyQt6" 2>/dev/null; then
    echo "⚠️  Warning: PyQt6 was not found in python3."
    echo "   The graphical user interface requires PyQt6."
    echo "   To install on Fedora / RHEL / CentOS / Rocky:"
    echo "     sudo dnf install python3-pyqt6"
    echo "   Or via pip:"
    echo "     pip install PyQt6"
    echo ""
fi

# Copy icon
cp "${SCRIPT_DIR}/assets/icon.svg" "${ICONS_DIR}/confclean.svg"

# Generate desktop file with absolute path to main.py
cat <<EOF > "${APPS_DIR}/confclean.desktop"
[Desktop Entry]
Name=ConfClean FC
Comment=Safe, comprehensive configuration cleaner for Fedora and RPM Linux distributions
Exec=${SCRIPT_DIR}/main.py
Icon=${ICONS_DIR}/confclean.svg
Terminal=false
Type=Application
Categories=System;Utility;Settings;
StartupNotify=true
Keywords=cleaner;orphans;config;cache;fedora;rpm;backup;restore;bleachbit;fedy;
EOF

chmod +x "${APPS_DIR}/confclean.desktop"
update-desktop-database "${APPS_DIR}" 2>/dev/null || true

echo "ConfClean FC desktop entry installed successfully to ${APPS_DIR}/confclean.desktop!"
echo "You can now launch ConfClean FC from GNOME Application Menu or run: ${SCRIPT_DIR}/main.py"

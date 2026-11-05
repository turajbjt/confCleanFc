Name:           confclean-fc
Version:        1.1.4
Release:        10%{?dist}
Summary:        Fedora & RPM system cleaner and orphan configuration purger

License:        GPL-3.0-or-later
URL:            https://github.com/turajb/confCleanFc
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

Requires:       python3 >= 3.9
Requires:       python3-pyqt6
Recommends:     python3-rpm
Recommends:     flatpak
Recommends:     policycoreutils

# Helper overrides for building in standalone environments
%define dist %{nil}
%define __os_install_post %{nil}
%define __arch_install_post %{nil}
%define __check_files %{nil}
%define _unpackaged_files_terminate_build 0

%description
ConfClean FC is a safety-first graphical system cleaner and configuration
purger built specifically for Fedora Linux and compatible RPM-based distributions
(Rocky Linux, AlmaLinux, CentOS Stream, and RHEL).

BETA NOTICE: This application is currently in BETA. It is provided "as is"
without warranty of any kind. Use at your own risk. Always verify items during
dry run mode before proceeding with deletion.

Features include:
- Deep scanning for orphaned configurations, broken .desktop launchers, and .rpmsave / .rpmnew files
- Built-in unified diff viewer for inspecting .rpmnew and .rpmsave configuration changes
- Automatic pre-deletion compressed .tar.gz backups with JSON manifests
- Built-in interactive selective and full restore tool
- Cache and junk purger (thumbnails, caches, DNF, journalctl)
- Safe kernel retention, unneeded package optimizer, and Flatpak / Snap runtime pruner
- Application factory reset tool with automatic pre-reset backup
- Real-time audit logging and ironclad desktop safelist
- PyQt6 GUI with modern Adwaita dark theme and headless CLI mode

%prep
%setup -q

%build
# Pure python application, no compilation required

%install
rm -rf %{buildroot}

# Install application files into /usr/share/confclean-fc
mkdir -p %{buildroot}%{_datadir}/%{name}
cp -r confclean %{buildroot}%{_datadir}/%{name}/
cp -r assets %{buildroot}%{_datadir}/%{name}/
install -m 755 main.py %{buildroot}%{_datadir}/%{name}/main.py

# Ensure noarch RPM contains pure Python source without version-locked bytecode
find %{buildroot}%{_datadir}/%{name} -name "*.pyc" -delete 2>/dev/null || :
find %{buildroot}%{_datadir}/%{name} -depth -type d -name "__pycache__" -delete 2>/dev/null || :

# Install CLI wrapper / binaries into /usr/bin
mkdir -p %{buildroot}%{_bindir}
cat << 'EOF' > %{buildroot}%{_bindir}/confclean-fc
#!/bin/bash
if [ "$EUID" -eq 0 ] && [ -n "$DISPLAY" ] && [ -z "$QT_QPA_PLATFORM" ]; then
    export QT_QPA_PLATFORM=xcb
fi
exec /usr/bin/python3 %{_datadir}/confclean-fc/main.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/confclean-fc

# Convenience symlink: confclean -> confclean-fc
ln -sf confclean-fc %{buildroot}%{_bindir}/confclean

# Install polkit policy for privilege escalation
mkdir -p %{buildroot}%{_datadir}/polkit-1/actions
install -m 644 packaging/io.github.confclean_fc.policy %{buildroot}%{_datadir}/polkit-1/actions/io.github.confclean_fc.policy

# Install desktop entry
mkdir -p %{buildroot}%{_datadir}/applications
cat << 'EOF' > %{buildroot}%{_datadir}/applications/confclean-fc.desktop
[Desktop Entry]
Name=ConfClean FC
GenericName=System Cleaner
Comment=Safe, comprehensive configuration cleaner for Fedora and RPM Linux distributions
Exec=/usr/bin/confclean-fc
Icon=confclean-fc
Terminal=false
Type=Application
Categories=System;Utility;Settings;
StartupNotify=true
StartupWMClass=confclean-fc
Keywords=cleaner;orphans;config;cache;fedora;rpm;backup;restore;bleachbit;fedy;
EOF

# Install application icons
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m 644 assets/icon.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/confclean-fc.svg

for size in 16 24 32 48 64 128 256 512 ; do
    if [ -f "assets/icons/${size}x${size}/confclean-fc.png" ]; then
        mkdir -p %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps
        install -m 644 "assets/icons/${size}x${size}/confclean-fc.png" %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/confclean-fc.png
    fi
done

# Install documentation & licenses
mkdir -p %{buildroot}%{_docdir}/%{name}
cp -r docs %{buildroot}%{_docdir}/%{name}/
install -m 644 README.md %{buildroot}%{_docdir}/%{name}/
install -m 644 CONTRIBUTING.md %{buildroot}%{_docdir}/%{name}/

mkdir -p %{buildroot}%{_licensedir}/%{name}
install -m 644 LICENSE %{buildroot}%{_licensedir}/%{name}/

%post
/usr/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
/usr/bin/update-desktop-database &>/dev/null || :
/usr/bin/python3 -m compileall -q %{_datadir}/%{name} &>/dev/null || :

%postun
if [ $1 -eq 0 ] ; then
    find %{_datadir}/%{name} -name "*.pyc" -delete 2>/dev/null || :
    find %{_datadir}/%{name} -depth -type d -name "__pycache__" -delete 2>/dev/null || :
    /usr/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
    /usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
    /usr/bin/update-desktop-database &>/dev/null || :
fi

%posttrans
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%files
%license LICENSE
%doc README.md CONTRIBUTING.md docs/
%{_bindir}/confclean-fc
%{_bindir}/confclean
%{_datadir}/%{name}
%{_datadir}/applications/confclean-fc.desktop
%{_datadir}/icons/hicolor/*/apps/confclean-fc.*
%{_datadir}/polkit-1/actions/io.github.confclean_fc.policy

%changelog
* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-10
- Set desktopFileName and applicationName to confclean-fc for GNOME Wayland app_id icon mapping
- Add StartupWMClass=confclean-fc to desktop launcher
- Install standard raster icon sizes (16x16 to 512x512) and update icon cache in %post

* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-9
- Run SELinux schedule and cancel operations asynchronously in background QThread to keep GUI responsive
- Fix window manager focus-stealing and authentication dialog interruption in GNOME/Wayland
- Register fixfiles action in Polkit policy configuration
- Increase pkexec authorization timeout to 180s and handle cancellation gracefully

* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-8
- Expand Factory Reset library to 30 desktop applications (Slack, Nextcloud, Cura, Android Studio, GitKraken, Picard, etc.)
- Add detector mapping aliases for newly supported desktop applications

* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-7
- Auto-refresh custom safelist UI on tab navigation and showEvent
- Expose load_user_whitelist() on SafelistManager and refresh_whitelist() on SettingsTab

* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-6
- Safely handle unreadable files (permission denied) during pre-deletion backup without aborting cleanup
- Add automatic permission unlock for read-only directories and files during rmtree
- Inform user with guidance to elevate via pkexec if root-owned files cannot be removed

* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-5
- Fix AppConfigsTab.status_changed signal signature (0 arguments) to prevent crash on startup scan

* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-4
- Make noarch RPM purely Python source and eliminate conflicting %pre scriptlet
- Compile bytecode on target system in %post to match installed Python version
- Eliminate "remove failed: No such file or directory" errors during dnf upgrade

* Wed Nov 04 2026 James Turansky <turajb@gmail.com> - 1.1.4-3
- Consolidate CLI and GUI features into unified, non-redundant offerings
- Unify Application Configs view (Uninstalled Leftovers & Factory Reset) into single 6-tab navigation
- Move SELinux on-boot relabeling and direct DNF package cache cleaning into Packages & System tab
- Unify CLI package operations (--packages [--retired-only] [--clean-cache]) and scan operations (--scan [--symlinks-only])
- Thoroughly purge DNF/RPM package caches and foreign systemd journal directories

* Mon Nov 02 2026 James Turansky <turajb@gmail.com> - 1.1.4-2
- Package compiled Python bytecode and purge stale unmanaged pycache across upgrades

* Sun Nov 01 2026 James Turansky <turajb@gmail.com> - 1.1.4-1
- Increase application logo size to 42x42 (75% larger) in header

* Sun Nov 01 2026 James Turansky <turajb@gmail.com> - 1.1.3-1
- Add application logo icon to header left of ConfClean FC title

* Sun Nov 01 2026 James Turansky <turajb@gmail.com> - 1.1.2-1
- Add copyright notice for BuildDesignCreate.com under safety rules

* Sun Nov 01 2026 James Turansky <turajb@gmail.com> - 1.1.1-1
- Fix pkexec root relaunch with Wayland/X11 display preservation
- Add Polkit GUI execution policy action
- Auto-size table name columns to width of longest entry
- Auto-run package analysis when navigating to empty Package Manager
- Add progress bar and confirmation for package removal
- Add uninstallation guide and desktop uninstaller script

* Sun Nov 01 2026 James Turansky <turajb@plugnpay.com> - 1.1.0-1
- Add broken .desktop and autostart entry detection and safe cleaning
- Add Flatpak unused runtime and Snap disabled revision pruning
- Add built-in unified diff viewer for .rpmnew and .rpmsave files
- Optimize privilege escalation to a single prompt per batch operation

* Fri Oct 30 2026 James Turansky <turajb@plugnpay.com> - 1.0.0-1
- Initial RPM release of ConfClean FC for Fedora and RPM distributions

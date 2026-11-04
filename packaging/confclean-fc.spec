Name:           confclean-fc
Version:        1.1.4
Release:        2%{?dist}
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
%define __os_install_post %{nil}
%define __arch_install_post %{nil}
%define __check_files %(test -x /usr/lib/rpm/check-files && echo /usr/lib/rpm/check-files || (test -x /tmp/rpmbuild_tool/usr/lib/rpm/check-files && echo /tmp/rpmbuild_tool/usr/lib/rpm/check-files || echo true))
%define __rpmuncompress %(test -x /usr/lib/rpm/rpmuncompress && echo /usr/lib/rpm/rpmuncompress || (test -x /tmp/rpmbuild_tool/usr/lib/rpm/rpmuncompress && echo /tmp/rpmbuild_tool/usr/lib/rpm/rpmuncompress || echo "/bin/tar -x -f"))

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

# Pre-compile Python bytecode so the RPM package owns and manages all .pyc files
/usr/bin/python3 -m compileall -q -f -s %{buildroot} -p / %{buildroot}%{_datadir}/%{name}

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
Keywords=cleaner;orphans;config;cache;fedora;rpm;backup;restore;bleachbit;fedy;
EOF

# Install application icons
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m 644 assets/icon.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/confclean-fc.svg

# Install documentation & licenses
mkdir -p %{buildroot}%{_docdir}/%{name}
cp -r docs %{buildroot}%{_docdir}/%{name}/
install -m 644 README.md %{buildroot}%{_docdir}/%{name}/
install -m 644 CONTRIBUTING.md %{buildroot}%{_docdir}/%{name}/

mkdir -p %{buildroot}%{_licensedir}/%{name}
install -m 644 LICENSE %{buildroot}%{_licensedir}/%{name}/

%pre
# Purge any stale unmanaged runtime __pycache__ from prior installs
rm -rf %{_datadir}/%{name}/confclean/**/__pycache__ %{_datadir}/%{name}/confclean/__pycache__ 2>/dev/null || :

%post
/usr/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
/usr/bin/update-desktop-database &>/dev/null || :
/usr/bin/python3 -m compileall -q -f %{_datadir}/%{name} &>/dev/null || :

%postun
if [ $1 -eq 0 ] ; then
    rm -rf %{_datadir}/%{name}/confclean/**/__pycache__ %{_datadir}/%{name}/confclean/__pycache__ 2>/dev/null || :
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
%{_datadir}/icons/hicolor/scalable/apps/confclean-fc.svg
%{_datadir}/polkit-1/actions/io.github.confclean_fc.policy

%changelog
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

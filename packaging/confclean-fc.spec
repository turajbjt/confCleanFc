Name:           confclean-fc
Version:        1.0.0
Release:        2%{?dist}
Summary:        Fedora & RPM system cleaner and orphan configuration purger

License:        GPL-3.0-or-later
URL:            https://github.com/turajb/confCleanFc
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

Requires:       python3 >= 3.9
Requires:       python3-pyqt6
Requires:       python3-rpm
Requires:       python3-psutil
Recommends:     flatpak

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

# Install CLI wrapper / binaries into /usr/bin
mkdir -p %{buildroot}%{_bindir}
cat << 'EOF' > %{buildroot}%{_bindir}/confclean-fc
#!/bin/bash
exec /usr/bin/python3 %{_datadir}/confclean-fc/main.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/confclean-fc

# Convenience symlink: confclean -> confclean-fc
ln -sf confclean-fc %{buildroot}%{_bindir}/confclean

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

%post
/usr/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
/usr/bin/update-desktop-database &>/dev/null || :

%postun
if [ $1 -eq 0 ] ; then
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

%changelog
* Sun Nov 01 2026 James Turansky <turajb@plugnpay.com> - 1.0.0-2
- Add broken .desktop and autostart entry detection and safe cleaning
- Add Flatpak unused runtime and Snap disabled revision pruning
- Add built-in unified diff viewer for .rpmnew and .rpmsave files

* Fri Oct 30 2026 James Turansky <turajb@plugnpay.com> - 1.0.0-1
- Initial RPM release of ConfClean FC for Fedora and RPM distributions

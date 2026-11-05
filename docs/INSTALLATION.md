# ConfClean FC Installation & Uninstallation Guide 📥🗑️

This guide provides instructions for installing, running, updating, and completely uninstalling **ConfClean FC** across supported Fedora, RHEL, CentOS Stream, AlmaLinux, and Rocky Linux environments.

---

## 📥 Installation Methods

### Method 1: Install via RPM Package (Recommended)

Installing the pre-built `.rpm` package provides full system integration: it installs `/usr/bin/confclean` and `/usr/bin/confclean-fc` into system PATH, configures system desktop launchers, and installs scalable high-resolution application icons for GNOME, KDE, and XFCE.

You can install the pre-built unified `.rpm` package directly from this repository (compatible across Fedora 40+, CentOS Stream, Rocky Linux, and RHEL):

```bash
# Using DNF with automatic dependency resolution:
sudo dnf install ./confclean-fc-1.1.4-12.noarch.rpm

# Or directly with RPM:
sudo rpm -ivh ./confclean-fc-1.1.4-12.noarch.rpm
```

#### Rebuilding or Inspecting from Source RPM (SRPM):
The repository also provides the official source RPM (`confclean-fc-1.1.4-12.src.rpm`), allowing you to inspect the spec file, audit source tarballs, or rebuild binary packages in isolated mock/chroot environments:

```bash
# Rebuild binary RPM from source package:
rpmbuild --rebuild ./confclean-fc-1.1.4-12.src.rpm

# Or inspect the spec file and source archive:
rpm -ivh ./confclean-fc-1.1.4-12.src.rpm
```

Verify package integrity using the included SHA256 checksums:
```bash
sha256sum -c SHA256SUMS
```

Once installed, launch ConfClean FC from your application grid or from any terminal:
```bash
confclean-fc
# or simply:
confclean
```

To upgrade an existing RPM package installation in the future:
```bash
sudo dnf upgrade ./confclean-fc-1.1.4-12.noarch.rpm
```

---

### Method 2: Run Directly from Source (No Installation Needed)

ConfClean FC can be executed directly from the cloned repository without installing anything into system directories:

1. **Install Prerequisites**:
   ```bash
   sudo dnf install python3-pyqt6
   ```

2. **Run the Application**:
   ```bash
   ./main.py
   # or:
   python3 main.py
   ```

3. **(Optional) Add to Application Menu**:
   If you run from source but want ConfClean FC to appear in your desktop application grid, install the per-user desktop launcher:
   ```bash
   ./install-desktop.sh
   ```

---

## 🗑️ Uninstallation Methods

### Method 1: Uninstall RPM Package

To remove ConfClean FC if it was installed via RPM:

```bash
# Using DNF:
sudo dnf remove confclean-fc

# Or using RPM:
sudo rpm -e confclean-fc
```

This cleanly removes the application binaries, system `.desktop` file, icons, documentation, and library modules installed in `/usr/share/confclean-fc`.

---

### Method 2: Uninstall Per-User Desktop Launcher

If you installed the per-user launcher using `./install-desktop.sh`:

Run the included uninstaller script:
```bash
./uninstall-desktop.sh
```

Or remove the files manually:
```bash
rm -f ~/.local/share/applications/confclean.desktop
rm -f ~/.local/share/applications/confclean-fc.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/confclean.svg
rm -f ~/.local/share/icons/hicolor/scalable/apps/confclean-fc.svg
update-desktop-database ~/.local/share/applications
```

---

### Method 3: Clean ConfClean FC Application Data & Backups

When you use ConfClean FC, safety backup archives (`.tar.gz`), audit logs, and custom whitelist rules are stored in standard user XDG directories. Removing the RPM package or desktop launcher does not touch your safety backups so your data remains protected.

If you wish to **completely purge** all ConfClean FC data from your home directory:

```bash
# 1. Remove pre-deletion safety backup archives and audit logs:
rm -rf ~/.local/share/confclean-fc

# 2. Remove user custom whitelist settings:
rm -rf ~/.config/confclean-fc
```

> [!WARNING]
> Purging `~/.local/share/confclean-fc` permanently deletes any `.tar.gz` safety archives created before previous clean operations. Ensure you do not need to restore any previously cleaned items before running this command.

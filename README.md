# ConfClean FC 🛡️🧹
### Fedora, Rocky Linux & CentOS System Cleaner, Orphan Purger & Configuration Manager

[![Linux](https://img.shields.io/badge/Platform-Fedora%20%7C%20Rocky%20%7C%20CentOS%20%7C%20RHEL-blue?logo=fedora)](https://getfedora.org)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://python.org)
[![GUI](https://img.shields.io/badge/GUI-PyQt6%20Adwaita-3584e4?logo=qt)](https://pypi.org/project/PyQt6/)
[![RPM Package](https://img.shields.io/badge/RPM-Universal%20noarch-red?logo=redhat)](packaging/)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Safety](https://img.shields.io/badge/Safety-Pre--Clean%20Backups%20%26%20Ironclad%20Safelist-26a269)](docs/SAFETY.md)
[![Tests](https://img.shields.io/badge/Tests-140%2F140%20Passing-brightgreen)](tests/)

**ConfClean FC** is a powerful, safety-first system cleaner, orphan configuration purger, and maintenance suite built specifically for **Fedora Linux** (Fedora 40, 41, 42, 43, 44, 45+) and compatible **RPM-based distributions** (Rocky Linux, CentOS Stream, RHEL, and AlmaLinux).

Inspired by the philosophy of tools like OrphyCleaner, ConfClean FC goes substantially further: it provides an end-to-end configuration cleaner with **automatic pre-deletion compressed backup archives**, a **built-in interactive restore tool** (selective or whole), **cache and junk cleanup**, **DNF/RPM package suggestions** (unneeded dependencies and safe old kernel cleanup), **application factory reset**, and an **ironclad system safelist**. Featuring both a modern **GNOME 45+ Adwaita Dark GUI** and a full-featured **headless CLI** for remote administration and scripts.

---

## 📚 Documentation Quick Links

- [📥 Installation & Setup Guide](docs/INSTALLATION.md)
- [💻 Command-Line Interface (CLI) Reference](docs/CLI_REFERENCE.md)
- [🏗️ Architecture & Design Specification](docs/ARCHITECTURE.md)
- [🛡️ Safety Engine & Protection Principles](docs/SAFETY.md)
- [🤝 Contributing Guidelines](CONTRIBUTING.md)

---

> [!CAUTION]
> ## ⚠️ BETA SOFTWARE — USE AT YOUR OWN RISK
>
> **ConfClean FC is currently in active BETA.**
>
> While ConfClean FC is architected with multiple conservative safety layers (including an ironclad system safelist, dry-run simulation enabled by default, and automatic pre-deletion `.tar.gz` safety archives), any software that inspects, modifies, or deletes configuration files, system caches, and package dependencies carries inherent risk.
>
> * **USE AT YOUR OWN RISK**: This software is provided **"AS IS"**, without warranty of any kind, either express or implied, including but not limited to the implied warranties of merchantability, fitness for a particular purpose, and non-infringement.
> * **NO LIABILITY / DISCLAIMER**: In no event shall the authors, copyright holders, maintainers, or contributors be held liable for any direct, indirect, incidental, special, exemplary, or consequential damages (including, but not limited to, loss of data, system corruption, application misbehavior, downtime, or desktop environment instability) arising in any way out of the use or misuse of this software.
> * **INDEPENDENT BACKUPS RECOMMENDED**: While ConfClean FC automatically creates safety archives prior to any deletion, you should always maintain independent, current backups of your personal files, home directory (`~`), and critical configurations before executing cleanup operations on production machines.
> * **ALWAYS VERIFY CANDIDATES**: Dry run simulation mode is enabled by default across both GUI and CLI. Carefully review the scanned paths and confirmed orphan status before unchecking "Dry Run" or supplying the `--apply` flag.

---

## 🌟 Key Highlights & Comparison

| Feature | ConfClean FC | OrphyCleaner | BleachBit | Fedy |
| :--- | :---: | :---: | :---: | :---: |
| **Fedora & RPM Native (DNF5/DNF4/RPM)** | **Yes (Full)** | No (Arch Linux focused) | Generic | Basic wrapper |
| **Pre-Deletion Backup (.tar.gz + JSON Manifest)** | **Yes (Automatic)** | No | No | No |
| **Interactive Restore Tool (Selective / Full)** | **Yes** | No | No | No |
| **Dry Run Simulation Mode** | **Yes (ON by Default)** | No | Partial | No |
| **Orphan Config Detection (RPM + Flatpak + Desktop)** | **Yes** | Partial | No | No |
| **Broken Desktop & Autostart Cleanup** | **Yes** | No | No | No |
| **Built-in Unified RPM Diff Viewer (.rpmnew/.rpmsave)** | **Yes** | No | No | No |
| **Multi-System Package Pruning (DNF + Flatpak + Snap)** | **Yes (Single Auth)** | No | No | Basic script |
| **Safe Kernel Cleanup (Protects Running & Backup Kernels)** | **Yes** | No | No | Basic script |
| **App Reset to Factory Fresh Defaults** | **Yes (With auto-backup)** | No | No | No |
| **Comprehensive Audit Logging** | **Yes** | Minimal | Basic | No |
| **Dual User / Root Mode (Polkit / pkexec)** | **Yes** | User only | Separate apps | Root only |

---

## 🚀 Quick Start

### 📋 Prerequisites & GUI Dependencies

ConfClean FC requires **Python 3.9+** and **PyQt6** for its graphical interface:

* **Fedora / RHEL / CentOS Stream / Rocky Linux / AlmaLinux (DNF)**:
  ```bash
  sudo dnf install python3-pyqt6
  # Optional accelerator for sub-second RPM metadata queries:
  # sudo dnf install python3-rpm
  ```
* **Ubuntu / Debian (APT)**:
  ```bash
  sudo apt install python3-pyqt6
  ```
* **Arch Linux (Pacman)**:
  ```bash
  sudo pacman -S python-pyqt6
  ```
* **Python Virtual Environments / Pip**:
  ```bash
  pip install -r requirements.txt
  ```

> [!TIP]
> If PyQt6 is not installed on your system, ConfClean FC can still run in headless CLI mode via `--scan`, `--clean`, `--cache`, etc., or will display an informative prompt with the exact command to install PyQt6.

### 1. Install via RPM Package (Recommended)
You can directly install the pre-built unified `.rpm` package included in the repository using `dnf` or `rpm` (compatible across Fedora 40+, CentOS Stream, Rocky Linux, and RHEL):
```bash
# Install binary RPM locally with automatic dependency resolution:
sudo dnf install ./confclean-fc-1.1.4-13.noarch.rpm

# Or with rpm:
sudo rpm -ivh ./confclean-fc-1.1.4-13.noarch.rpm
```

#### Rebuilding or Inspecting from Source RPM (SRPM):
The repository also includes the official source RPM (`confclean-fc-1.1.4-13.src.rpm`), enabling full auditability, reproducible rebuilds, and mock/chroot building:
```bash
# Rebuild binary RPM directly from the source RPM:
rpmbuild --rebuild ./confclean-fc-1.1.4-13.src.rpm

# Or inspect the spec file and source archive:
rpm -ivh ./confclean-fc-1.1.4-13.src.rpm
```

Verify package integrity using the included checksums:
```bash
sha256sum -c SHA256SUMS
```

Once installed, launch ConfClean FC from your application menu or directly in terminal:
```bash
confclean-fc        # or simply: confclean
```

To build both binary and source RPMs at any time:
```bash
./packaging/build-rpm.sh
```

### 2. Run Directly from Source (No Installation Needed)
Kick off the application directly from the repository:
```bash
./main.py
# or
python3 main.py
```

### 3. Optional: Install Per-User Desktop Application Launcher
If running from source rather than RPM:
```bash
./install-desktop.sh
```

### 4. How to Uninstall ConfClean FC
* **If installed via RPM**:
  ```bash
  sudo dnf remove confclean-fc
  # or: sudo rpm -e confclean-fc
  ```
* **If running from source with desktop launcher**:
  ```bash
  ./uninstall-desktop.sh
  ```
* **(Optional) Purge application safety archives and logs**:
  ```bash
  rm -rf ~/.local/share/confclean-fc ~/.config/confclean-fc
  ```
For complete details, see the dedicated 📖 **[Installation & Uninstallation Guide](docs/INSTALLATION.md)**.

### 5. CLI Commands (Headless / Terminal-Driven)
ConfClean FC works seamlessly without a graphical display. **Safety Note:** Deletion operations run in **DRY RUN mode by default** to prevent accidental loss; use `--apply` (or `--no-dry-run`) to commit changes:

```bash
# Scan system for orphaned configs and broken/stale symlinks
./main.py --scan

# Scan only broken and stale symbolic links
./main.py --scan --symlinks-only

# Dry-run simulation of orphan cleanup (default behavior)
./main.py --clean

# Commit actual orphan and broken symlink cleanup with pre-deletion safety backup
./main.py --clean --apply

# Scan all cleanable caches, thumbnails, journals, trash, and temporary data
./main.py --cache

# Clean all system caches (Dry run by default; use --apply to commit purge)
./main.py --cache --clean --apply

# Query DNF for unneeded dependencies, retired packages, and old kernels
./main.py --packages

# Query only retired / repository-orphaned packages
./main.py --packages --retired-only

# View protected system safelist and custom whitelist entries
./main.py --safelist

# Safelist a retired package or custom tool to protect it from removal
./main.py --safelist-add miracle-wm

# Purge DNF and PackageKit download caches directly from package manager
./main.py --packages --clean-cache --apply

# Remove unneeded / retired packages (Dry run by default; use --apply to commit)
./main.py --packages --clean --apply

# Schedule an on-boot SELinux policy and file context fix (sudo fixfiles -B onboot)
./main.py --selinux-fix-boot

# Check SELinux status and next-boot relabeling schedule
./main.py --selinux-status

# View syntax-highlighted unified diff for an RPM upgrade artifact (.rpmnew / .rpmsave)
./main.py --diff /etc/cups/cupsd.conf.rpmnew

# List all past backup archives
./main.py --restore list

# Restore a specific backup archive by ID
./main.py --restore confclean_backup_YYYYMMDD_HHMMSS

# Reset an app to factory defaults (Dry run by default; use --apply to commit reset)
./main.py --reset-app firefox --apply
```

---

## 🛡️ Safety Architecture (First & Foremost)

### 1. Dry Run Enabled by Default
To eliminate accidental deletions, **Dry Run is ON by default** across both GUI and CLI:
* **In the GUI**: The "Dry Run (Simulation)" checkbox is checked whenever opening any cleaning or reset view. Action buttons clearly indicate `🔍 Simulate Clean (Dry Run)`. To commit actual file deletion, simply uncheck the box.
* **In the CLI**: Running `--clean`, `--cache --clean`, or `--reset-app` simulates the operation and outputs exactly what would be cleaned without modifying any files. Actual execution requires passing `--apply` (or `--no-dry-run`).

### 2. Ironclad System Safelist
ConfClean FC will **never** target or delete critical desktop environment or system plumbing components:
* **Desktop Environments**: GNOME Shell, KDE Plasma, XFCE, Cinnamon, MATE, Sway, Hyprland.
* **Core Plumbing**: `dconf`, `systemd`, `pipewire`, `wireplumber`, `pulse`, `dbus`, `polkit`, `gtk-*`, `fontconfig`, `user-dirs.*`, `mimeapps.list`.
* **Security & Auth**: SSH keys (`~/.ssh`), GPG keys (`~/.gnupg`), PKI certificates, keyrings, crypto tokens.
* **Developer Toolchains**: `.git`, `.gitconfig`, `.cargo`, `.rustup`, `.gradle`, `.m2`, `.dotnet`.
* **Shell Environments**: `.bashrc`, `.zshrc`, `.profile`.

### 3. Pre-Deletion Backup Archives
Whenever files or folders are slated for deletion:
1. They are compressed into a `.tar.gz` archive stored at `~/.local/share/confclean-fc/backups/`.
2. A structured `manifest.json` is embedded inside the archive recording original absolute paths, permissions, timestamps, and removal reasons.
3. A companion `.log` file is generated alongside the archive for human-readable auditability.

### 4. Integrated Restore Tool
The **Restore & Backups** tab allows you to:
* Browse all historical backup archives.
* View exact files and folders contained in each archive.
* **Restore Selected Items**: Select specific apps or folders to restore.
* **Restore Entire Archive**: Put everything back in its exact original location.
* Conflict protection: Option to skip or overwrite existing files.

### 5. Safe Kernel & Package Management
* **User Package Safelist**: Any package added to the safelist (via right-click context menu, toolbar button, Settings tab, or `--safelist-add`) is permanently locked as `PROTECTED`. Retired packages (repo extras), unneeded dependencies, old kernels, and Flatpaks/Snaps are shielded from accidental removal.
* **Core Protected Packages**: Base OS packages (`glibc`, `systemd`, `dnf`, `kernel`, `polkit`, `NetworkManager`) are hardcoded in `CORE_PROTECTED_PACKAGES` and locked against removal.
* **Running Kernel Safeguard**: Identifies currently booted running kernel (`uname -r`) and **locks it as protected**.
* **Fallback Kernel Safeguard**: Identifies the latest fallback backup kernel and **locks it as safe keep**.
* **Redundant Old Kernels**: Only older redundant kernels (3rd+ kernel versions, not in safelist) are suggested for removal.
* **Defense-in-Depth Removal Verification**: Safelisted packages are strictly omitted from batch removal commands generated across DNF, Flatpak, and Snap.

---

## 📚 Detailed Documentation

For in-depth technical references and developer guides, consult the dedicated manuals:
* 📥 **[Installation & Uninstallation Guide](docs/INSTALLATION.md)**: Full walkthrough for RPM installation, running from source, desktop shortcuts, and clean uninstallation.
* 🏛️ **[System Architecture & Internals](docs/ARCHITECTURE.md)**: Deep dive into the detection engine, scanning heuristics, thread worker pool, and data flows.
* 💻 **[CLI Reference Manual](docs/CLI_REFERENCE.md)**: Detailed guide to flags, dry-run syntax, headless operation, and cron/script integration.
* 🛡️ **[Safety Specification](docs/SAFETY.md)**: Comprehensive rules on the ironclad safelist, credential protection, and kernel retention.
* 🤝 **[Contributing Guidelines](CONTRIBUTING.md)**: Guide to setting up the development environment, coding standards, and running tests.
* 📜 **[GPLv3 License](LICENSE)**: Full open-source license text.

---

## 📁 Project Structure

```text
confCleanFc/
├── assets/
│   ├── icons/            # Multi-size raster icons (16x16 to 512x512) for Wayland/GNOME
│   └── icon.svg          # Fedora-themed vector icon
├── confclean/
│   ├── core/
│   │   ├── app_resetter.py   # App reset engine with mandatory auto-backups (30 profiles)
│   │   ├── backup_manager.py # Pre-deletion .tar.gz archiving with JSON manifests
│   │   ├── cache_cleaner.py  # User & root cache / junk purger
│   │   ├── cleaner.py        # Safe deletion engine with safelist assertions
│   │   ├── detector.py       # RPM, Flatpak, Binary, Desktop app indexer
│   │   ├── logger.py         # Persistent audit logging and live event bus
│   │   ├── package_manager.py# DNF autoremove & old kernel optimizer
│   │   ├── restore_manager.py# Selective & whole restore engine
│   │   ├── safelist.py       # Built-in system safelist and custom whitelist
│   │   ├── scanner.py        # Deep scanner for user and system configs
│   │   └── selinux_manager.py# SELinux on-boot relabeling and status management
│   ├── gui/
│   │   ├── app.py            # Primary PyQt6 window with 6-tab sidebar navigation
│   │   ├── styles.py         # Modern Fedora Adwaita dark theme stylesheet
│   │   ├── tab_apps.py       # Unified Application Configs view (Leftovers + Factory Reset)
│   │   ├── tab_app_reset.py  # App Reset view component
│   │   ├── tab_cache.py      # Cache & Junk Cleaner view
│   │   ├── tab_logs.py       # Real-time searchable Audit Logs view
│   │   ├── tab_packages.py   # Packages & System Maintenance view (Packages, Cache & SELinux)
│   │   ├── tab_restore.py    # Restore & Backups manager view
│   │   ├── tab_scanner.py    # Orphan Config Scanner view component
│   │   ├── tab_settings.py   # Custom Whitelist & Protection Settings view
│   │   └── workers.py        # Non-blocking QThread background workers (Scan, Clean, SELinux, etc.)
│   └── cli.py                # Command-line interface implementation
├── docs/                     # Detailed architectural and user guides
│   ├── ARCHITECTURE.md       # Technical design and subsystem dataflows
│   ├── CLI_REFERENCE.md      # Headless syntax and examples
│   ├── INSTALLATION.md       # Installation, desktop shortcuts, and uninstallation
│   └── SAFETY.md             # Security and protection guarantees
├── packaging/                # Universal RPM specs, packaging scripts, and Polkit policies
│   ├── build-rpm.sh          # Binary & source RPM build automation script
│   ├── confclean-fc.spec     # Universal RPM packaging spec file
│   ├── io.github.confclean_fc.policy # Polkit authentication policy
│   └── rpmbuild-runner.c     # Standalone C runner using librpm/librpmbuild
├── tests/                    # Automated unit test suite (152 tests)
├── confclean.desktop         # Freedesktop application shortcut
├── install-desktop.sh        # Installer script for GNOME Application Grid
├── uninstall-desktop.sh      # Uninstaller script for desktop shortcuts
├── main.py                   # Main executable entry point
├── requirements.txt          # Python dependencies
├── SHA256SUMS                # Official cryptographic checksums for RPM packages
└── README.md
```

---

## 🔧 Distro Compatibility

* **Fedora 40, 41, 42, 43, 44+** (Workstation, Silverblue, KDE Spin, Kinoite)
* **Rocky Linux 8, 9, 10**
* **CentOS Stream 8, 9, 10**
* **Red Hat Enterprise Linux (RHEL) 8, 9, 10**
* **AlmaLinux**

---

## 🧪 Comprehensive Unit Testing

Run the full automated test suite:
```bash
python3 -m unittest discover -s tests
```

### Test Coverage Highlights (152 Unit Tests):
* **`tests/test_safelist.py`** (8 tests): Core system patterns, root dirs, /etc files, security/credential protection, developer toolchains, package safelist matching and pattern wildcards, uninstalled orphan allowances, custom whitelist JSON persistence, dynamic auto-reloading, and error recovery.
* **`tests/test_detector.py`** (11 tests): SystemDetector processes, exact and component Flatpak matching, Snap application detection, known application mappings (30 curated app aliases), RPM direct and version/flavor suffix matching, binary PATH searches, desktop file parser, distinct fork handling (`cura-lulzbot` vs `cura`).
* **`tests/test_scanner.py`** (14 tests): ScanItem size and date formatting, `get_path_stats` file/dir/symlink/missing, `_analyze_item` (safelist, rpmsave, rpmnew, active, orphan > 14 days, probable <= 14 days), broken `.desktop` and autostart entry detection, broken symlink detection, `.rpmnew` unified diff engine (`get_rpm_diff`), `scan_all` orchestration and progress callback.
* **`tests/test_logger.py`** (7 tests): AuditLogger singleton behavior, file logging, listener dispatch, faulty listener resilience, `audit_event` formatting (B, KB, MB), `get_recent_logs` filtering and limits, 2000-record buffer overflow rotation.
* **`tests/test_backup_restore.py`** (9 tests): BackupMetadata formatting, `create_backup` empty error and disk space check, full backup creation with `.tar.gz` and `manifest.json` and companion `.log`, `list_backups`, selective restore, destination override, overwrite vs skip conflict handling, symlink restoration, and backup deletion.
* **`tests/test_cleaner.py`** (8 tests): CleanResult formatting, empty items, safelist enforcement, dry-run simulation, dry-run by default verification, backup failure aborts deletion, actual clean of files and dirs with progress reporting and audit logging.
* **`tests/test_clean_safety.py`** (4 tests): Comprehensive safety checks ensuring system files, user home roots, and critical system paths are never targeted for deletion.
* **`tests/test_cache_cleaner.py`** (9 tests): CacheCategory formatting, `scan_categories` on user and system data, `_evaluate_old_tmp_category` age filter, root requirement enforcement, directory emptying while preserving parent folders, DNF clean and journalctl vacuum commands, dry-run by default verification.
* **`tests/test_package_manager.py`** (17 tests): PackageSuggestion NEVRA and size formatting, `removal_spec` for exact version targeting, `get_removal_command` root vs user (pkexec) and sudo fallback, `_get_old_kernels` sorting and running kernel protection, user-safelisted retired package protection, user-safelisted unneeded dependency protection, user-safelisted old kernel protection, defense-in-depth removal command assertion, `_get_unneeded_packages`, `_get_duplicate_packages`, Flatpak unused runtimes query & graceful degradation when missing, Snap disabled revisions query & graceful degradation when missing, single-authentication privilege escalation batching, progress reporting.
* **`tests/test_app_resetter.py`** (6 tests): AppResetProfile formatting, `discover_reset_profiles` for 30 known apps and Flatpaks, safelist refusal, factory reset with pre-reset backup and path wiping, dry-run by default verification, empty path validation.
* **`tests/test_cli.py`** (23 tests): `format_table` ASCII alignment, `--scan` output, `--dry-run` simulation, default dry-run on `--clean`, `--clean` with `--force`, user cancellation on prompt, `--cache` listing, cache clean dry-run by default, cache clean apply, `--packages` listing with DNF/Flatpak/Snap and batched removal commands, `--safelist` listing, `--safelist-add`, `--safelist-remove`, safelist package protection verification, `--restore list`, `--reset-app` dry run & apply, `--diff` unified diff viewer, `--selinux-status`, `--selinux-fix-boot`, symlinks scan and clean.
* **`tests/test_gui_headless.py`** (25 tests): All 10 asynchronous workers (`ScanWorker`, `CleanWorker`, `PackageScanWorker`, `CacheCleanWorker`, `AppResetWorker`, `RestoreWorker`, `BackupListWorker`, `ArchiveInspectWorker`, `PackageRemovalWorker`, `SELinuxWorker`), offscreen testing of `ScannerTab` (including broken `.desktop` entry display and double-click diff viewer invocation), `RpmDiffDialog` (colorization and clipboard copy), `PackageTab` (Flatpak/Snap category badges, batched package removal, SELinux onboot scheduling, right-click context menu safelisting, batch Safelist Selected button, dynamic protection re-evaluation), `CacheTab`, `AppResetTab`, `RestoreTab`, `LogsTab`, `SettingsTab` (elevation logic and custom whitelist live auto-refresh), `MainWindow` multi-tab navigation, and verification that Dry Run is checked by default across all tabs.
* **`tests/test_selinux.py`** (8 tests): SELinux status detection, scheduling on-boot fix via `fixfiles -B onboot` using root/pkexec/sudo, on-boot cancellation removing `/.autorelabel`, command argument construction, and error resilience.
* **`tests/test_version.py`** (3 tests): Version synchronization across `confclean/__init__.py`, `pyproject.toml`, and RPM packaging spec (`confclean-fc.spec`).

---

## ⚖️ License & Copyright

- **Copyright**: © [BuildDesignCreate.com](https://builddesigncreate.com)
- **License**: [GNU General Public License v3.0 or later (GPL-3.0-or-later)](LICENSE)
- **Sister Application**: [ConfTune FC](https://github.com/turajbjt/confTuneFc)

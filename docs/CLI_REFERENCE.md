# ConfClean FC CLI Reference Manual 💻📖

`main.py` provides a rich, headless command-line interface for terminal users, system administrators, scripts, and remote SSH sessions.

---

> [!WARNING]
> ### ⚠️ BETA SOFTWARE WARNING & DISCLAIMER
> ConfClean FC is **BETA** software. Executing commands with `--apply` or `--force` will commit real deletions and changes on disk. **Use entirely at your own risk.** Always run operations in default simulation mode first to inspect the dry-run output, and verify that you maintain independent backups before applying changes.

---

## 📋 General Syntax

```bash
python3 main.py [OPTIONS]
# or
./main.py [OPTIONS]
```

When run without flags in a graphical desktop session (Wayland or X11), ConfClean FC automatically launches the PyQt6 GUI. When run on a headless system or when CLI flags are specified, it executes in terminal mode.

---

## ⚙️ Options & Arguments

### Core Execution Flags
| Flag | Description |
| :--- | :--- |
| `--gui` | Force launch the PyQt6 graphical user interface. |
| `--scan` | Scan for orphaned configurations and print a formatted ASCII table of findings. |
| `--clean` | Clean detected orphan configurations (**Dry run by default** unless `--apply` is passed). |
| `--dry-run` | Explicitly simulate actions without deleting files. (ENABLED by default for destructive operations). |
| `--apply`, `--no-dry-run` | Execute actual deletion or reset on the filesystem (disables dry run). |
| `--no-backup` | Skip creating a pre-deletion `.tar.gz` backup archive (not recommended). |
| `-f`, `--force` | Skip interactive `[y/N]` confirmation prompts. Ideal for automated scripting. |

### Module Flags
| Flag | Description |
| :--- | :--- |
| `--cache` | Scan cleanable application caches, thumbnails, trash, and system temporary files. When combined with `--clean`, purges them. |
| `--packages` | Scan DNF, RPM, Flatpak, and Snap for unneeded dependencies, redundant kernels, unused runtimes, and disabled revisions. |
| `--retired` | Scan and remove retired or repository-orphaned RPM packages (extras no longer present in any active repo). |
| `--symlinks` | Scan and clean broken or stale symbolic links across user and system directories. |
| `--selinux-fix-boot` | Schedule SELinux policy and file context relabel on next boot (`sudo fixfiles -B onboot`). Alias: `--fix-selinux`. |
| `--selinux-status` | Display current SELinux enforcement mode, policy, and next-boot autorelabel schedule. |
| `--diff <FILE>` | View a syntax-highlighted unified diff between an RPM template (`.rpmnew` or `.rpmsave`) and its active configuration file. |
| `--restore [ID]` | List available backup archives (if no ID specified) or restore files from a specific backup ID or path. |
| `--reset-app <APP>` | Reset an application's settings to factory defaults with automatic backup (**Dry run by default** unless `--apply`). |
| `-h`, `--help` | Display command usage and examples. |

---

## 🛡️ Dry Run Default Behavior

ConfClean FC operates under a strict **dry run by default** policy for all destructive commands:
* If you execute `./main.py --clean`, it scans for orphans, displays the table, and performs a **simulation**:
  ```text
  [DRY RUN] Dry run complete: 45 items would be cleaned (378.9 MB reclaimable).
  [DRY RUN MODE ENABLED BY DEFAULT] No files were removed. To perform actual deletion, add --apply.
  ```
* To execute the actual cleanup and delete the files with a pre-clean backup archive, pass `--apply`:
  ```bash
  ./main.py --clean --apply
  ```

---

## 💡 Practical Examples

### 1. Scan for Orphan Configurations
Display all leftover configs from previously uninstalled applications:
```bash
./main.py --scan
```

### 2. Simulate Orphan Cleanup (Dry Run)
Verify what would be deleted without risking any files:
```bash
./main.py --clean
# or explicitly:
./main.py --dry-run
```

### 3. Clean Orphans with Automatic Pre-Backup
Prompt for confirmation, archive all targets to `~/.local/share/confclean-fc/backups/`, and purge:
```bash
./main.py --clean --apply
```

### 4. Automated Scripting (Non-Interactive)
Bypass confirmation prompts in automated cron jobs or setup scripts:
```bash
./main.py --clean --apply -f
```

### 5. Inspect and Clean Caches
Inspect reclaimable cache categories:
```bash
./main.py --cache
```

Simulate purging all accessible caches:
```bash
./main.py --cache --clean
```

Purge caches for real:
```bash
./main.py --cache --clean --apply -f
```

### 6. Query Unneeded Packages and Old Kernels
Query DNF for unneeded dependencies and old redundant kernels while preserving the booted kernel (`uname -r`):
```bash
./main.py --packages
```

### 7. List and Restore Backup Archives
List all historical backups created by ConfClean FC:
```bash
./main.py --restore list
```

Restore all files from a specific backup archive:
```bash
./main.py --restore confclean_backup_20261029_110021
```

### 8. Factory Reset an Application
Simulate resetting Firefox preferences and caches:
```bash
./main.py --reset-app firefox
```

Commit the factory reset (creates a pre-reset backup before wiping):
```bash
./main.py --reset-app firefox --apply
```

### 9. View Configuration Diff (.rpmnew / .rpmsave)
Compare an incoming RPM upgrade template against the existing live configuration file:
```bash
./main.py --diff /etc/cups/cupsd.conf.rpmnew
```

### 10. Scan and Remove Retired Packages (Repo Extras)
Scan installed packages that are no longer available in any active repository:
```bash
./main.py --retired
```

Simulate removal (dry run by default):
```bash
./main.py --retired --clean
```

Execute removal of retired packages:
```bash
./main.py --retired --clean --apply
```

### 11. Schedule SELinux Policy & File Context Fix on Next Boot
Check whether SELinux is active and if a relabel is scheduled:
```bash
./main.py --selinux-status
```

Schedule file context repair on next boot via `fixfiles -B onboot` (elevates via `sudo`):
```bash
./main.py --selinux-fix-boot
```

---

## 📂 File Locations

| Path | Purpose |
| :--- | :--- |
| `~/.local/share/confclean-fc/backups/` | Storage directory for pre-deletion `.tar.gz` backup archives and companion `.log` files. |
| `~/.local/share/confclean-fc/logs/audit.log` | Persistent append-only audit log recording every scan, clean, reset, and restore event. |
| `~/.config/confclean-fc/whitelist.json` | User-defined custom protection whitelist. |

---

## 🚦 Exit Codes

* `0`: Command completed successfully or dry run completed without errors.
* `1`: Command aborted by user, target not found, or operation encountered an error.

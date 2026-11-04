# ConfClean FC Safety Specification & Protection Engine 🛡️🔒

**Safety is the foremost guiding principle of ConfClean FC.** Linux users often hesitate to use automated cleaner tools because poorly engineered cleaners can delete essential desktop configurations, broken symlinks, shell files, or system credentials.

ConfClean FC implements an **ironclad multi-layer defense system** to ensure your system remains completely stable, functional, and recoverable at all times.

---

> [!CAUTION]
> ## ⚠️ BETA STATUS, DISCLAIMER & USE AT YOUR OWN RISK
>
> **ConfClean FC is currently in active BETA.**
>
> While every feature has been built with defense-in-depth safety checks and backed by comprehensive unit tests, configuration cleaning inherently interacts with live system and user application files.
>
> **Please read and understand this disclaimer prior to using the application:**
> 1. **USE STRICTLY AT YOUR OWN RISK**: The software is provided "as is", without warranty of any kind, express or implied.
> 2. **NO LIABILITY**: Under no legal theory (contract, tort, negligence, or otherwise) shall the authors, maintainers, or contributors be liable for any damages, data loss, operating system unbootability, package removal issues, desktop environment crashes, or system downtime arising from the operation of this software.
> 3. **INDEPENDENT BACKUP REQUIREMENT**: Although ConfClean FC automatically generates `.tar.gz` safety archives with JSON manifests prior to cleaning, **automated backups do not replace an external, independent backup strategy**. Maintain full backups of your home directory (`~`) and critical configurations prior to executing non-dry-run operations.
> 4. **USER RESPONSIBILITY**: It is the user's sole responsibility to inspect candidate files presented during dry-run scans before approving file purge or application reset.

---

## 🛑 Layer 1: The Ironclad System Safelist

The core `SafetyEngine` ([`confclean/core/safelist.py`](file:///home/turajb/cursorProjects/confCleanFc/confclean/core/safelist.py)) evaluates every candidate file or directory against hardcoded protection patterns. If an item matches any protected rule, **it is immediately locked and cannot be selected or deleted under any circumstances**.

### 1. Desktop Environments & Shell Compositors
Configuration files and socket state for all major Linux desktop environments are permanently protected:
* **GNOME**: `gnome*`, `gdm`, `dconf`, `nautilus`, `evolution-data-server`, `gvfs`, `tracker*`.
* **KDE Plasma**: `plasma*`, `kdeglobals`, `kwin*`, `kscreen`, `dolphin`, `sddm`.
* **XFCE / Cinnamon / MATE**: `xfce*`, `cinnamon*`, `mate*`, `marco`.
* **Tiling Wayland Compositors**: `sway`, `hyprland`, `waybar`, `mako`, `wofi`.

### 2. Core OS Plumbing & Audio/Display Subsystems
* **System Services**: `systemd`, `dbus`, `polkit`, `upower`, `NetworkManager`.
* **Audio Subsystem**: `pipewire`, `wireplumber`, `pulse`, `alsa`.
* **Graphics & Fonts**: `fontconfig`, `mesa`, `vulkan`, `glvnd`, `monitors.xml`.
* **Desktop Standards**: `user-dirs.*`, `mimeapps.list`, `gtk-*`, `qt*`.

### 3. Security, Authentication & Cryptographic Credentials
Any path containing sensitive credentials or keys is blocked automatically across all path segments:
* **SSH Keys**: `~/.ssh`, `id_rsa`, `id_ed25519`, `authorized_keys`, `known_hosts`.
* **GPG & Keyrings**: `~/.gnupg`, `keyrings`, `pki`, `certificates`, `ca-trust`.
* **Authentication**: `kwallet*`, `gnome-keyring`, `auth`, `secrets`, `passwd`, `shadow`.

### 4. Developer Environments & Toolchains
ConfClean FC prevents accidental deletion of project setups, caches, and repository configurations:
* **Version Control**: `.git`, `.gitignore`, `.gitconfig`, `.svn`, `.hg`.
* **Compilers & Package Managers**: `.cargo`, `.rustup`, `.gradle`, `.m2`, `.dotnet`, `virtualenvs`.
* **Shell Profiles**: `.bashrc`, `.bash_profile`, `.zshrc`, `.profile`.

### 5. Critical System Directories
When operating in root mode, ConfClean FC strictly blocks modification of system mount points and essential OS partitions:
* `/`, `/boot`, `/boot/efi`, `/dev`, `/proc`, `/sys`, `/usr`, `/lib`, `/lib64`, `/bin`, `/sbin`, `/root`.
* Critical system configuration files: `/etc/passwd`, `/etc/shadow`, `/etc/fstab`, `/etc/os-release`, `/etc/sudoers`.

---

## 🎯 Layer 2: Custom User Whitelist

Users can define their own permanent protection rules via:
1. **The GUI Settings & Safelist Tab**: Add exact folder names or substring keywords to the Whitelist list (changes take effect immediately and auto-refresh dynamically across all tabs).
2. **The JSON Configuration File**: Located at `~/.config/confclean-fc/custom_whitelist.json`.

```json
[
  "my_custom_tool",
  "project_alpha_settings"
]
```

Any item matching a custom whitelist entry is displayed in the GUI with a greyed-out checkbox and marked `PROTECTED (User Whitelist)`.

---

## 🔄 Layer 3: Dry Run ON by Default

All deletion and factory reset operations in ConfClean FC default to **Dry Run mode**:
* In the **GUI**, the "Dry Run (Simulation)" checkbox is checked on startup. Destructive buttons display a magnifying glass icon `🔍 Simulate Clean (Dry Run)`.
* In the **CLI**, running `--clean`, `--cache --clean`, or `--reset-app` simulates the cleanup without touching any files.
* To perform actual deletion, the user must explicitly uncheck the box in the GUI or pass `--apply` in the CLI.

---

## 📦 Layer 4: Automatic Pre-Deletion Backup Archives

Whenever ConfClean FC performs actual deletions or an application factory reset, it executes a mandatory backup phase:
1. **Compressed Archive**: Targets are compressed into a `.tar.gz` archive stored at `~/.local/share/confclean-fc/backups/`.
2. **Structured JSON Manifest**: A `manifest.json` is embedded inside the archive recording:
   * Unique Backup ID
   * Timestamp
   * User name and OS version
   * Absolute original paths
   * Permissions and timestamps
   * Reason for removal
3. **Companion Human-Readable Log**: A `.log` file is placed adjacent to the archive.
4. **Pre-Flight Disk Space Check**: If the system does not have sufficient free disk space to store the archive, the operation **aborts immediately** before a single file is touched.

---

## 🔁 Layer 5: Built-in Selective & Full Restore Tool

If you ever need to retrieve a deleted configuration or undo an application reset:
* Open the **Restore & Backups** tab in the GUI or run `./main.py --restore <Backup_ID>` in the CLI.
* You can restore the **entire archive** or selectively restore **individual application configurations**.
* **Conflict Resolution**: Choose whether to skip already existing files or overwrite them with the backed-up version.

---

## 🐧 Layer 6: Safe Kernel & Package Management

RPM-based systems (like Fedora) regularly install newer Linux kernels while maintaining fallback kernels. ConfClean FC protects against kernel unbootability:
* **Running Kernel**: Evaluates `uname -r`. The running booted kernel is locked as `PROTECTED`.
* **Fallback Kernel**: Identifies the latest alternative kernel installed on the system and locks it as `PROTECTED`.
* **Old Redundant Kernels**: Only kernels that are 3rd or older are offered as removal candidates.
* **DNF Dependencies**: Unneeded dependencies are cross-checked against core system libraries before removal commands are generated.

---

## 🛡️ Layer 7: Privilege Separation & Polkit

* **User Space Isolation**: Regular configuration cleaning (`~/.config`, `~/.local/share`, `~/.var/app`) runs strictly unprivileged with normal user permissions, completely isolated from system files.
* **Privileged System Maintenance**: System cleaning (`/var/cache/dnf`, `journalctl`, `/etc/*.rpmsave`) and on-boot SELinux relabeling require root privileges.
* **Asynchronous Polkit Escalation (`pkexec`)**: When elevated actions are initiated from the GUI without root permissions, ConfClean FC invokes `pkexec` asynchronously inside dedicated background `QThread` workers. This prevents main Qt event loop stalls, avoiding window manager ping timeouts (`_NET_WM_PING`) in Wayland/GNOME that would otherwise steal keyboard focus away from Polkit password prompts.
* **SELinux Re-label Safety**: Scheduling an SELinux relabel invokes standard `/usr/sbin/fixfiles -B onboot` creating `/.autorelabel`. ConfClean FC can safely cancel the scheduled relabel at any time by removing `/.autorelabel` via `pkexec /usr/bin/rm -f /.autorelabel` without modifying or compromising active SELinux policy rules.

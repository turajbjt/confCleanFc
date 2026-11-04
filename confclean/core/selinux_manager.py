"""
SELinux Policy and File Context Maintenance Manager for ConfClean FC.
Provides inspection of SELinux status and scheduling of on-boot file relabeling
via fixfiles -B onboot.
"""

import os
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple

from confclean.core.logger import get_logger


class SELinuxManager:
    """Manages SELinux inspection and on-boot policy/context repairs."""

    AUTORELABEL_PATH = "/.autorelabel"

    def __init__(self, fixfiles_bin: Optional[str] = None):
        self.logger = get_logger()
        self.fixfiles_bin = fixfiles_bin or self._find_fixfiles()
        self.is_root = (os.geteuid() == 0)

    def _find_fixfiles(self) -> Optional[str]:
        """Locates the fixfiles executable on the system."""
        for path in ["/usr/bin/fixfiles", "/usr/sbin/fixfiles", "/sbin/fixfiles"]:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return shutil.which("fixfiles")

    def is_selinux_supported(self) -> bool:
        """Checks if SELinux is supported and tools exist on this distribution."""
        return self.fixfiles_bin is not None or os.path.exists("/etc/selinux") or os.path.exists("/sys/fs/selinux")

    def get_status(self) -> Dict[str, object]:
        """
        Returns a dictionary detailing the current SELinux state:
        - enabled: bool
        - mode: str ("Enforcing", "Permissive", "Disabled", "Not Installed")
        - policy: str ("targeted", "mls", "minimum", etc.)
        - autorelabel_scheduled: bool
        - autorelabel_flags: str
        - fixfiles_available: bool
        - fixfiles_path: Optional[str]
        """
        status: Dict[str, object] = {
            "enabled": False,
            "mode": "Disabled",
            "policy": "unknown",
            "autorelabel_scheduled": False,
            "autorelabel_flags": "",
            "fixfiles_available": self.fixfiles_bin is not None,
            "fixfiles_path": self.fixfiles_bin,
        }

        # 1. Query python-selinux bindings if available
        try:
            import selinux
            if selinux.is_selinux_enabled() == 1:
                status["enabled"] = True
                enf = selinux.security_getenforce()
                status["mode"] = "Enforcing" if enf == 1 else ("Permissive" if enf == 0 else "Disabled")
                pol_res = selinux.selinux_getpolicytype()
                if isinstance(pol_res, (list, tuple)) and len(pol_res) >= 2:
                    status["policy"] = str(pol_res[1])
                elif isinstance(pol_res, str):
                    status["policy"] = pol_res
            else:
                status["enabled"] = False
                status["mode"] = "Disabled"
        except Exception:
            # Fallback to sestatus or /sys/fs/selinux
            if os.path.exists("/sys/fs/selinux") and os.path.isdir("/sys/fs/selinux"):
                status["enabled"] = True
                try:
                    res = subprocess.run(["sestatus"], capture_output=True, text=True, check=False, timeout=5)
                    if res.returncode == 0:
                        for line in res.stdout.splitlines():
                            line_s = line.strip()
                            if "Current mode:" in line_s:
                                status["mode"] = line_s.split(":", 1)[1].strip().capitalize()
                            elif "Loaded policy name:" in line_s:
                                status["policy"] = line_s.split(":", 1)[1].strip()
                except Exception:
                    pass

        # 2. Check for scheduled on-boot autorelabel
        status["autorelabel_scheduled"] = self.is_autorelabel_scheduled()
        if status["autorelabel_scheduled"]:
            try:
                if os.path.isfile(self.AUTORELABEL_PATH):
                    with open(self.AUTORELABEL_PATH, "r", encoding="utf-8", errors="replace") as f:
                        status["autorelabel_flags"] = f.read().strip()
            except Exception:
                status["autorelabel_flags"] = "active"

        return status

    def is_autorelabel_scheduled(self) -> bool:
        """Returns True if /.autorelabel is present on the filesystem."""
        try:
            return os.path.lexists(self.AUTORELABEL_PATH)
        except OSError:
            return False

    def get_schedule_command(
        self,
        boottime_only: bool = True,
        force: bool = False,
        use_pkexec: bool = False,
        use_sudo: bool = False,
    ) -> List[str]:
        """
        Builds the command arguments to schedule an on-boot SELinux relabel.
        Example: ['fixfiles', '-B', 'onboot'] or ['sudo', 'fixfiles', '-B', 'onboot'].
        """
        bin_path = self.fixfiles_bin or "fixfiles"
        cmd = [bin_path]
        if force:
            cmd.append("-F")
        if boottime_only:
            cmd.append("-B")
        cmd.append("onboot")

        if self.is_root:
            return cmd

        if use_pkexec:
            pkexec_bin = shutil.which("pkexec")
            if pkexec_bin:
                return [pkexec_bin] + cmd
        elif use_sudo:
            sudo_bin = shutil.which("sudo")
            if sudo_bin:
                return [sudo_bin] + cmd

        # If escalation requested but not specified, prefer pkexec if available, else sudo
        esc = shutil.which("pkexec") if use_pkexec else (shutil.which("sudo") or shutil.which("pkexec"))
        if esc:
            return [esc] + cmd
        return cmd

    def get_cancel_command(self, use_pkexec: bool = False, use_sudo: bool = False) -> List[str]:
        """Builds command arguments to remove /.autorelabel and cancel scheduled relabel."""
        rm_bin = shutil.which("rm") or "/bin/rm"
        cmd = [rm_bin, "-f", self.AUTORELABEL_PATH]
        if self.is_root:
            return cmd

        if use_pkexec:
            pkexec_bin = shutil.which("pkexec")
            if pkexec_bin:
                return [pkexec_bin] + cmd
        elif use_sudo:
            sudo_bin = shutil.which("sudo")
            if sudo_bin:
                return [sudo_bin] + cmd

        esc = shutil.which("pkexec") if use_pkexec else (shutil.which("sudo") or shutil.which("pkexec"))
        if esc:
            return [esc] + cmd
        return cmd

    def schedule_onboot_fix(
        self,
        boottime_only: bool = True,
        force: bool = False,
        use_pkexec: bool = False,
        use_sudo: bool = False,
    ) -> Tuple[bool, str]:
        """
        Schedules an SELinux policy and file context fix on the next boot via fixfiles -B onboot.
        Returns (success: bool, message: str).
        """
        if not self.fixfiles_bin:
            msg = "The 'fixfiles' utility is not installed on this system. Please install 'policycoreutils'."
            self.logger.error(msg)
            return False, msg

        cmd = self.get_schedule_command(
            boottime_only=boottime_only,
            force=force,
            use_pkexec=use_pkexec,
            use_sudo=use_sudo,
        )

        try:
            self.logger.info(f"Executing: {' '.join(cmd)}")
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=180 if use_pkexec else 30,
            )

            # Check if command succeeded or /.autorelabel was created
            if res.returncode == 0 or self.is_autorelabel_scheduled():
                msg = (
                    "SELinux policy relabel scheduled for next boot (via fixfiles -B onboot). "
                    "The system will automatically verify and repair file contexts created or modified "
                    "since the last boot during the next system startup."
                )
                self.logger.info(
                    f"AUDIT | Action: SELINUX_ONBOOT_SCHEDULED | Target: '{self.AUTORELABEL_PATH}' | "
                    f"Status: SUCCESS | Note: fixfiles -B onboot"
                )
                return True, msg
            elif res.returncode in (126, 127):
                return False, "Authorization cancelled by user."
            else:
                err = res.stderr.strip() or res.stdout.strip() or f"Process exited with code {res.returncode}"
                if "cancelled" in err.lower() or "not authorized" in err.lower():
                    return False, "Authorization cancelled by user."
                msg = f"Failed to schedule SELinux relabel: {err}"
                self.logger.error(msg)
                return False, msg

        except subprocess.TimeoutExpired:
            msg = "Timed out waiting for authorization."
            self.logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Error scheduling SELinux relabel: {e}"
            self.logger.error(msg)
            return False, msg

    def cancel_onboot_fix(self, use_pkexec: bool = False, use_sudo: bool = False) -> Tuple[bool, str]:
        """
        Cancels a scheduled on-boot SELinux relabel by removing /.autorelabel.
        Returns (success: bool, message: str).
        """
        if not self.is_autorelabel_scheduled():
            return True, "No on-boot SELinux relabel was scheduled (/.autorelabel does not exist)."

        if self.is_root:
            try:
                os.remove(self.AUTORELABEL_PATH)
                self.logger.info(
                    f"AUDIT | Action: SELINUX_ONBOOT_CANCELLED | Target: '{self.AUTORELABEL_PATH}' | Status: SUCCESS"
                )
                return True, "Cancelled on-boot SELinux relabel (removed /.autorelabel)."
            except OSError as e:
                msg = f"Failed to remove /.autorelabel: {e}"
                self.logger.error(msg)
                return False, msg

        cmd = self.get_cancel_command(use_pkexec=use_pkexec, use_sudo=use_sudo)
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=180 if use_pkexec else 15,
            )
            if res.returncode == 0 or not self.is_autorelabel_scheduled():
                self.logger.info(
                    f"AUDIT | Action: SELINUX_ONBOOT_CANCELLED | Target: '{self.AUTORELABEL_PATH}' | Status: SUCCESS"
                )
                return True, "Cancelled on-boot SELinux relabel (removed /.autorelabel)."
            elif res.returncode in (126, 127):
                return False, "Authorization cancelled by user."
            else:
                err = res.stderr.strip() or f"Exit code {res.returncode}"
                if "cancelled" in err.lower() or "not authorized" in err.lower():
                    return False, "Authorization cancelled by user."
                return False, f"Failed to cancel on-boot relabel: {err}"
        except subprocess.TimeoutExpired:
            return False, "Timed out waiting for authorization."
        except Exception as e:
            return False, f"Error cancelling on-boot relabel: {e}"

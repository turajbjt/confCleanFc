"""
Unit tests for SELinuxManager in ConfClean FC.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.selinux_manager import SELinuxManager


class TestSELinuxManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SELinuxManager(fixfiles_bin="/usr/bin/fixfiles")

    def test_status_structure(self):
        st = self.mgr.get_status()
        self.assertIn("enabled", st)
        self.assertIn("mode", st)
        self.assertIn("policy", st)
        self.assertIn("autorelabel_scheduled", st)
        self.assertIn("autorelabel_flags", st)
        self.assertIn("fixfiles_available", st)

    def test_schedule_command_root(self):
        self.mgr.is_root = True
        cmd = self.mgr.get_schedule_command(boottime_only=True, force=False)
        self.assertEqual(cmd, ["/usr/bin/fixfiles", "-B", "onboot"])

        cmd_force = self.mgr.get_schedule_command(boottime_only=True, force=True)
        self.assertEqual(cmd_force, ["/usr/bin/fixfiles", "-F", "-B", "onboot"])

    def test_schedule_command_user_pkexec_and_sudo(self):
        self.mgr.is_root = False
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda bin: f"/usr/bin/{bin}"
            # Test pkexec
            cmd_pk = self.mgr.get_schedule_command(boottime_only=True, use_pkexec=True)
            self.assertEqual(cmd_pk[0], "/usr/bin/pkexec")
            self.assertEqual(cmd_pk[1:], ["/usr/bin/fixfiles", "-B", "onboot"])

            # Test sudo
            cmd_sudo = self.mgr.get_schedule_command(boottime_only=True, use_sudo=True)
            self.assertEqual(cmd_sudo[0], "/usr/bin/sudo")
            self.assertEqual(cmd_sudo[1:], ["/usr/bin/fixfiles", "-B", "onboot"])

    @patch("subprocess.run")
    def test_schedule_onboot_fix_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        with patch.object(self.mgr, "is_autorelabel_scheduled", return_value=True):
            success, msg = self.mgr.schedule_onboot_fix(boottime_only=True)
            self.assertTrue(success)
            self.assertIn("SELinux policy relabel scheduled for next boot", msg)

    @patch("subprocess.run")
    def test_schedule_onboot_fix_failure(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Permission denied"
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        with patch.object(self.mgr, "is_autorelabel_scheduled", return_value=False):
            success, msg = self.mgr.schedule_onboot_fix(boottime_only=True)
            self.assertFalse(success)
            self.assertIn("Permission denied", msg)

    def test_cancel_onboot_fix_when_not_scheduled(self):
        with patch.object(self.mgr, "is_autorelabel_scheduled", return_value=False):
            success, msg = self.mgr.cancel_onboot_fix()
            self.assertTrue(success)
            self.assertIn("No on-boot SELinux relabel was scheduled", msg)

    @patch("os.remove")
    def test_cancel_onboot_fix_root(self, mock_remove):
        self.mgr.is_root = True
        with patch.object(self.mgr, "is_autorelabel_scheduled", return_value=True):
            success, msg = self.mgr.cancel_onboot_fix()
            self.assertTrue(success)
            mock_remove.assert_called_once_with(self.mgr.AUTORELABEL_PATH)

    @patch("subprocess.run")
    def test_cancel_onboot_fix_user(self, mock_run):
        self.mgr.is_root = False
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        with patch.object(self.mgr, "is_autorelabel_scheduled", side_effect=[True, False]):
            success, msg = self.mgr.cancel_onboot_fix(use_sudo=True)
            self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()

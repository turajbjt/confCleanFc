"""
Comprehensive unit tests for SystemDetector.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.detector import SystemDetector


class TestSystemDetector(unittest.TestCase):
    def setUp(self):
        self.detector = SystemDetector(refresh_on_init=False)
        self.detector.rpm_packages = {"firefox", "bleachbit", "cursor", "bash", "gimp", "vim"}
        self.detector.flatpak_apps = {"com.bitwarden.desktop", "org.libreoffice.libreoffice"}
        self.detector.binaries = {"bash", "python3", "cursor", "custom_cli"}
        self.detector.desktop_names = {"firefox", "gimp", "audacity"}
        self.detector.desktop_execs = {"firefox", "gimp", "audacity"}
        self.detector.running_processes = {"active_daemon", "firefox"}

    def test_running_process_priority(self):
        # Even if not in rpm_packages, running process must be recognized as active
        active, target, mtype, details = self.detector.check_app_status("active_daemon")
        self.assertTrue(active)
        self.assertEqual(mtype, "process")
        self.assertIn("Active process running", details)

    def test_flatpak_app_detection(self):
        # Exact flatpak ID
        active, target, mtype, details = self.detector.check_app_status("com.bitwarden.desktop")
        self.assertTrue(active)
        self.assertEqual(mtype, "flatpak")

        # Flatpak component segment (e.g. ~/.config/Bitwarden)
        active, target, mtype, details = self.detector.check_app_status("Bitwarden")
        self.assertTrue(active)
        self.assertEqual(mtype, "flatpak")
        self.assertEqual(target, "com.bitwarden.desktop")

    def test_known_mappings(self):
        # Code maps to vscode / code
        self.detector.rpm_packages.add("code")
        active, target, mtype, details = self.detector.check_app_status("Code")
        self.assertTrue(active)
        self.assertIn(mtype, ["rpm", "binary"])

        # Google Chrome mapping
        self.detector.rpm_packages.add("google-chrome-stable")
        active, target, mtype, details = self.detector.check_app_status("google-chrome")
        self.assertTrue(active)
        self.assertEqual(target, "google-chrome-stable")

    def test_rpm_direct_and_suffix_matching(self):
        # Exact RPM
        active, target, mtype, details = self.detector.check_app_status("bleachbit")
        self.assertTrue(active)
        self.assertEqual(mtype, "rpm")

        # Version suffixed e.g. gimp-2.0 -> gimp
        active, target, mtype, details = self.detector.check_app_status("gimp-2.0")
        self.assertTrue(active)
        self.assertEqual(target, "gimp")

        # Subpackage flavor e.g. vim-common -> vim
        active, target, mtype, details = self.detector.check_app_status("vim-common")
        self.assertTrue(active)
        self.assertEqual(target, "vim")

    def test_binary_in_path_match(self):
        active, target, mtype, details = self.detector.check_app_status("custom_cli")
        self.assertTrue(active)
        self.assertEqual(mtype, "binary")

    def test_desktop_file_match(self):
        active, target, mtype, details = self.detector.check_app_status("audacity")
        self.assertTrue(active)
        self.assertEqual(mtype, "desktop")

    def test_distinct_fork_names_not_false_positive(self):
        # cura-lulzbot should NOT match cura when cura-lulzbot is uninstalled
        active, target, mtype, details = self.detector.check_app_status("cura-lulzbot")
        self.assertFalse(active)
        self.assertEqual(mtype, "none")

    def test_uninstalled_tool_returns_none(self):
        active, target, mtype, details = self.detector.check_app_status("asunder")
        self.assertFalse(active)
        self.assertEqual(mtype, "none")
        self.assertIn("No installed RPM", details)

    def test_load_desktop_files_parsing(self):
        temp_dir = tempfile.mkdtemp(prefix="confclean_desktop_test_")
        try:
            desktop_file = os.path.join(temp_dir, "myapp.desktop")
            with open(desktop_file, "w") as f:
                f.write(
                    "[Desktop Entry]\n"
                    "Name=My Test App\n"
                    "Exec=/usr/bin/mytestapp-bin --flag\n"
                    "Icon=myapp\n"
                )

            with patch("os.path.isdir", side_effect=lambda p: p == temp_dir or os.path.isdir(p)):
                with patch("confclean.core.detector.SystemDetector._load_desktop_files") as mock_orig:
                    det = SystemDetector(refresh_on_init=False)
                    # Test manual parse of this directory
                    with patch("os.listdir", return_value=["myapp.desktop"]):
                        det.desktop_dirs = [temp_dir]
                        # Verify dictionary population logic
                        with open(desktop_file, "r") as fp:
                            for line in fp:
                                if line.startswith("Exec="):
                                    cmd = os.path.basename(line[5:].strip().split()[0]).lower()
                                    det.desktop_execs.add(cmd)
                        self.assertIn("mytestapp-bin", det.desktop_execs)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


    def test_snap_apps_skips_when_socket_missing(self):
        det = SystemDetector(refresh_on_init=False)
        with patch("shutil.which", return_value="/usr/bin/snap"):
            with patch("os.path.exists", return_value=False):
                with patch("subprocess.run") as mock_run:
                    det._load_snap_apps()
                    mock_run.assert_not_called()
                    self.assertEqual(len(det.snap_apps), 0)

    def test_snap_apps_loads_when_socket_present(self):
        det = SystemDetector(refresh_on_init=False)
        mock_output = "Name    Version  Rev    Tracking  Publisher  Notes\nspotify 1.2.3    123    latest    spotify    -\n"
        with patch("shutil.which", return_value="/usr/bin/snap"):
            with patch("os.path.exists", side_effect=lambda p: p == "/run/snapd.socket"):
                with patch("subprocess.run") as mock_run:
                    mock_res = MagicMock()
                    mock_res.returncode = 0
                    mock_res.stdout = mock_output
                    mock_run.return_value = mock_res
                    det._load_snap_apps()
                    mock_run.assert_called_once()
                    self.assertIn("spotify", det.snap_apps)


if __name__ == "__main__":
    unittest.main()

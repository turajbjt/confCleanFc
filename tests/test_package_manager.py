"""
Comprehensive unit tests for PackageManager and PackageSuggestion.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.package_manager import PackageManager, PackageSuggestion


class TestPackageManager(unittest.TestCase):
    def setUp(self):
        self.mgr = PackageManager()

    def test_package_suggestion_properties(self):
        s = PackageSuggestion(
            name="kernel-devel",
            version="7.2.10",
            release="200.fc44",
            arch="x86_64",
            size_bytes=50 * 1024 * 1024,
            summary="Development files for the Linux kernel",
            category="old_kernel",
            reason="Old kernel",
        )
        self.assertEqual(s.full_nevra, "kernel-devel-7.2.10-200.fc44.x86_64")
        self.assertEqual(s.removal_spec, "kernel-devel-7.2.10-200.fc44.x86_64")
        self.assertEqual(s.formatted_size, "50.0 MB")

        # Standard unneeded dep uses simple package name for removal
        s_dep = PackageSuggestion(
            name="unused-lib",
            version="1.2.3",
            release="1.fc44",
            arch="x86_64",
            size_bytes=1024,
            summary="Unused library",
            category="unneeded_dep",
            reason="Unneeded",
        )
        self.assertEqual(s_dep.removal_spec, "unused-lib")

        # Duplicate package uses full spec
        s_dup = PackageSuggestion(
            name="curl",
            version="8.5.0",
            release="1.fc44",
            arch="x86_64",
            size_bytes=1024,
            summary="Duplicate version",
            category="duplicate",
            reason="Duplicate",
        )
        self.assertEqual(s_dup.removal_spec, "curl-8.5.0-1.fc44.x86_64")

    def test_removal_command_builder_root_and_user(self):
        s1 = PackageSuggestion(
            name="orphan-dep",
            version="1.0",
            release="1",
            arch="x86_64",
            size_bytes=1000,
            summary="Orphan",
            category="unneeded_dep",
            reason="Unneeded",
            is_protected=False,
            is_selected=True,
        )
        s_unselected = PackageSuggestion(
            name="skipped-dep",
            version="1.0",
            release="1",
            arch="x86_64",
            size_bytes=1000,
            summary="Skipped",
            category="unneeded_dep",
            reason="Unselected",
            is_protected=False,
            is_selected=False,
        )
        s_protected = PackageSuggestion(
            name="kernel-core",
            version="7.2.13",
            release="200.fc44",
            arch="x86_64",
            size_bytes=50000000,
            summary="Running kernel",
            category="old_kernel",
            reason="Running kernel",
            is_protected=True,
            is_selected=True,  # Even if somehow selected, must NEVER be in command!
        )

        # Test as regular user -> uses pkexec when available
        self.mgr.is_root = False
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda bin: "/usr/bin/pkexec" if bin == "pkexec" else None
            cmd = self.mgr.get_removal_command([s1, s_unselected, s_protected])
            self.assertIn("pkexec", cmd)
            self.assertIn("orphan-dep", cmd)
            self.assertNotIn("skipped-dep", cmd)
            self.assertNotIn("kernel-core", cmd)

        # Test fallback to sudo when pkexec is absent
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda bin: "/usr/bin/sudo" if bin == "sudo" else None
            cmd_sudo = self.mgr.get_removal_command([s1])
            self.assertIn("sudo", cmd_sudo)
            self.assertIn("orphan-dep", cmd_sudo)

        # Test as root -> no pkexec or sudo
        self.mgr.is_root = True
        cmd_root = self.mgr.get_removal_command([s1])
        self.assertNotIn("pkexec", cmd_root)
        self.assertNotIn("sudo", cmd_root)
        self.assertEqual(cmd_root[0], self.mgr.dnf_bin)

        # Test empty selection -> empty command
        self.assertEqual(self.mgr.get_removal_command([]), [])

    @patch("subprocess.run")
    def test_old_kernels_protection_logic(self, mock_subproc):
        # Mock dnf repoquery --installonly output with 3 kernels
        kernel_stdout = (
            "kernel-core-0:7.2.13-200.fc44.x86_64\n"
            "kernel-modules-0:7.2.13-200.fc44.x86_64\n"
            "kernel-core-0:7.2.12-200.fc44.x86_64\n"
            "kernel-modules-0:7.2.12-200.fc44.x86_64\n"
            "kernel-core-0:7.2.10-200.fc44.x86_64\n"
            "kernel-modules-0:7.2.10-200.fc44.x86_64\n"
        )
        mock_subproc.return_value = MagicMock(returncode=0, stdout=kernel_stdout)

        # Mock uname release as 7.2.13-200.fc44.x86_64
        with patch("os.uname") as mock_uname:
            mock_uname.return_value = MagicMock(release="7.2.13-200.fc44.x86_64")
            with patch.object(self.mgr, "_get_rpm_info_map", return_value={}):
                kernels = self.mgr._get_old_kernels()

        self.assertEqual(len(kernels), 6)

        # Check running kernel 7.2.13 -> Protected, not selected
        k_running = [k for k in kernels if "7.2.13" in k.version]
        for k in k_running:
            self.assertTrue(k.is_protected)
            self.assertFalse(k.is_selected)
            self.assertIn("Currently running booted kernel", k.reason)

        # Check fallback kernel 7.2.12 -> Protected, not selected
        k_fallback = [k for k in kernels if "7.2.12" in k.version]
        for k in k_fallback:
            self.assertTrue(k.is_protected)
            self.assertFalse(k.is_selected)
            self.assertIn("Latest fallback backup kernel", k.reason)

        # Check older kernel 7.2.10 -> Unprotected, SELECTED for removal!
        k_old = [k for k in kernels if "7.2.10" in k.version]
        for k in k_old:
            self.assertFalse(k.is_protected)
            self.assertTrue(k.is_selected)
            self.assertIn("Old unused kernel", k.reason)

    @patch("subprocess.run")
    def test_unneeded_packages_parsing(self, mock_subproc):
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout="libtest-0:1.2.3-1.fc44.x86_64\nunused-cli-0:2.0.0-1.fc44.noarch\n",
        )
        with patch.object(self.mgr, "_get_rpm_info_map", return_value={}):
            unneeded = self.mgr._get_unneeded_packages()

        self.assertEqual(len(unneeded), 2)
        self.assertEqual(unneeded[0].name, "libtest")
        self.assertEqual(unneeded[1].name, "unused-cli")
        self.assertTrue(unneeded[0].is_selected)
        self.assertFalse(unneeded[0].is_protected)

    @patch("subprocess.run")
    def test_duplicate_packages_parsing(self, mock_subproc):
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout="curl-0:8.5.0-1.fc44.x86_64\ncurl-0:8.6.0-1.fc44.x86_64\n",
        )
        with patch.object(self.mgr, "_get_rpm_info_map", return_value={}):
            dups = self.mgr._get_duplicate_packages()

        self.assertEqual(len(dups), 2)
        self.assertEqual(dups[0].category, "duplicate")

    def test_scan_all_suggestions_progress(self):
        progress_calls = []

        def callback(msg, cur, tot):
            progress_calls.append((msg, cur, tot))

        with patch.object(self.mgr, "_get_unneeded_packages", return_value=[]):
            with patch.object(self.mgr, "_get_old_kernels", return_value=[]):
                with patch.object(self.mgr, "_get_duplicate_packages", return_value=[]):
                    with patch.object(self.mgr, "_get_unused_flatpaks", return_value=[]):
                        with patch.object(self.mgr, "_get_unused_snaps", return_value=[]):
                            res = self.mgr.scan_all_suggestions(progress_callback=callback)

        self.assertEqual(len(res), 0)
        self.assertEqual(len(progress_calls), 6)

    def test_flatpak_unused_graceful_missing(self):
        with patch("shutil.which", return_value=None):
            self.assertEqual(self.mgr._get_unused_flatpaks(), [])

    @patch("subprocess.run")
    def test_flatpak_unused_parsing(self, mock_subproc):
        stdout_sample = (
            "        ID                                      Branch        Op\n"
            " 1.     org.freedesktop.Platform.GL.default     20.08         r\n"
            " 2.     org.gnome.Platform                      40            r\n"
            "\n"
            "Proceed with these changes to the system installation? [Y/n]:\n"
        )
        mock_subproc.return_value = MagicMock(returncode=0, stdout=stdout_sample)
        with patch("shutil.which", return_value="/usr/bin/flatpak"):
            items = self.mgr._get_unused_flatpaks()

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].name, "org.freedesktop.Platform.GL.default")
        self.assertEqual(items[0].version, "20.08")
        self.assertEqual(items[0].category, "flatpak_unused")
        self.assertTrue(items[0].is_selected)

    def test_snap_unused_graceful_missing(self):
        with patch("shutil.which", return_value=None):
            self.assertEqual(self.mgr._get_unused_snaps(), [])

    @patch("subprocess.run")
    def test_snap_unused_parsing(self, mock_subproc):
        stdout_sample = (
            "Name               Version                         Rev    Tracking       Publisher     Notes\n"
            "core20             20260901                        2922   latest/stable  canonical✓    base\n"
            "core20             20260410                        2866   latest/stable  canonical✓    base,disabled\n"
            "gnome-46-2404      0+git.b31ceab-sdk0+git.ef6f7e9  177    latest/stable  canonical✓    -\n"
            "gnome-46-2404      0+git.b31ceab-sdk0+git.f80dd8b  168    latest/stable  canonical✓    disabled\n"
        )
        mock_subproc.return_value = MagicMock(returncode=0, stdout=stdout_sample)
        with patch("shutil.which", return_value="/usr/bin/snap"):
            items = self.mgr._get_unused_snaps()

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].name, "core20")
        self.assertEqual(items[0].release, "2866")
        self.assertEqual(items[0].category, "snap_unused")
        self.assertEqual(items[1].name, "gnome-46-2404")
        self.assertEqual(items[1].release, "168")

    def test_removal_commands_multi_system(self):
        rpm_pkg = PackageSuggestion(
            name="orphan-lib",
            version="1.0",
            release="1.fc44",
            arch="x86_64",
            size_bytes=100,
            summary="RPM Orphan",
            category="unneeded_dep",
            reason="Unneeded",
            is_selected=True,
        )
        flatpak_pkg = PackageSuggestion(
            name="org.gnome.Platform",
            version="40",
            release="",
            arch="",
            size_bytes=0,
            summary="Flatpak runtime",
            category="flatpak_unused",
            reason="Unused runtime",
            is_selected=True,
        )
        snap_pkg = PackageSuggestion(
            name="core20",
            version="20260410",
            release="2866",
            arch="",
            size_bytes=0,
            summary="Snap disabled",
            category="snap_unused",
            reason="Disabled revision",
            is_selected=True,
        )

        with patch("shutil.which", return_value="/bin/tool"):
            self.mgr.is_root = False
            cmds = self.mgr.get_removal_commands([rpm_pkg, flatpak_pkg, snap_pkg])
            self.assertEqual(len(cmds), 3)

            single_cmd = self.mgr.get_removal_command([rpm_pkg, flatpak_pkg, snap_pkg])
            self.assertEqual(single_cmd[0], "pkexec")
            self.assertEqual(single_cmd[1], "bash")
            self.assertEqual(single_cmd[2], "-c")
            self.assertIn("orphan-lib", single_cmd[3])
            self.assertIn("flatpak", single_cmd[3])
            self.assertIn("snap", single_cmd[3])

            # Root user runs directly under sh -c
            self.mgr.is_root = True
            root_cmd = self.mgr.get_removal_command([rpm_pkg, flatpak_pkg, snap_pkg])
            self.assertEqual(root_cmd[0], "sh")
            self.assertEqual(root_cmd[1], "-c")

    def test_single_escalation_for_multiple_snaps(self):
        s1 = PackageSuggestion(
            name="core20", version="1", release="100", arch="", size_bytes=0,
            summary="Snap 1", category="snap_unused", reason="Disabled", is_selected=True
        )
        s2 = PackageSuggestion(
            name="core24", version="1", release="200", arch="", size_bytes=0,
            summary="Snap 2", category="snap_unused", reason="Disabled", is_selected=True
        )

        with patch("shutil.which", return_value="/usr/bin/pkexec"):
            self.mgr.is_root = False
            cmd = self.mgr.get_removal_command([s1, s2])
            # Must wrap under a SINGLE pkexec call, not multiple
            self.assertEqual(cmd[0], "pkexec")
            self.assertEqual(cmd[1], "bash")
            self.assertEqual(cmd[2], "-c")
            self.assertIn("snap remove core20 --revision=100", cmd[3])
            self.assertIn("snap remove core24 --revision=200", cmd[3])
            # Ensure "pkexec" does NOT appear repeatedly inside the subshell
            self.assertNotIn("pkexec snap", cmd[3])

    @patch.dict("sys.modules", {"rpm": None})
    @patch("subprocess.run")
    def test_get_rpm_info_map_fallback_when_rpm_module_missing(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "testpkg|1.0.0|1.fc44|x86_64|0|1048576|A test package\n"
        mock_run.return_value = mock_proc

        pkg_map = self.mgr._get_rpm_info_map()
        self.assertIn("testpkg-1.0.0-1.fc44.x86_64", pkg_map)
        self.assertEqual(pkg_map["testpkg"]["size"], 1048576)
        self.assertEqual(pkg_map["testpkg"]["summary"], "A test package")


if __name__ == "__main__":
    unittest.main()

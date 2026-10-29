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
        self.assertEqual(s.formatted_size, "50.0 MB")

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

        # Test as regular user -> uses pkexec
        self.mgr.is_root = False
        cmd = self.mgr.get_removal_command([s1, s_unselected, s_protected])
        self.assertIn("pkexec", cmd)
        self.assertIn("orphan-dep", cmd)
        self.assertNotIn("skipped-dep", cmd)
        self.assertNotIn("kernel-core", cmd)

        # Test as root -> no pkexec
        self.mgr.is_root = True
        cmd_root = self.mgr.get_removal_command([s1])
        self.assertNotIn("pkexec", cmd_root)
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
                    res = self.mgr.scan_all_suggestions(progress_callback=callback)

        self.assertEqual(len(res), 0)
        self.assertEqual(len(progress_calls), 4)


if __name__ == "__main__":
    unittest.main()

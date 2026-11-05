"""
Comprehensive unit tests for ConfClean FC Command Line Interface.
"""

import argparse
import io
import unittest
from unittest.mock import MagicMock, patch

from confclean.cli import format_table, run_cli
from confclean.core.app_resetter import AppResetProfile
from confclean.core.backup_manager import BackupMetadata
from confclean.core.cache_cleaner import CacheCategory
from confclean.core.cleaner import CleanResult
from confclean.core.package_manager import PackageSuggestion
from confclean.core.scanner import ScanItem


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.mock_scanner = MagicMock()
        self.mock_cleaner = MagicMock()
        self.mock_safety = MagicMock()
        self.mock_backup_mgr = MagicMock()

    def test_format_table(self):
        headers = ["Col1", "Col2"]
        rows = [["Val1", "Value2Long"], ["Short", "V"]]
        output = format_table(rows, headers)
        self.assertIn("Col1", output)
        self.assertIn("Value2Long", output)
        self.assertIn("-+-", output)

    def test_cli_scan_and_dry_run(self):
        mock_item = ScanItem(
            path="/home/user/.config/asunder",
            name="asunder",
            category="config",
            is_directory=True,
            size_bytes=1024 * 1024,
            file_count=5,
            last_modified=100000.0,
            status="CONFIRMED_ORPHAN",
            reason="Uninstalled app",
        )
        self.mock_scanner.scan_all.return_value = [mock_item]
        clean_res = CleanResult()
        clean_res.deleted_items = [mock_item]
        clean_res.is_dry_run = True
        self.mock_cleaner.clean_items.return_value = (clean_res, "Dry run complete: 1 items would be cleaned")

        args = argparse.Namespace(
            scan=True,
            clean=False,
            dry_run=True,
            cache=False,
            packages=False,
            restore=None,
            reset_app=None,
            force=False,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("asunder", output)
        self.assertIn("[DRY RUN]", output)

    def test_cli_clean_default_dry_run(self):
        mock_item = ScanItem(
            path="/home/user/.config/asunder",
            name="asunder",
            category="config",
            is_directory=True,
            size_bytes=100,
            file_count=1,
            last_modified=100000.0,
            status="CONFIRMED_ORPHAN",
            reason="Uninstalled app",
        )
        self.mock_scanner.scan_all.return_value = [mock_item]
        clean_res = CleanResult()
        clean_res.deleted_items = [mock_item]
        clean_res.is_dry_run = True
        self.mock_cleaner.clean_items.return_value = (clean_res, "Dry run complete: 1 items would be cleaned")

        args = argparse.Namespace(
            scan=False,
            clean=True,
            dry_run=False,
            apply=False,  # Default when user doesn't specify --apply
            cache=False,
            packages=False,
            restore=None,
            reset_app=None,
            force=True,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("[DRY RUN]", output)
        self.assertIn("DRY RUN MODE ENABLED BY DEFAULT", output)
        self.mock_cleaner.clean_items.assert_called_with([mock_item], create_backup=False, dry_run=True)

    def test_cli_clean_with_force(self):
        mock_item = ScanItem(
            path="/home/user/.config/asunder",
            name="asunder",
            category="config",
            is_directory=True,
            size_bytes=100,
            file_count=1,
            last_modified=100000.0,
            status="CONFIRMED_ORPHAN",
            reason="Uninstalled app",
        )
        self.mock_scanner.scan_all.return_value = [mock_item]
        clean_res = CleanResult()
        clean_res.deleted_items = [mock_item]
        clean_res.backup_archive_path = "/backups/b1.tar.gz"
        self.mock_cleaner.clean_items.return_value = (clean_res, "Cleaned 1 items")

        args = argparse.Namespace(
            scan=False,
            clean=True,
            dry_run=False,
            cache=False,
            packages=False,
            restore=None,
            reset_app=None,
            force=True,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("Cleaned 1 items", output)
        self.assertIn("/backups/b1.tar.gz", output)

    def test_cli_clean_cancel_prompt(self):
        mock_item = ScanItem(
            path="/home/user/.config/asunder",
            name="asunder",
            category="config",
            is_directory=True,
            size_bytes=100,
            file_count=1,
            last_modified=100000.0,
            status="CONFIRMED_ORPHAN",
            reason="Uninstalled app",
        )
        self.mock_scanner.scan_all.return_value = [mock_item]

        args = argparse.Namespace(
            scan=False,
            clean=True,
            dry_run=False,
            cache=False,
            packages=False,
            restore=None,
            reset_app=None,
            force=False,
            no_backup=False,
        )

        with patch("builtins.input", return_value="n"):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                run_cli(
                    args,
                    scanner=self.mock_scanner,
                    cleaner=self.mock_cleaner,
                    safety=self.mock_safety,
                    backup_mgr=self.mock_backup_mgr,
                )
                output = mock_stdout.getvalue()

        self.assertIn("Clean operation cancelled by user", output)

    @patch("confclean.core.cache_cleaner.CacheCleaner.scan_categories")
    @patch("confclean.core.cache_cleaner.CacheCleaner.clean_category")
    def test_cli_cache_clean(self, mock_clean_cat, mock_scan_cat):
        cat = CacheCategory(
            category_id="thumbnails",
            name="Thumbnails",
            description="Cached previews",
            requires_root=False,
            paths=["/thumb"],
            size_bytes=1024 * 1024 * 5,
        )
        mock_scan_cat.return_value = [cat]
        mock_clean_cat.return_value = (5 * 1024 * 1024, 10, "Cleaned thumbnails")

        args = argparse.Namespace(
            scan=False,
            clean=True,
            dry_run=False,
            cache=True,
            packages=False,
            restore=None,
            reset_app=None,
            force=True,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("Thumbnails", output)
        self.assertIn("5.00 MB purged", output)

    @patch("confclean.core.cache_cleaner.CacheCleaner.scan_categories")
    @patch("confclean.core.cache_cleaner.CacheCleaner.clean_category")
    def test_cli_cache_clean_default_dry_run(self, mock_clean_cat, mock_scan_cat):
        cat = CacheCategory(
            category_id="thumbnails",
            name="Thumbnails",
            description="Cached previews",
            requires_root=False,
            paths=["/thumb"],
            size_bytes=1024 * 1024 * 5,
        )
        mock_scan_cat.return_value = [cat]
        mock_clean_cat.return_value = (5 * 1024 * 1024, 10, "Simulated thumbnails")

        args = argparse.Namespace(
            scan=False,
            clean=True,
            dry_run=False,
            apply=False,
            cache=True,
            packages=False,
            restore=None,
            reset_app=None,
            force=True,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("[DRY RUN]", output)
        self.assertIn("DRY RUN MODE ENABLED BY DEFAULT", output)
        mock_clean_cat.assert_called_with(cat, dry_run=True)

    @patch("confclean.core.package_manager.PackageManager.scan_all_suggestions")
    def test_cli_packages(self, mock_pkg_scan):
        s = PackageSuggestion(
            name="unused-lib",
            version="1.0",
            release="1",
            arch="x86_64",
            size_bytes=1024 * 1024,
            summary="Unused library",
            category="unneeded_dep",
            reason="Unneeded dependency",
            is_protected=False,
            is_selected=True,
        )
        mock_pkg_scan.return_value = [s]

        args = argparse.Namespace(
            scan=False,
            clean=False,
            dry_run=False,
            cache=False,
            packages=True,
            restore=None,
            reset_app=None,
            force=False,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("unused-lib", output)
        self.assertIn("Suggested Removal Command", output)

    @patch("confclean.core.package_manager.PackageManager.scan_all_suggestions")
    def test_cli_packages_flatpak_and_snap(self, mock_pkg_scan):
        s1 = PackageSuggestion(
            name="org.gnome.Platform//45",
            version="45",
            release="",
            arch="x86_64",
            size_bytes=500 * 1024 * 1024,
            summary="Unused runtime",
            category="flatpak_unused",
            reason="Unused runtime",
            is_protected=False,
            is_selected=True,
        )
        s2 = PackageSuggestion(
            name="core20 (rev 1822)",
            version="rev 1822",
            release="",
            arch="",
            size_bytes=60 * 1024 * 1024,
            summary="Disabled revision",
            category="snap_unused",
            reason="Disabled revision",
            is_protected=False,
            is_selected=True,
        )
        mock_pkg_scan.return_value = [s1, s2]

        args = argparse.Namespace(
            scan=False,
            clean=False,
            dry_run=False,
            cache=False,
            packages=True,
            restore=None,
            reset_app=None,
            force=False,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("org.gnome.Platform//45", output)
        self.assertIn("core20 (rev 1822)", output)
        self.assertIn("flatpak_unused", output)
        self.assertIn("snap_unused", output)
        self.assertIn("Suggested Removal Command", output)

    def test_cli_restore_list(self):
        b = BackupMetadata(
            backup_id="backup_123",
            archive_path="/backups/backup_123.tar.gz",
            log_path="/backups/backup_123.log",
            created_at="2026-10-29",
            user="user",
            item_count=3,
            total_size_bytes=5000,
        )
        self.mock_backup_mgr.list_backups.return_value = [b]

        args = argparse.Namespace(
            scan=False,
            clean=False,
            dry_run=False,
            cache=False,
            packages=False,
            restore="list",
            reset_app=None,
            force=False,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("backup_123", output)

    @patch("confclean.core.app_resetter.AppResetter.discover_reset_profiles")
    @patch("confclean.core.app_resetter.AppResetter.reset_app")
    def test_cli_reset_app(self, mock_reset, mock_discover):
        prof = AppResetProfile(
            app_id="firefox",
            name="Mozilla Firefox",
            description="Browser",
            target_paths=["/home/user/.mozilla/firefox"],
            size_bytes=5000,
        )
        mock_discover.return_value = [prof]
        mock_reset.return_value = (True, "/backups/reset.tar.gz", "Reset success")

        args = argparse.Namespace(
            scan=False,
            clean=False,
            dry_run=False,
            cache=False,
            packages=False,
            restore=None,
            reset_app="firefox",
            force=True,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("Reset success", output)
        self.assertIn("/backups/reset.tar.gz", output)

    @patch("confclean.core.app_resetter.AppResetter.discover_reset_profiles")
    @patch("confclean.core.app_resetter.AppResetter.reset_app")
    def test_cli_reset_app_default_dry_run(self, mock_reset, mock_discover):
        prof = AppResetProfile(
            app_id="firefox",
            name="Mozilla Firefox",
            description="Browser",
            target_paths=["/home/user/.mozilla/firefox"],
            size_bytes=5000,
        )
        mock_discover.return_value = [prof]
        mock_reset.return_value = (True, None, "Would wipe /home/user/.mozilla/firefox")

        args = argparse.Namespace(
            scan=False,
            clean=False,
            dry_run=False,
            apply=False,
            cache=False,
            packages=False,
            restore=None,
            reset_app="firefox",
            force=True,
            no_backup=False,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            output = mock_stdout.getvalue()

        self.assertIn("[DRY RUN]", output)
        self.assertIn("DRY RUN MODE ENABLED BY DEFAULT", output)
        mock_reset.assert_called_with(prof, create_backup=False, dry_run=True)

    @patch("confclean.cli.get_rpm_diff")
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_diff_command(self, mock_stdout, mock_diff):
        mock_diff.return_value = ("/etc/app.conf", "/etc/app.conf.rpmnew", "--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new")
        args = argparse.Namespace(
            scan=False,
            clean=False,
            dry_run=False,
            cache=False,
            packages=False,
            restore=None,
            reset_app=None,
            diff="/etc/app.conf.rpmnew",
            force=False,
        )
        run_cli(
            args,
            scanner=self.mock_scanner,
            cleaner=self.mock_cleaner,
            safety=self.mock_safety,
            backup_mgr=self.mock_backup_mgr,
        )
        out = mock_stdout.getvalue()
        self.assertIn("Configuration Diff", out)
        self.assertIn("/etc/app.conf.rpmnew", out)
        self.assertIn("+new", out)

    def test_cli_symlinks_scan_and_clean(self):
        broken_sym = ScanItem(
            path="/home/user/.local/bin/dead_tool",
            name="dead_tool",
            category="broken_symlink",
            is_directory=False,
            size_bytes=24,
            file_count=1,
            last_modified=1000.0,
            status="CONFIRMED_ORPHAN",
            reason="Broken symlink pointing to non-existent target: '/opt/missing'",
            suggested_action="clean",
            is_selected=True,
        )
        self.mock_scanner.scan_broken_symlinks.return_value = [broken_sym]
        clean_res = CleanResult()
        clean_res.deleted_items = [broken_sym]
        clean_res.is_dry_run = True
        self.mock_cleaner.clean_items.return_value = (clean_res, "Dry run complete: 1 items would be cleaned")

        # 1. Test symlink scan only
        args_scan = argparse.Namespace(
            scan=False,
            clean=False,
            dry_run=False,
            cache=False,
            packages=False,
            symlinks=True,
            restore=None,
            reset_app=None,
            force=False,
            no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args_scan,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            out = mock_stdout.getvalue()

        self.assertIn("dead_tool", out)
        self.assertIn("Broken symlink", out)
        self.assertIn("Discovered 1 broken symbolic link", out)

        # 2. Test symlink clean (dry run by default)
        args_clean = argparse.Namespace(
            scan=False,
            clean=True,
            dry_run=False,
            apply=False,
            cache=False,
            packages=False,
            symlinks=True,
            restore=None,
            reset_app=None,
            force=True,
            no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(
                args_clean,
                scanner=self.mock_scanner,
                cleaner=self.mock_cleaner,
                safety=self.mock_safety,
                backup_mgr=self.mock_backup_mgr,
            )
            out_clean = mock_stdout.getvalue()

        self.assertIn("[DRY RUN]", out_clean)
        self.assertIn("DRY RUN MODE ENABLED BY DEFAULT", out_clean)
        self.mock_cleaner.clean_items.assert_called_with([broken_sym], create_backup=False, dry_run=True)

    def test_cli_retired_scan_and_clean_dry_run(self):
        mock_pkg_mgr = MagicMock()
        ret_pkg = PackageSuggestion(
            name="dead-pkg",
            version="1.0",
            release="1.fc44",
            arch="x86_64",
            size_bytes=1024 * 1024,
            summary="Dead package",
            category="repo_orphan",
            reason="Retired repo orphan",
            is_protected=False,
            is_selected=True,
        )
        mock_pkg_mgr.scan_retired_packages.return_value = [ret_pkg]
        mock_pkg_mgr.get_removal_command.return_value = ["pkexec", "dnf", "remove", "-y", "dead-pkg"]

        # Scan only
        args_scan = argparse.Namespace(
            scan=False, clean=False, dry_run=False, cache=False, packages=False,
            symlinks=False, retired=True, selinux_status=False, selinux_fix_boot=False,
            restore=None, reset_app=None, force=False, no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args_scan, pkg_mgr=mock_pkg_mgr)
            out = mock_stdout.getvalue()

        self.assertIn("dead-pkg", out)
        self.assertIn("Suggested Removal Command:", out)

        # Clean (dry run by default)
        args_clean = argparse.Namespace(
            scan=False, clean=True, dry_run=False, apply=False, cache=False, packages=False,
            symlinks=False, retired=True, selinux_status=False, selinux_fix_boot=False,
            restore=None, reset_app=None, force=False, no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args_clean, pkg_mgr=mock_pkg_mgr)
            out_clean = mock_stdout.getvalue()

        self.assertIn("[DRY RUN]", out_clean)
        self.assertIn("Would remove 1 retired package(s)", out_clean)

    @patch("subprocess.run")
    def test_cli_retired_clean_apply(self, mock_subproc):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        mock_pkg_mgr = MagicMock()
        ret_pkg = PackageSuggestion(
            name="dead-pkg",
            version="1.0",
            release="1.fc44",
            arch="x86_64",
            size_bytes=1024,
            summary="Dead package",
            category="repo_orphan",
            reason="Retired repo orphan",
            is_protected=False,
            is_selected=True,
        )
        mock_pkg_mgr.scan_retired_packages.return_value = [ret_pkg]
        mock_pkg_mgr.get_removal_command.return_value = ["pkexec", "dnf", "remove", "-y", "dead-pkg"]

        args_apply = argparse.Namespace(
            scan=False, clean=True, dry_run=False, apply=True, cache=False, packages=False,
            symlinks=False, retired=True, selinux_status=False, selinux_fix_boot=False,
            restore=None, reset_app=None, force=True, no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args_apply, pkg_mgr=mock_pkg_mgr)
            out = mock_stdout.getvalue()

        self.assertIn("Executing retired package removal", out)
        self.assertIn("Retired package removal completed successfully", out)
        mock_subproc.assert_called_once_with(["pkexec", "dnf", "remove", "-y", "dead-pkg"])

    def test_cli_selinux_status(self):
        mock_selinux = MagicMock()
        mock_selinux.is_selinux_supported.return_value = True
        mock_selinux.get_status.return_value = {
            "mode": "Enforcing",
            "policy": "targeted",
            "autorelabel_scheduled": False,
            "autorelabel_flags": "",
            "fixfiles_path": "/usr/bin/fixfiles",
        }

        args = argparse.Namespace(
            scan=False, clean=False, dry_run=False, cache=False, packages=False,
            symlinks=False, retired=False, selinux_status=True, selinux_fix_boot=False,
            restore=None, reset_app=None, force=False, no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args, selinux_mgr=mock_selinux)
            out = mock_stdout.getvalue()

        self.assertIn("SELinux System Status:", out)
        self.assertIn("Enforcing", out)
        self.assertIn("targeted", out)
        self.assertIn("NOT SCHEDULED", out)

    def test_cli_selinux_fix_boot(self):
        mock_selinux = MagicMock()
        mock_selinux.is_selinux_supported.return_value = True
        mock_selinux.get_status.return_value = {
            "autorelabel_scheduled": False,
            "autorelabel_flags": "",
        }
        mock_selinux.get_schedule_command.return_value = ["/usr/bin/sudo", "/usr/bin/fixfiles", "-B", "onboot"]
        mock_selinux.schedule_onboot_fix.return_value = (True, "SELinux relabel scheduled for next boot")

        args = argparse.Namespace(
            scan=False, clean=False, dry_run=False, cache=False, packages=False,
            symlinks=False, retired=False, selinux_status=False, selinux_fix_boot=True,
            restore=None, reset_app=None, force=True, no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args, selinux_mgr=mock_selinux)
            out = mock_stdout.getvalue()

        self.assertIn("SELinux File Context Relabel on Next Boot:", out)
        self.assertIn("sudo /usr/bin/fixfiles -B onboot", out)
        self.assertIn("SELinux relabel scheduled for next boot", out)
        mock_selinux.schedule_onboot_fix.assert_called_once_with(boottime_only=True, use_sudo=True)

    def test_cli_packages_retired_only_flag(self):
        mock_pkg_mgr = MagicMock()
        ret_pkg = PackageSuggestion(
            name="orphan-app",
            version="2.0",
            release="1.fc44",
            arch="x86_64",
            size_bytes=2048,
            summary="Retired package",
            category="repo_orphan",
            reason="Retired repo orphan",
            is_protected=False,
            is_selected=True,
        )
        mock_pkg_mgr.scan_retired_packages.return_value = [ret_pkg]
        mock_pkg_mgr.get_removal_command.return_value = ["pkexec", "dnf", "remove", "-y", "orphan-app"]

        args = argparse.Namespace(
            scan=False, clean=False, dry_run=False, cache=False, packages=True,
            retired_only=True, clean_cache=False, symlinks_only=False, retired=False, symlinks=False,
            selinux_status=False, selinux_fix_boot=False, restore=None, reset_app=None, force=False, no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args, pkg_mgr=mock_pkg_mgr)
            out = mock_stdout.getvalue()

        self.assertIn("orphan-app", out)
        self.assertIn("--packages --retired-only --clean", out)
        mock_pkg_mgr.scan_retired_packages.assert_called_once()

    def test_cli_scan_symlinks_only_flag(self):
        mock_symlink = ScanItem(
            path="/home/user/.config/broken.lnk",
            name="broken.lnk",
            category="broken_symlink",
            is_directory=False,
            size_bytes=0,
            file_count=1,
            last_modified=10000.0,
            status="CONFIRMED_ORPHAN",
            reason="Broken symlink target missing",
        )
        self.mock_scanner.scan_broken_symlinks.return_value = [mock_symlink]

        args = argparse.Namespace(
            scan=True, symlinks_only=True, clean=False, dry_run=False, cache=False, packages=False,
            retired_only=False, clean_cache=False, retired=False, symlinks=False,
            selinux_status=False, selinux_fix_boot=False, restore=None, reset_app=None, force=False, no_backup=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args, scanner=self.mock_scanner)
            out = mock_stdout.getvalue()

        self.assertIn("broken.lnk", out)
        self.assertIn("Broken symlink target missing", out)
        self.assertIn("--symlinks --clean", out)
        self.mock_scanner.scan_broken_symlinks.assert_called_once()

    @patch("confclean.cli.CacheCleaner")
    def test_cli_packages_clean_cache(self, mock_cc_class):
        mock_cc = MagicMock()
        mock_cc_class.return_value = mock_cc
        cat_dnf = CacheCategory(
            category_id="dnf_cache",
            name="DNF / RPM Package Cache",
            description="Package cache",
            requires_root=True,
            paths=["/var/cache/dnf"],
            size_bytes=50000,
        )
        mock_cc.scan_categories.return_value = [cat_dnf]
        mock_cc.clean_category.return_value = (50000, 5, "Purged DNF cache")

        args = argparse.Namespace(
            scan=False, clean=False, dry_run=False, apply=True, cache=False, packages=True,
            retired_only=False, clean_cache=True, symlinks_only=False, retired=False, symlinks=False,
            selinux_status=False, selinux_fix_boot=False, restore=None, reset_app=None, force=True, no_backup=False,
        )
        mock_pkg_mgr = MagicMock()
        mock_pkg_mgr.scan_all_suggestions.return_value = []

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args, pkg_mgr=mock_pkg_mgr)
            out = mock_stdout.getvalue()

        self.assertIn("Purging DNF / PackageKit cache", out)
        self.assertIn("Purged DNF cache", out)
        mock_cc.clean_category.assert_called_once_with(cat_dnf, dry_run=False)

    def test_cli_safelist_management(self):
        # 1. Add to safelist
        args_add = argparse.Namespace(
            scan=False, clean=False, dry_run=False, cache=False, packages=False,
            safelist_add="miracle-wm", safelist_remove=None, safelist=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args_add, safety=self.mock_safety)
            out = mock_stdout.getvalue()
        self.mock_safety.add_user_whitelist.assert_called_with("miracle-wm")
        self.assertIn("Successfully added 'miracle-wm' to custom protected safelist", out)

        # 2. List safelist
        self.mock_safety.user_whitelist = ["miracle-wm", "/opt/custom_dir", "my_pattern*"]
        args_list = argparse.Namespace(
            scan=False, clean=False, dry_run=False, cache=False, packages=False,
            safelist_add=None, safelist_remove=None, safelist=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args_list, safety=self.mock_safety)
            out = mock_stdout.getvalue()
        self.assertIn("miracle-wm", out)
        self.assertIn("/opt/custom_dir", out)
        self.assertIn("my_pattern*", out)

        # 3. Remove from safelist
        args_rem = argparse.Namespace(
            scan=False, clean=False, dry_run=False, cache=False, packages=False,
            safelist_add=None, safelist_remove="miracle-wm", safelist=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args_rem, safety=self.mock_safety)
            out = mock_stdout.getvalue()
        self.mock_safety.remove_user_whitelist.assert_called_with("miracle-wm")
        self.assertIn("Successfully removed 'miracle-wm' from custom protected safelist", out)

    def test_cli_packages_with_safelist_protection(self):
        s_safe = PackageSuggestion(
            name="retired-kept-app",
            version="1.0",
            release="1.fc44",
            arch="x86_64",
            size_bytes=1000,
            summary="Kept retired app",
            category="repo_orphan",
            reason="PROTECTED: User safelist match: 'retired-kept-app'",
            is_protected=True,
            is_selected=False,
        )
        mock_pkg_mgr = MagicMock()
        mock_pkg_mgr.scan_retired_packages.return_value = [s_safe]
        mock_pkg_mgr.get_removal_command.return_value = []

        args = argparse.Namespace(
            scan=False, clean=True, dry_run=True, apply=False, cache=False, packages=True,
            retired_only=True, clean_cache=False, symlinks_only=False, retired=False, symlinks=False,
            selinux_status=False, selinux_fix_boot=False, restore=None, reset_app=None, force=True, no_backup=False,
            safelist=False, safelist_add=None, safelist_remove=None,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            run_cli(args, pkg_mgr=mock_pkg_mgr, safety=self.mock_safety)
            out = mock_stdout.getvalue()

        self.assertIn("retired-kept-app", out)
        self.assertIn("YES", out)  # Protected column says YES
        self.assertIn("No removable retired package(s) selected", out)


if __name__ == "__main__":
    unittest.main()

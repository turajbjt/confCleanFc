"""
Command Line Interface for ConfClean FC.
Provides powerful terminal-driven scanning, cleaning, package management, and restoration.
"""

import argparse
import os
import sys
from typing import List

from confclean.core.app_resetter import AppResetter
from confclean.core.backup_manager import BackupManager
from confclean.core.cache_cleaner import CacheCleaner
from confclean.core.cleaner import SafeCleaner
from confclean.core.logger import get_logger
from confclean.core.package_manager import PackageManager
from confclean.core.restore_manager import RestoreManager
from confclean.core.safelist import SafetyEngine
from confclean.core.scanner import ConfigScanner, get_rpm_diff


def format_table(rows: List[List[str]], headers: List[str]) -> str:
    """Formats ASCII table with column widths."""
    all_rows = [headers] + rows
    col_widths = [max(len(str(row[i])) for row in all_rows) for i in range(len(headers))]

    header_line = " | ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers)))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))

    data_lines = []
    for r in rows:
        line = " | ".join(f"{str(r[i]):<{col_widths[i]}}" for i in range(len(r)))
        data_lines.append(line)

    return f"{header_line}\n{sep_line}\n" + "\n".join(data_lines)


def run_cli(
    args: argparse.Namespace,
    scanner: ConfigScanner = None,
    cleaner: SafeCleaner = None,
    safety: SafetyEngine = None,
    backup_mgr: BackupManager = None,
):
    """Executes the CLI commands."""
    logger = get_logger()
    safety = safety or SafetyEngine()
    backup_mgr = backup_mgr or BackupManager()
    cleaner = cleaner or SafeCleaner(safety=safety, backup_mgr=backup_mgr)
    scanner = scanner or ConfigScanner(safety=safety)

    # Diff View for .rpmnew / .rpmsave
    if getattr(args, "diff", None):
        target_file = args.diff
        active_p, rpm_p, diff_text = get_rpm_diff(target_file)
        print(f"\nConfiguration Diff: {target_file}")
        print(f"Active File: {active_p or 'None'}")
        print("=" * 60)
        use_color = sys.stdout.isatty()
        for line in diff_text.splitlines():
            if use_color:
                if line.startswith("+++") or line.startswith("---"):
                    print(f"\033[1;30m{line}\033[0m")
                elif line.startswith("@@"):
                    print(f"\033[1;35m{line}\033[0m")
                elif line.startswith("+"):
                    print(f"\033[32m{line}\033[0m")
                elif line.startswith("-"):
                    print(f"\033[31m{line}\033[0m")
                else:
                    print(line)
            else:
                print(line)
        print("=" * 60)
        return

    # 1. Cache Cleaning
    if args.cache:
        cache_cleaner = CacheCleaner(safety=safety)
        categories = cache_cleaner.scan_categories()
        table_rows = []
        for cat in categories:
            table_rows.append([cat.name, cat.formatted_size, "Yes" if cat.requires_root else "No", cat.description[:40]])

        print("\nCache and Junk Categories:\n")
        print(format_table(table_rows, ["Category", "Size", "Root?", "Description"]))

        is_dry_run = getattr(args, "dry_run", False) or (not getattr(args, "apply", False) if hasattr(args, "apply") else False)

        if args.clean:
            if not is_dry_run and not args.force:
                confirm = input("\nClean all accessible cache categories? [y/N]: ")
                if confirm.lower() not in ["y", "yes"]:
                    print("Cancelled.")
                    return
            total_cleaned = 0
            for cat in categories:
                if cat.size_bytes > 0 and (not cat.requires_root or os.geteuid() == 0):
                    reclaimed, count, msg = cache_cleaner.clean_category(cat, dry_run=is_dry_run)
                    total_cleaned += reclaimed
                    if is_dry_run:
                        print(f" - {cat.name}: {reclaimed / (1024*1024):.2f} MB simulated (DRY RUN).")
                    else:
                        print(f" - {cat.name}: {reclaimed / (1024*1024):.2f} MB purged.")
            if is_dry_run:
                print(f"\n[DRY RUN] Total Cache Simulated: {total_cleaned / (1024*1024):.2f} MB")
                print("[DRY RUN MODE ENABLED BY DEFAULT] No files were removed. To perform actual deletion, add --apply.")
            else:
                print(f"\nTotal Cache Reclaimed: {total_cleaned / (1024*1024):.2f} MB")
        return

    # 2. Package Management
    elif args.packages:
        pkg_mgr = PackageManager()
        print("\nQuerying DNF / RPM for unneeded packages and old kernels...")
        suggs = pkg_mgr.scan_all_suggestions()
        if not suggs:
            print("No unneeded packages or removable kernels found.")
            return

        table_rows = []
        for s in suggs:
            table_rows.append([s.name, s.version, s.formatted_size, s.category, "YES" if s.is_protected else "NO"])

        print("\n" + format_table(table_rows, ["Package", "Version", "Size", "Category", "Protected"]))
        removable = [s for s in suggs if not s.is_protected and s.is_selected]
        if removable:
            cmd = pkg_mgr.get_removal_command(removable)
            print(f"\nSuggested Removal Command:\n  {' '.join(cmd)}")
        return

    # 3. Restore Backups
    elif args.restore is not None:
        restore_mgr = RestoreManager()
        backups = backup_mgr.list_backups()
        if not backups:
            print("\nNo backup archives found.")
            return

        if args.restore == "list" or args.restore == "":
            print("\nAvailable Backup Archives:\n")
            table_rows = []
            for b in backups:
                table_rows.append([b.backup_id, b.created_at, b.formatted_size, str(b.item_count), b.archive_path])
            print(format_table(table_rows, ["Backup ID", "Created At", "Size", "Items", "Path"]))
            print("\nTo restore, run: python3 main.py --restore <Backup_ID>")
            return
        else:
            # Look for specific backup ID or path
            target_backup = None
            for b in backups:
                if b.backup_id == args.restore or b.archive_path == args.restore or args.restore in b.backup_id:
                    target_backup = b
                    break
            if not target_backup:
                print(f"Error: Backup '{args.restore}' not found.")
                return

            print(f"\nRestoring backup archive: {target_backup.archive_path}")
            items = restore_mgr.get_archive_items(target_backup.archive_path)
            print(f"Archive contains {len(items)} items.")
            if not args.force:
                confirm = input("Restore all items to their original locations? [y/N]: ")
                if confirm.lower() not in ["y", "yes"]:
                    print("Restore cancelled.")
                    return

            res, summary = restore_mgr.restore(target_backup.archive_path)
            print(f"\n{summary}")
            return

    # 4. Reset App
    elif args.reset_app:
        app_resetter = AppResetter()
        profiles = app_resetter.discover_reset_profiles()
        target_prof = None
        for p in profiles:
            if p.app_id.lower() == args.reset_app.lower() or p.name.lower() == args.reset_app.lower():
                target_prof = p
                break
        if not target_prof:
            print(f"Error: App '{args.reset_app}' not found or has no config.")
            print("Available apps to reset:", ", ".join(p.app_id for p in profiles))
            return

        is_dry_run = getattr(args, "dry_run", False) or (not getattr(args, "apply", False) if hasattr(args, "apply") else False)

        print(f"\nApp Reset Target: {target_prof.name} ({target_prof.formatted_size})")
        print("Paths to be wiped:")
        for path in target_prof.target_paths:
            print(f" - {path}")

        if is_dry_run:
            ok, b_arch, msg = app_resetter.reset_app(target_prof, create_backup=False, dry_run=True)
            print(f"\n[DRY RUN] {msg}")
            print("[DRY RUN MODE ENABLED BY DEFAULT] No files were modified. To perform actual reset, add --apply.")
            return

        if not args.force:
            confirm = input(
                f"\nAre you sure you want to reset '{target_prof.name}' to fresh install defaults? [y/N]: "
            )
            if confirm.lower() not in ["y", "yes"]:
                print("Reset cancelled.")
                return

        ok, b_arch, msg = app_resetter.reset_app(target_prof, create_backup=True, dry_run=False)
        print(f"\n{msg}")
        if b_arch:
            print(f"Safety Backup Created at: {b_arch}")
        return

    # 5. Scan / Clean Orphan Configurations
    elif args.scan or args.clean or args.dry_run:
        print("\nScanning for leftover configurations and orphaned settings...")
        items = scanner.scan_all()
        orphans = [i for i in items if i.status == "CONFIRMED_ORPHAN"]
        probable = [i for i in items if i.status == "PROBABLE_ORPHAN"]

        total_orphan_bytes = sum(i.size_bytes for i in orphans)
        size_mb = total_orphan_bytes / (1024 * 1024)

        table_rows = []
        for it in orphans:
            table_rows.append([it.name, it.category, it.formatted_size, it.formatted_date, it.status])

        if table_rows:
            print("\n" + format_table(table_rows, ["Name", "Category", "Size", "Modified", "Status"]))
            print(f"\nDiscovered {len(orphans)} confirmed orphan items ({size_mb:.2f} MB reclaimable).")
            if probable:
                print(f"Discovered {len(probable)} probable orphans (review in GUI).")
        else:
            print("\nNo orphaned configurations found! Your system is clean.")
            return

        # If only scan requested without clean or dry_run
        if args.scan and not (args.clean or args.dry_run):
            return

        is_dry_run = getattr(args, "dry_run", False) or (not getattr(args, "apply", False) if hasattr(args, "apply") else False)

        if is_dry_run:
            res, summary = cleaner.clean_items(orphans, create_backup=False, dry_run=True)
            print(f"\n[DRY RUN] {summary}")
            print("[DRY RUN MODE ENABLED BY DEFAULT] No files were removed. To perform actual deletion, add --apply.")
            return

        if args.clean:
            if not args.force:
                confirm = input(
                    f"\nAre you sure you want to clean {len(orphans)} items ({size_mb:.2f} MB)? [y/N]: "
                )
                if confirm.lower() not in ["y", "yes"]:
                    print("Clean operation cancelled by user.")
                    return

            create_backup = not args.no_backup
            print(f"\nExecuting cleanup (Backup {'ENABLED' if create_backup else 'DISABLED'})...")
            res, summary = cleaner.clean_items(orphans, create_backup=create_backup, dry_run=False)
            print(f"\n{summary}")
            if res.backup_archive_path:
                print(f"Safety Backup Archive: {res.backup_archive_path}")
            return

    else:
        print("No command specified. Use --help to view available commands, or run without flags for GUI.")

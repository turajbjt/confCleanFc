#!/usr/bin/env python3
"""
ConfClean FC - Fedora & RPM System Cleaner and Orphan Configuration Purger.
Entry point for GUI application and CLI workflows.
"""

import argparse
import os
import sys

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def main():
    parser = argparse.ArgumentParser(
        description="ConfClean FC - Safe, comprehensive configuration cleaner for Fedora and RPM Linux distributions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py                     # Launch graphical interface (default)
  python3 main.py --scan              # Scan and list orphaned configs in terminal
  python3 main.py --clean             # Clean confirmed orphans with pre-backup
  python3 main.py --dry-run           # Simulate orphan cleanup without deletion
  python3 main.py --cache             # List cleanable cache and temporary data
  python3 main.py --packages          # Query DNF for unneeded packages & old kernels
  python3 main.py --restore list      # List all past backup archives
  python3 main.py --restore <ID>      # Restore files from a specific backup
  python3 main.py --reset-app firefox # Reset app settings with automatic backup
        """,
    )

    parser.add_argument("--gui", action="store_true", help="Launch the graphical interface (default)")
    parser.add_argument("--elevated-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scan", action="store_true", help="Scan for orphaned settings and print summary")
    parser.add_argument("--clean", action="store_true", help="Clean detected orphan items (dry run by default unless --apply is passed)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Simulate without deleting files (ENABLED by default)")
    parser.add_argument("--apply", "--no-dry-run", action="store_true", dest="apply", help="Execute actual deletion/changes (disables dry run)")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating backup archive before cleaning")
    parser.add_argument("--cache", action="store_true", help="Scan or clean application and system cache")
    parser.add_argument("--packages", action="store_true", help="Scan for unneeded RPM packages and old kernels")
    parser.add_argument("--restore", nargs="?", const="list", help="List or restore pre-clean backup archives")
    parser.add_argument("--reset-app", metavar="APP", help="Reset an application to factory install defaults (dry run by default unless --apply)")
    parser.add_argument("--diff", metavar="FILE", help="View unified diff between an .rpmnew or .rpmsave file and the active system config")
    parser.add_argument("-f", "--force", action="store_true", help="Skip confirmation prompts in CLI mode")

    args = parser.parse_args()

    # Determine execution mode: CLI or GUI
    cli_flags = [args.scan, args.clean, args.dry_run, args.cache, args.packages, (args.restore is not None), bool(args.reset_app), bool(args.diff)]
    is_cli_requested = any(cli_flags)

    if is_cli_requested and not args.gui:
        from confclean.cli import run_cli
        run_cli(args)
    else:
        # Check display server availability
        has_display = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
        if not has_display:
            if args.gui or args.elevated_child:
                print(
                    "Error: Graphical interface requested, but no WAYLAND_DISPLAY or DISPLAY environment variable was found.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print("No Wayland or X11 display detected. Falling back to CLI mode...")
            from confclean.cli import run_cli
            args.scan = True
            run_cli(args)
            return

        try:
            from confclean.gui.app import run_gui
            run_gui(ready_signal=args.elevated_child)
        except ImportError as e:
            err_msg = (
                "\n"
                "=================================================================\n"
                "[ERROR] Missing GUI Dependency: PyQt6 is required to run the GUI.\n"
                "=================================================================\n"
                f"Details: {e}\n\n"
                "To install the required package on Fedora / RHEL / CentOS / Rocky:\n"
                "  sudo dnf install python3-pyqt6\n\n"
                "Or install via pip:\n"
                "  pip install PyQt6\n\n"
                "Alternatively, you can run ConfClean FC in terminal mode without a GUI:\n"
                "  python3 main.py --scan\n"
                "  python3 main.py --help\n"
                "=================================================================\n"
            )
            print(err_msg, file=sys.stderr)

            # Attempt desktop notification if run from a graphical session
            try:
                import subprocess
                subprocess.run(
                    [
                        "notify-send",
                        "-u", "critical",
                        "ConfClean FC - Missing Dependency",
                        "PyQt6 is required to run the GUI.\nRun: sudo dnf install python3-pyqt6",
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
            sys.exit(1)


if __name__ == "__main__":
    main()

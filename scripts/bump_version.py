#!/usr/bin/env python3
"""
ConfClean FC - Automatic Version Management Script.
Synchronizes SemVer across:
  - confclean/__init__.py
  - pyproject.toml
  - packaging/confclean-fc.spec (%changelog and Version)
  - docs/INSTALLATION.md & README.md
Optionally rebuilds the RPM package immediately.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR) == "scripts" else SCRIPT_DIR


def get_current_version() -> str:
    init_path = os.path.join(ROOT_DIR, "confclean", "__init__.py")
    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not m:
        raise ValueError("Could not find __version__ in confclean/__init__.py")
    return m.group(1)


def parse_semver(version_str: str):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str.strip())
    if not m:
        raise ValueError(f"Invalid SemVer string: {version_str}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def calculate_next_version(current: str, bump_type: str) -> str:
    major, minor, patch = parse_semver(current)
    bump_lower = bump_type.lower()
    if bump_lower == "patch":
        return f"{major}.{minor}.{patch + 1}"
    elif bump_lower == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_lower == "major":
        return f"{major + 1}.0.0"
    else:
        # Assume explicit version
        parse_semver(bump_type)
        return bump_type.strip()


def update_init_py(new_version: str):
    path = os.path.join(ROOT_DIR, "confclean", "__init__.py")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(
        r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        content,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  [✓] Updated confclean/__init__.py -> {new_version}")


def update_pyproject_toml(new_version: str):
    path = os.path.join(ROOT_DIR, "pyproject.toml")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(
        r'version\s*=\s*["\'][^"\']+["\']',
        f'version = "{new_version}"',
        content,
        count=1,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  [✓] Updated pyproject.toml -> {new_version}")


def get_git_author() -> str:
    try:
        name = subprocess.check_output(["git", "config", "user.name"], text=True).strip()
        email = subprocess.check_output(["git", "config", "user.email"], text=True).strip()
        if name and email:
            return f"{name} <{email}>"
    except Exception:
        pass
    return "James Turansky <turajb@plugnpay.com>"


def update_spec_file(new_version: str, changelog_msg: str):
    path = os.path.join(ROOT_DIR, "packaging", "confclean-fc.spec")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Update Version: line
    new_content = re.sub(
        r"^Version:\s*([^\s]+)",
        f"Version:        {new_version}",
        content,
        flags=re.MULTILINE,
    )

    # Format changelog entry
    # Fedora RPM changelog format: * Day Mon DD YYYY Name <email> - Version-Release
    # e.g. * Sun Nov 01 2026 James Turansky <turajb@plugnpay.com> - 1.1.1-1
    now = datetime.datetime.now()
    date_str = now.strftime("%a %b %d %Y")
    author = get_git_author()

    # Format lines of changelog
    lines = [l.strip() for l in changelog_msg.strip().split("\n") if l.strip()]
    formatted_msg_lines = []
    for l in lines:
        if not l.startswith("-"):
            formatted_msg_lines.append(f"- {l}")
        else:
            formatted_msg_lines.append(l)

    bullet_points = "\n".join(formatted_msg_lines)
    new_changelog_entry = f"* {date_str} {author} - {new_version}-1\n{bullet_points}\n\n"

    # Insert right after '%changelog\n'
    changelog_marker = "%changelog\n"
    idx = new_content.find(changelog_marker)
    if idx != -1:
        insert_pos = idx + len(changelog_marker)
        new_content = new_content[:insert_pos] + new_changelog_entry + new_content[insert_pos:]

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  [✓] Updated packaging/confclean-fc.spec -> {new_version}-1 with %changelog")


def update_docs(old_version: str, new_version: str):
    doc_files = [
        os.path.join(ROOT_DIR, "README.md"),
        os.path.join(ROOT_DIR, "docs", "INSTALLATION.md"),
    ]
    for doc_path in doc_files:
        if not os.path.exists(doc_path):
            continue
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()
        new_content = content.replace(f"confclean-fc-{old_version}", f"confclean-fc-{new_version}")
        new_content = new_content.replace(f"release-v{old_version}", f"release-v{new_version}")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  [✓] Updated {os.path.relpath(doc_path, ROOT_DIR)} ({old_version} -> {new_version})")


def main():
    parser = argparse.ArgumentParser(description="Bump ConfClean FC version across all project files.")
    parser.add_argument(
        "bump",
        nargs="?",
        default="patch",
        help="Bump target: 'patch', 'minor', 'major', or an explicit version string (e.g. 1.2.0). Default: patch",
    )
    parser.add_argument(
        "-m", "--message",
        default="",
        help="Changelog bullet point or summary message for this release.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        default=True,
        help="Automatically rebuild the RPM package after bumping version (default: True)",
    )
    parser.add_argument(
        "--no-build",
        action="store_false",
        dest="build",
        help="Skip RPM rebuilding",
    )

    args = parser.parse_args()

    old_ver = get_current_version()
    new_ver = calculate_next_version(old_ver, args.bump)

    print(f"==> Bumping ConfClean FC version: {old_ver} -> {new_ver}")

    changelog = args.message
    if not changelog:
        changelog = f"Maintenance release and stability updates for {new_ver}"

    update_init_py(new_ver)
    update_pyproject_toml(new_ver)
    update_spec_file(new_ver, changelog)
    update_docs(old_ver, new_ver)

    print(f"\n[SUCCESS] Version successfully bumped to {new_ver} across all files.")

    if args.build:
        print("\n==> Rebuilding RPM package...")
        build_script = os.path.join(ROOT_DIR, "packaging", "build-rpm.sh")
        subprocess.check_call(["/usr/bin/env", "bash", build_script])


if __name__ == "__main__":
    main()

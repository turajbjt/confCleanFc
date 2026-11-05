"""
Full unit tests for SafetyEngine.
"""

import json
import os
import shutil
import tempfile
import unittest

from confclean.core.safelist import SafetyEngine


class TestSafetyEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="confclean_safelist_test_")
        self.safety = SafetyEngine(config_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_custom_whitelist_add_remove_save(self):
        self.assertEqual(len(self.safety.user_whitelist), 0)

        # Add items
        self.assertTrue(self.safety.add_user_whitelist("my_custom_app*"))
        self.assertTrue(self.safety.add_user_whitelist("/opt/custom_tool"))
        # Adding duplicate returns False
        self.assertFalse(self.safety.add_user_whitelist("my_custom_app*"))
        self.assertEqual(len(self.safety.user_whitelist), 2)

        # Verify JSON on disk
        self.assertTrue(os.path.isfile(self.safety.whitelist_file))
        with open(self.safety.whitelist_file, "r") as f:
            data = json.load(f)
            self.assertIn("my_custom_app*", data)
            self.assertIn("/opt/custom_tool", data)

        # Test reload in new instance
        new_safety = SafetyEngine(config_dir=self.test_dir)
        self.assertEqual(len(new_safety.user_whitelist), 2)

        # Remove item
        self.assertTrue(self.safety.remove_user_whitelist("my_custom_app*"))
        self.assertFalse(self.safety.remove_user_whitelist("nonexistent"))
        self.assertEqual(len(self.safety.user_whitelist), 1)

    def test_corrupt_whitelist_file_recovery(self):
        with open(self.safety.whitelist_file, "w") as f:
            f.write("{invalid json syntax")

        # Shouldn't raise error
        safety_recovered = SafetyEngine(config_dir=self.test_dir)
        self.assertEqual(len(safety_recovered.user_whitelist), 0)

    def test_protected_root_and_etc_dirs(self):
        for root_p in ["/", "/boot", "/usr", "/lib", "/bin", "/sbin", "/sys", "/dev", "/run"]:
            is_prot, reason = self.safety.is_safelisted(root_p)
            self.assertTrue(is_prot, f"Expected {root_p} to be protected")
            self.assertIn("Critical system root directory", reason)

        for etc_f in ["/etc/passwd", "/etc/shadow", "/etc/fstab", "/etc/sudoers", "/etc/dnf/dnf.conf"]:
            is_prot, reason = self.safety.is_safelisted(etc_f)
            self.assertTrue(is_prot, f"Expected {etc_f} to be protected")
            self.assertIn("Essential system configuration", reason)

    def test_security_and_credentials_keywords(self):
        cases = [
            "/home/user/.ssh",
            "/home/user/.ssh/id_rsa",
            "/home/user/.gnupg",
            "/home/user/.pki",
            "/home/user/.local/share/keyrings",
            "/home/user/.config/secrets.json",
            "/home/user/.crypto_tokens",
            "/home/user/.my_wallet",
            "/home/user/.credentials",
            "/home/user/my_cert.pem",
        ]
        for c in cases:
            is_prot, reason = self.safety.is_safelisted(c)
            self.assertTrue(is_prot, f"Expected {c} to be protected as credential/security")
            self.assertIn("Protected security/credential storage", reason)

    def test_desktop_environments_and_plumbing(self):
        cases = [
            "dconf",
            "gnome-shell",
            "gnome-control-center",
            ".gsd-keyboard.settings-ported",
            "kde4",
            "plasma-org.kde.plasma.desktop-appletsrc",
            "xfce4",
            "cinnamon",
            "mate",
            "pipewire",
            "pulse",
            "pulseaudio",
            "wireplumber",
            "systemd",
            "dbus-1",
            "polkit-1",
            "NetworkManager",
            "gtk-3.0",
            "gtk-4.0",
            "fontconfig",
            "mimeapps.list",
            "user-dirs.dirs",
            "environment.d",
            ".cache",
        ]
        for c in cases:
            is_prot, reason = self.safety.is_safelisted(c)
            self.assertTrue(is_prot, f"Expected {c} to be protected")

    def test_developer_toolchains_protected(self):
        cases = [
            ".git",
            ".gitconfig",
            ".cargo",
            ".rustup",
            ".gradle",
            ".m2",
            ".dotnet",
        ]
        for c in cases:
            is_prot, reason = self.safety.is_safelisted(c)
            self.assertTrue(is_prot, f"Expected {c} to be protected as developer toolchain")

    def test_uninstalled_orphans_allowed(self):
        unprotected_cases = [
            "asunder",
            "cura-lulzbot",
            "skypeforlinux",
            "teams",
            "VirtualBox",
            "bleachbit",
            "filezilla",
            "my_uninstalled_tool",
            "/home/user/.config/asunder",
            "/home/user/.config/cura-lulzbot",
        ]
        for c in unprotected_cases:
            is_prot, reason = self.safety.is_safelisted(c)
            self.assertFalse(is_prot, f"Expected {c} NOT to be protected, but got: {reason}")

    def test_package_safelisting_and_custom_whitelist(self):
        # 1. ConfClean FC core app protected
        is_prot, reason = self.safety.is_package_safelisted("confclean-fc")
        self.assertTrue(is_prot)
        self.assertIn("ConfClean FC core application", reason)

        # 2. Critical system packages protected
        for core_pkg in ["glibc", "systemd", "kernel", "rpm", "dnf", "dnf5", "bash", "coreutils", "selinux-policy"]:
            is_prot, reason = self.safety.is_package_safelisted(core_pkg)
            self.assertTrue(is_prot, f"Expected {core_pkg} to be protected")
            self.assertIn("Core system package", reason)

        # 3. Arbitrary package initially not protected
        is_prot, _ = self.safety.is_package_safelisted("miracle-wm")
        self.assertFalse(is_prot)

        # 4. User adds package to safelist
        self.safety.add_user_whitelist("miracle-wm")
        is_prot, reason = self.safety.is_package_safelisted("miracle-wm")
        self.assertTrue(is_prot)
        self.assertIn("User safelist match", reason)

        # Also matches full NEVRA specifier
        is_prot, reason = self.safety.is_package_safelisted("miracle-wm", "miracle-wm-0.3.0-1.fc44.x86_64")
        self.assertTrue(is_prot)

        # 5. Wildcard pattern for packages
        self.safety.add_user_whitelist("my-retired-*")
        is_prot, reason = self.safety.is_package_safelisted("my-retired-editor")
        self.assertTrue(is_prot)
        self.assertIn("User safelist match", reason)

        # 6. check_core=False ignores core system packages but retains user safelist
        is_prot, _ = self.safety.is_package_safelisted("glibc", check_core=False)
        self.assertFalse(is_prot)
        is_prot, _ = self.safety.is_package_safelisted("miracle-wm", check_core=False)
        self.assertTrue(is_prot)


if __name__ == "__main__":
    unittest.main()

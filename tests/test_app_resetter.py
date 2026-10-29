"""
Comprehensive unit tests for AppResetter and AppResetProfile.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from confclean.core.app_resetter import AppResetProfile, AppResetter
from confclean.core.backup_manager import BackupManager
from confclean.core.detector import SystemDetector
from confclean.core.safelist import SafetyEngine


class TestAppResetter(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="confclean_reset_test_")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.safety = SafetyEngine(config_dir=self.test_dir)
        self.backup_mgr = BackupManager(backup_dir=self.backup_dir)
        self.detector = SystemDetector(refresh_on_init=False)
        self.resetter = AppResetter(
            detector=self.detector,
            backup_mgr=self.backup_mgr,
            safety=self.safety,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_app_reset_profile_properties(self):
        p = AppResetProfile(
            app_id="firefox",
            name="Firefox",
            description="Browser",
            target_paths=["/path1"],
            size_bytes=1024 * 1024 * 50,  # 50 MB
            file_count=20,
            is_installed=True,
        )
        self.assertEqual(p.formatted_size, "50.0 MB")
        self.assertTrue(p.is_installed)

    def test_discover_known_and_flatpak_profiles(self):
        fake_home = os.path.join(self.test_dir, "home")
        fake_firefox = os.path.join(fake_home, ".mozilla", "firefox")
        os.makedirs(fake_firefox, exist_ok=True)
        with open(os.path.join(fake_firefox, "prefs.js"), "w") as f:
            f.write("user_pref();")

        fake_flatpak = os.path.join(fake_home, ".var", "app", "org.test.FlatpakApp")
        os.makedirs(fake_flatpak, exist_ok=True)
        with open(os.path.join(fake_flatpak, "data.bin"), "wb") as f:
            f.write(b"12345")

        with patch("os.path.expanduser", side_effect=lambda p: p.replace("~", fake_home)):
            profiles = self.resetter.discover_reset_profiles()

        self.assertGreater(len(profiles), 0)
        ff_prof = next((p for p in profiles if p.app_id == "firefox"), None)
        self.assertIsNotNone(ff_prof)
        self.assertIn(fake_firefox, ff_prof.target_paths)

        flatpak_prof = next((p for p in profiles if p.app_id == "flatpak_org.test.FlatpakApp"), None)
        self.assertIsNotNone(flatpak_prof)
        self.assertEqual(flatpak_prof.name, "Flatpak: org.test.FlatpakApp")

    def test_reset_refusal_on_safelisted_path(self):
        profile = AppResetProfile(
            app_id="bad_app",
            name="Bad App Targeting Dconf",
            description="Bad",
            target_paths=["/home/user/.config/dconf"],
            size_bytes=100,
        )
        with patch("os.path.exists", return_value=True):
            ok, b_path, msg = self.resetter.reset_app(profile)
            self.assertFalse(ok)
            self.assertIn("Refusing to reset protected system component", msg)

    def test_reset_success_with_backup(self):
        fake_app_dir = os.path.join(self.test_dir, "my_app_config")
        os.makedirs(fake_app_dir, exist_ok=True)
        conf_file = os.path.join(fake_app_dir, "app.cfg")
        with open(conf_file, "w") as f:
            f.write("theme=dark\n")

        profile = AppResetProfile(
            app_id="my_app",
            name="My Application",
            description="App Description",
            target_paths=[fake_app_dir],
            size_bytes=11,
            file_count=1,
            is_installed=True,
        )

        progress_calls = []

        def callback(msg, cur, tot):
            progress_calls.append((msg, cur, tot))

        ok, b_path, msg = self.resetter.reset_app(profile, create_backup=True, dry_run=False, progress_callback=callback)

        self.assertTrue(ok)
        self.assertIsNotNone(b_path)
        self.assertTrue(os.path.exists(b_path))
        self.assertIn("Successfully reset 'My Application'", msg)
        # Original app dir must be wiped
        self.assertFalse(os.path.exists(fake_app_dir))
        self.assertGreater(len(progress_calls), 0)

    def test_reset_app_dry_run_by_default(self):
        fake_app_dir = os.path.join(self.test_dir, "fake_app_dry_run")
        os.makedirs(fake_app_dir, exist_ok=True)
        test_file = os.path.join(fake_app_dir, "settings.json")
        with open(test_file, "w") as f:
            f.write('{"theme": "dark"}')

        profile = AppResetProfile(
            app_id="dry_run_app",
            name="Dry Run Application",
            description="Test app",
            target_paths=[fake_app_dir],
            size_bytes=100,
        )

        ok, b_path, msg = self.resetter.reset_app(profile)  # Defaults to dry_run=True
        self.assertTrue(ok)
        self.assertIsNone(b_path)
        self.assertIn("[DRY RUN]", msg)
        # Path must NOT be deleted in dry run
        self.assertTrue(os.path.exists(test_file))

    def test_reset_empty_target_paths(self):
        profile = AppResetProfile(
            app_id="empty_app",
            name="Empty",
            description="Empty",
            target_paths=[],
        )
        ok, b_path, msg = self.resetter.reset_app(profile)
        self.assertFalse(ok)
        self.assertIn("No configuration paths exist", msg)


if __name__ == "__main__":
    unittest.main()

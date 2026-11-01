"""
Version Consistency Tests for ConfClean FC.
Ensures that the version numbers defined in confclean/__init__.py,
pyproject.toml, packaging/confclean-fc.spec, and documentation remain
strictly synchronized.
"""

import os
import re
import unittest
import confclean

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestVersionConsistency(unittest.TestCase):
    def test_version_format(self):
        ver = confclean.__version__
        self.assertRegex(ver, r"^\d+\.\d+\.\d+$", "Version must follow SemVer (e.g., 1.2.3)")

    def test_pyproject_version_matches(self):
        pyproject_path = os.path.join(ROOT_DIR, "pyproject.toml")
        with open(pyproject_path, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        self.assertIsNotNone(match, "version not found in pyproject.toml")
        self.assertEqual(match.group(1), confclean.__version__, "pyproject.toml version does not match confclean.__version__")

    def test_spec_version_matches(self):
        spec_path = os.path.join(ROOT_DIR, "packaging", "confclean-fc.spec")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.search(r"^Version:\s*([^\s]+)", content, re.MULTILINE)
        self.assertIsNotNone(match, "Version not found in confclean-fc.spec")
        self.assertEqual(match.group(1), confclean.__version__, "confclean-fc.spec Version does not match confclean.__version__")


if __name__ == "__main__":
    unittest.main()

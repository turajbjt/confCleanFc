# Contributing to ConfClean FC 🛡️🤝

Thank you for your interest in contributing to **ConfClean FC**! We welcome bug reports, feature requests, documentation improvements, and code contributions that make Linux configuration cleanup and maintenance safer and more effective.

---

## 🧭 Code of Conduct & Safety Philosophy

ConfClean FC operates on a strict **Safety-First Principle**:
1. **Never break the user's system**: System plumbing (`dconf`, `systemd`, `pipewire`, `polkit`, `wireplumber`), desktop environment settings, and cryptographic credentials (`~/.ssh`, `~/.gnupg`, PKI) must never be targeted or deleted.
2. **Dry Run by default**: Any destructive operation must default to safe simulation unless the user explicitly opts into live execution.
3. **Always backup before modification**: Deletions or application resets must create a valid `.tar.gz` archive with embedded `manifest.json` first.
4. **Preserve running kernels**: The running kernel (`uname -r`) and the primary fallback kernel must always remain protected from removal.

---

## 🛠️ Development Environment Setup

### Prerequisites
* **Operating System**: Fedora Linux 40+, CentOS Stream 9/10, Rocky Linux 9/10, or RHEL 9/10.
* **Python**: Python 3.10+ (tested on Python 3.12, 3.13, 3.14).
* **System Packages**:
  ```bash
  sudo dnf install python3-rpm python3-pyqt6
  ```

### Local Repository Setup
1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/confCleanFc.git
   cd confCleanFc
   ```
2. (Optional) Create and activate a virtual environment with system site packages (needed for `python3-rpm`):
   ```bash
   python3 -m venv --system-site-packages .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

---

## 🧪 Running the Test Suite

ConfClean FC maintains a comprehensive unit test suite covering 100% of core operations. All tests must pass before submitting a pull request.

Run the test suite with:
```bash
python3 -m unittest discover -s tests -v
```

### Running Specific Test Modules:
```bash
python3 -m unittest tests.test_safelist
python3 -m unittest tests.test_cleaner
python3 -m unittest tests.test_cache_cleaner
python3 -m unittest tests.test_app_resetter
python3 -m unittest tests.test_package_manager
python3 -m unittest tests.test_cli
python3 -m unittest tests.test_gui_headless
```

> **Note on GUI Testing**: GUI tests run headlessly using Qt's `offscreen` QPA platform. You do not need a running Wayland or X11 compositor to run the unit tests.

---

## 🧩 Adding New Features

### 1. Adding an Application Reset Profile
Application reset profiles reside in [`confclean/core/app_resetter.py`](file:///home/turajb/cursorProjects/confCleanFc/confclean/core/app_resetter.py) in the `KNOWN_APP_PROFILES` list:

```python
{
    "id": "app_identifier",
    "name": "Human Readable Application Name",
    "desc": "Explanation of what will be reset (preferences, caches, session).",
    "patterns": ["~/.config/app_dir", "~/.cache/app_dir"],
}
```

* Ensure patterns do **not** target user document directories (`~/Documents`, `~/Pictures`, etc.).
* Add a test in [`tests/test_app_resetter.py`](file:///home/turajb/cursorProjects/confCleanFc/tests/test_app_resetter.py).

### 2. Adding a Cache / Junk Category
Cache categories are evaluated in [`confclean/core/cache_cleaner.py`](file:///home/turajb/cursorProjects/confCleanFc/confclean/core/cache_cleaner.py) inside `scan_categories()`:

* User caches should have `requires_root=False`.
* System caches should have `requires_root=True`.
* Always use `_evaluate_category()` or write safe scanner logic that handles missing directories without throwing unhandled exceptions.
* Add corresponding assertions in [`tests/test_cache_cleaner.py`](file:///home/turajb/cursorProjects/confCleanFc/tests/test_cache_cleaner.py).

---

## 📝 Coding Guidelines & Style

* **Python Standard**: Follow PEP 8 guidelines.
* **Typing**: Use comprehensive type annotations (`typing.List`, `typing.Optional`, `typing.Tuple`, `typing.Dict`).
* **Preserve Comments**: Preserve existing docstrings and inline safety explanations.
* **Audit Logging**: Use `get_logger().audit_event(...)` for any system action that modifies, deletes, backs up, or restores files.
* **Defensive File Handling**: Always handle `OSError`, `PermissionError`, and `FileNotFoundError` gracefully.

---

## 🚀 Submitting a Pull Request

1. Create a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Commit your changes with clear, descriptive commit messages.
3. Ensure all 90+ tests pass cleanly (`python3 -m unittest discover -s tests`).
4. Push your branch and open a Pull Request against `master`.

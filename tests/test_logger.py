"""
Full unit tests for AuditLogger.
"""

import os
import shutil
import tempfile
import unittest

from confclean.core.logger import AuditLogger, get_logger


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        AuditLogger.reset_instance()
        self.test_dir = tempfile.mkdtemp(prefix="confclean_log_test_")
        self.logger = AuditLogger(log_dir=self.test_dir)

    def tearDown(self):
        AuditLogger.reset_instance()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_singleton_behavior(self):
        another = get_logger()
        self.assertIs(self.logger, another)

    def test_log_file_creation_and_writing(self):
        self.logger.info("Test informational message")
        self.logger.warning("Test warning message")
        self.logger.error("Test error message")

        self.assertTrue(os.path.isfile(self.logger.log_file))
        with open(self.logger.log_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Test informational message", content)
            self.assertIn("Test warning message", content)
            self.assertIn("Test error message", content)

    def test_listener_dispatch(self):
        events = []

        def listener(ts, lvl, msg):
            events.append((lvl, msg))

        self.logger.add_listener(listener)
        self.logger.info("Hello listener")
        self.logger.warning("Warning listener")

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0], ("INFO", "Hello listener"))
        self.assertEqual(events[1], ("WARNING", "Warning listener"))

        # Test remove listener
        self.logger.remove_listener(listener)
        self.logger.info("Should not be received")
        self.assertEqual(len(events), 2)

    def test_faulty_listener_does_not_break_logger(self):
        def bad_listener(ts, lvl, msg):
            raise RuntimeError("Listener error")

        self.logger.add_listener(bad_listener)
        try:
            self.logger.info("Safe dispatch")
        except Exception:
            self.fail("Logger raised exception due to bad listener")

    def test_audit_event_formatting(self):
        events = []
        self.logger.add_listener(lambda ts, lvl, msg: events.append(msg))

        # Size < 1024 -> bytes
        self.logger.audit_event("TEST_ACT", "/path/to/small", size_bytes=500, status="SUCCESS")
        self.assertIn("500 bytes", events[-1])

        # Size KB
        self.logger.audit_event("TEST_ACT", "/path/to/med", size_bytes=4096, status="SUCCESS")
        self.assertIn("4.00 KB", events[-1])

        # Size MB
        self.logger.audit_event(
            "TEST_ACT",
            "/path/to/large",
            size_bytes=10 * 1024 * 1024,
            status="SUCCESS",
            backup_archive="/backups/test.tar.gz",
            details="Extra detail",
        )
        self.assertIn("10.00 MB", events[-1])
        self.assertIn("Backup: 'test.tar.gz'", events[-1])
        self.assertIn("Note: Extra detail", events[-1])

    def test_get_recent_logs_and_filtering(self):
        self.logger.info("Alpha message")
        self.logger.warning("Beta warning")
        self.logger.error("Gamma critical failure")

        all_logs = self.logger.get_recent_logs()
        self.assertGreaterEqual(len(all_logs), 3)

        # Filter by text
        alpha_logs = self.logger.get_recent_logs(query="alpha")
        self.assertEqual(len(alpha_logs), 1)
        self.assertIn("Alpha message", alpha_logs[0]["message"])

        # Filter by level
        error_logs = self.logger.get_recent_logs(query="error")
        self.assertEqual(len(error_logs), 1)
        self.assertEqual(error_logs[0]["level"], "ERROR")

        # Test limit
        limited = self.logger.get_recent_logs(limit=2)
        self.assertEqual(len(limited), 2)

    def test_in_memory_records_overflow(self):
        # Force fill up to limit
        for i in range(2005):
            self.logger.info(f"Msg {i}")

        self.assertEqual(len(self.logger.in_memory_records), 2000)
        self.assertEqual(self.logger.in_memory_records[-1]["message"], "Msg 2004")


if __name__ == "__main__":
    unittest.main()

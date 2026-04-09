import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from cli import classify_probe_status, get_secret_file_status


class CliStatusHelperTests(unittest.TestCase):
    def test_classify_probe_status_variants(self):
        self.assertEqual(classify_probe_status(True, "key valid")[0], "ok")
        self.assertEqual(classify_probe_status(False, "HTTP 429")[0], "rate_limited")
        self.assertEqual(classify_probe_status(False, "invalid key (401 Unauthorized)")[0], "auth_failed")
        self.assertEqual(classify_probe_status(False, "connection error: timeout")[0], "unreachable")

    def test_get_secret_file_status_reports_permissions_and_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("TOKEN=abc\n")
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            info = get_secret_file_status(path)
            self.assertTrue(info["exists"])
            self.assertEqual(info["permissions_octal"], "600")
            self.assertIn("last_modified", info)
            self.assertTrue(info["last_modified"])


if __name__ == "__main__":
    unittest.main()

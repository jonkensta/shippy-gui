"""Unit tests for miscellaneous utility helpers."""

import os
import unittest
from unittest.mock import patch

from shippy_gui.core.misc import build_tempfile


class BuildTempfileTests(unittest.TestCase):
    """Tests for the tempfile context manager's acquisition and cleanup."""

    def test_removes_the_file_on_the_success_path(self):
        with build_tempfile(suffix=".png") as tmpfile:
            path = tmpfile.name
            self.assertTrue(os.path.exists(path))

        self.assertFalse(os.path.exists(path))

    def test_removes_the_file_when_the_body_raises(self):
        paths = []
        with self.assertRaises(ValueError):
            with build_tempfile(suffix=".png") as tmpfile:
                paths.append(tmpfile.name)
                raise ValueError("body failed")

        self.assertFalse(os.path.exists(paths[0]))

    def test_creation_failure_surfaces_the_real_error(self):
        """Cleanup must not mask why the tempfile could not be created."""
        with patch(
            "shippy_gui.core.misc.tempfile.NamedTemporaryFile",
            side_effect=PermissionError("no write access to temp dir"),
        ):
            with self.assertRaises(PermissionError):
                with build_tempfile(suffix=".png"):
                    self.fail("body must not run when creation fails")


if __name__ == "__main__":
    unittest.main()

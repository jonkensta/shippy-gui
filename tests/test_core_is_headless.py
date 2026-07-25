"""Guard the layering rule that ``core`` never depends on Qt.

Importing any core module must not pull in PySide6. Each module is checked in
its own subprocess, because one Qt-importing module would otherwise hide the
others behind an already-populated ``sys.modules``.
"""

import pkgutil
import subprocess
import sys
import unittest

import shippy_gui.core


def _core_module_names() -> list[str]:
    """Every importable module under shippy_gui.core."""
    return sorted(
        f"shippy_gui.core.{info.name}"
        for info in pkgutil.iter_modules(shippy_gui.core.__path__)
    )


class CoreIsHeadlessTests(unittest.TestCase):
    """Tests that core stays importable without a GUI toolkit."""

    def test_core_package_list_is_not_empty(self):
        self.assertTrue(_core_module_names())

    def test_no_core_module_imports_qt(self):
        offenders = []
        for module_name in ["shippy_gui.core"] + _core_module_names():
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"import sys; import {module_name}; "
                    "sys.exit(1 if any(m.startswith('PySide6') "
                    "for m in sys.modules) else 0)",
                ],
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                offenders.append((module_name, result.stderr.decode().strip()))

        self.assertEqual(
            offenders,
            [],
            "core modules must not import PySide6: "
            + ", ".join(name for name, _ in offenders),
        )


if __name__ == "__main__":
    unittest.main()

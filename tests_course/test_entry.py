"""实际启动课程入口，只复制入口和三个模块，不依赖旧项目代码。"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EntryTests(unittest.TestCase):
    def test_course_files_start_without_advanced_package_or_site_packages(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as temporary:
            folder = Path(temporary)
            shutil.copyfile(ROOT / "demo1.py", folder / "demo1.py")
            shutil.copytree(ROOT / "course_demo", folder / "course_demo",
                            ignore=shutil.ignore_patterns("__pycache__"))
            script = """
import json, runpy, sys, tkinter as tk
real_tk = tk.Tk
opened = []
def automatic_root(*args, **kwargs):
    root = real_tk(*args, **kwargs)
    opened.append(root)
    root.after(150, root.destroy)
    return root
tk.Tk = automatic_root
sys.argv = ['demo1.py', '--data', 'personal.json']
try:
    runpy.run_path('demo1.py', run_name='__main__')
except SystemExit as error:
    assert error.code == 0
assert not any(name.startswith('academic_scheduler') for name in sys.modules)
print(json.dumps({'windows': len(opened)}))
"""
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            process = subprocess.run([sys.executable, "-S", "-B", "-c", script],
                                     cwd=folder, env=env, capture_output=True,
                                     encoding="utf-8", timeout=30)
            self.assertEqual((process.returncode, process.stderr), (0, ""), process.stdout)
            self.assertEqual(json.loads(process.stdout), {"windows": 1})
            self.assertFalse((folder / "personal.json").exists())

    def test_help_is_available_without_creating_workspace(self):
        process = subprocess.run([sys.executable, str(ROOT / "demo1.py"), "--help"],
                                 capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertIn("--data", process.stdout)


if __name__ == "__main__":
    unittest.main()

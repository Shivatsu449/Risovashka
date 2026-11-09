"""Rebuild the Windows executable using the same project sources."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from importlib.metadata import distribution

from tools.make_icon import make_icon


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onedir", action="store_true", help="Build an unpacked application for diagnostics")
    parser.add_argument("--console", action="store_true", help="Keep diagnostics on stderr")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows EXE must be built on Windows.")
    root = Path(__file__).resolve().parent
    make_icon(root / "assets" / "icon.ico")
    licenses = root / "licenses"
    licenses.mkdir(exist_ok=True)
    for package, name in [("PyQt6", "PyQt6-GPL-3.0.txt"), ("PyQt6-Qt6", "Qt-LGPL-3.0.txt"), ("PyQt6-sip", "SIP-LICENSE.txt")]:
        dist = distribution(package)
        candidates = [item for item in dist.files or [] if item.name == "LICENSE" and ".dist-info" in str(item)]
        if not candidates:
            raise RuntimeError(f"License text not found for {package}")
        shutil.copyfile(dist.locate_file(candidates[0]), licenses / name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copyfile(python_license, licenses / "Python-LICENSE.txt")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--onedir" if args.onedir else "--onefile", "--console" if args.console else "--windowed", "--noupx",
               "--name", "LumaPaint", "--icon", str(root / "assets" / "icon.ico"),
               "--add-data", f"{root / 'assets'}:assets",
               "--add-data", f"{licenses}:licenses",
               "--exclude-module", "PyQt6.QtTest", "--exclude-module", "tkinter",
               "--exclude-module", "unittest", "main.py"]
    # Do not let unrelated applications' DLLs on PATH leak into a Qt bundle.
    env = os.environ.copy()
    windows = Path(env.get("SystemRoot", r"C:\Windows"))
    env["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(Path(sys.base_prefix)),
                                    str(windows / "System32"), str(windows)])
    subprocess.run(command, cwd=root, env=env, check=True)
    print("Ready:", root / "dist" / ("LumaPaint/LumaPaint.exe" if args.onedir else "LumaPaint.exe"))


if __name__ == "__main__":
    main()

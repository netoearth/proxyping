#!/usr/bin/env python3
"""
Cross-platform PyInstaller packaging script for ProxyPing Tkinter.
Produces platform-specific release archives in ./dist_release/.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


APP_NAME = "ProxyPing"
PYTHON_APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = PYTHON_APP_DIR.parent
RELEASE_DIR = REPO_ROOT / "dist_release"
BUILD_WORK_DIR = PYTHON_APP_DIR / "build"
BUILD_DIST_DIR = PYTHON_APP_DIR / "dist"


def clean_dirs() -> None:
    for d in (BUILD_WORK_DIR, BUILD_DIST_DIR, RELEASE_DIR):
        if d.exists():
            shutil.rmtree(d)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def run_pyinstaller() -> Path:
    sys_name = platform.system().lower()
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--paths",
        str(PYTHON_APP_DIR),
        "--distpath",
        str(BUILD_DIST_DIR),
        "--workpath",
        str(BUILD_WORK_DIR),
        "--specpath",
        str(BUILD_WORK_DIR),
    ]

    # macOS .app bundle uses --windowed directory; Win/Linux use single-file executable
    if sys_name != "darwin":
        cmd.append("--onefile")

    cmd.append(str(PYTHON_APP_DIR / "proxy_tester.py"))

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    if sys_name == "windows":
        return BUILD_DIST_DIR / f"{APP_NAME}.exe"
    if sys_name == "darwin":
        return BUILD_DIST_DIR / f"{APP_NAME}.app"
    return BUILD_DIST_DIR / APP_NAME


def package_artifact(artifact: Path) -> Path:
    sys_name = platform.system().lower()
    arch = platform.machine().lower()
    if arch in ("x86_64", "amd64"):
        arch_label = "x64"
    elif arch in ("arm64", "aarch64"):
        arch_label = "arm64"
    else:
        arch_label = arch

    if sys_name == "windows":
        out_path = RELEASE_DIR / f"{APP_NAME}-windows-{arch_label}.zip"
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(artifact, arcname=artifact.name)
            zf.write(REPO_ROOT / "README.md", arcname="README.md")
            zf.write(REPO_ROOT / "LICENSE", arcname="LICENSE")
        return out_path

    if sys_name == "darwin":
        out_path = RELEASE_DIR / f"{APP_NAME}-macos-{arch_label}.zip"
        if out_path.exists():
            out_path.unlink()
        subprocess.check_call(
            ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(artifact), str(out_path)]
        )
        return out_path

    out_path = RELEASE_DIR / f"{APP_NAME}-linux-{arch_label}.tar.gz"
    with tarfile.open(out_path, "w:gz") as tf:
        tf.add(artifact, arcname=artifact.name)
        tf.add(REPO_ROOT / "README.md", arcname="README.md")
        tf.add(REPO_ROOT / "LICENSE", arcname="LICENSE")
    return out_path


def package_python_source() -> Path:
    out_path = RELEASE_DIR / f"{APP_NAME}-python-src.zip"
    files = ["proxy_tester.py", "proxy_core.py", "ui_widgets.py", "README.md", "pyproject.toml"]
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in files:
            p = PYTHON_APP_DIR / name
            if p.exists():
                zf.write(p, arcname=f"{APP_NAME}/{name}")
        if (REPO_ROOT / "LICENSE").exists():
            zf.write(REPO_ROOT / "LICENSE", arcname=f"{APP_NAME}/LICENSE")
    return out_path


def main() -> None:
    skip_src = "--skip-src" in sys.argv[1:]
    clean_dirs()
    if not skip_src:
        src_zip = package_python_source()
        print(f"Created source bundle: {src_zip}")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is not installed. Run `pip install pyinstaller` to build native binary.",
            file=sys.stderr,
        )
        sys.exit(1)

    artifact = run_pyinstaller()
    archive = package_artifact(artifact)
    print(f"Created release package: {archive}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Cross-platform PyInstaller packaging script for ProxyPing Tkinter.
Produces platform-specific release archives in ./dist_release/:
  - Windows: ProxyPing-windows-<arch>.zip
  - macOS:   ProxyPing-macos-<arch>.zip
  - Linux:   ProxyPing-linux-<arch>.AppImage (or .tar.gz fallback if appimagetool missing)
"""

from __future__ import annotations

import os
import platform
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile
import zlib
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


def _write_png_icon(dest: Path, size: int = 256) -> None:
    """Generate a clean 256x256 PNG icon using Python stdlib only."""
    cx = cy = (size - 1) / 2.0
    bg = (0x1E, 0x27, 0x32, 0xFF)
    ring_outer = (0x52, 0x88, 0xC1, 0xFF)
    ring_inner = (0x64, 0xB5, 0xF6, 0xFF)
    node_ok = (0x45, 0xB9, 0x7C, 0xFF)
    transparent = (0, 0, 0, 0)

    r_bg = size * 0.46
    r_ring_out_hi = size * 0.34
    r_ring_out_lo = size * 0.29
    r_ring_in_hi = size * 0.22
    r_ring_in_lo = size * 0.17
    r_dot = size * 0.09

    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        dy = y - cy
        for x in range(size):
            dx = x - cx
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > r_bg:
                px = transparent
            elif dist <= r_dot:
                px = node_ok
            elif r_ring_in_lo <= dist <= r_ring_in_hi:
                px = ring_inner
            elif r_ring_out_lo <= dist <= r_ring_out_hi:
                px = ring_outer
            else:
                px = bg
            row.extend(px)
        rows.append(bytes(row))

    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + tag
            + data
            + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, level=9))
        + chunk(b"IEND", b"")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(png)


def run_pyinstaller(onedir: bool = False) -> Path:
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

    # macOS .app bundle and Linux AppImage use directory bundle; Windows/tarball use --onefile
    if not onedir:
        cmd.append("--onefile")

    cmd.append(str(PYTHON_APP_DIR / "proxy_tester.py"))

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    if sys_name == "windows":
        return BUILD_DIST_DIR / f"{APP_NAME}.exe"
    if sys_name == "darwin":
        return BUILD_DIST_DIR / f"{APP_NAME}.app"
    return BUILD_DIST_DIR / APP_NAME


def _find_appimagetool() -> str | None:
    env_tool = os.environ.get("APPIMAGETOOL", "").strip()
    if env_tool and Path(env_tool).is_file():
        return env_tool
    return shutil.which("appimagetool")


def _build_linux_appimage(
    binary_path: Path, arch_label: str, machine_arch: str, require_appimage: bool
) -> Path:
    tool = _find_appimagetool()
    if not tool:
        if require_appimage:
            raise RuntimeError(
                "appimagetool not found (set APPIMAGETOOL or install appimagetool in PATH)."
            )
        print("Warning: appimagetool not found; falling back to .tar.gz archive.", file=sys.stderr)
        out_path = RELEASE_DIR / f"{APP_NAME}-linux-{arch_label}.tar.gz"
        with tarfile.open(out_path, "w:gz") as tf:
            tf.add(binary_path, arcname=binary_path.name)
            tf.add(REPO_ROOT / "README.md", arcname="README.md")
            tf.add(REPO_ROOT / "LICENSE", arcname="LICENSE")
        return out_path

    appdir = BUILD_WORK_DIR / f"{APP_NAME}.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)

    usr_bin = appdir / "usr" / "bin"
    usr_apps = appdir / "usr" / "share" / "applications"
    usr_icons = appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    usr_bin.mkdir(parents=True, exist_ok=True)
    usr_apps.mkdir(parents=True, exist_ok=True)
    usr_icons.mkdir(parents=True, exist_ok=True)

    apprun = appdir / "AppRun"
    if binary_path.is_dir():
        usr_lib = appdir / "usr" / "lib" / "proxyping"
        usr_lib.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(binary_path, usr_lib, symlinks=True)
        (usr_lib / APP_NAME).chmod(0o755)
        bin_wrapper = usr_bin / APP_NAME
        bin_wrapper.write_text(
            f'#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")/../.."\nexec "$HERE/usr/lib/proxyping/{APP_NAME}" "$@"\n',
            encoding="utf-8",
        )
        bin_wrapper.chmod(0o755)
        apprun.write_text(
            f'#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/lib/proxyping/{APP_NAME}" "$@"\n',
            encoding="utf-8",
        )
    else:
        target_bin = usr_bin / APP_NAME
        shutil.copy2(binary_path, target_bin)
        target_bin.chmod(0o755)
        apprun.write_text(
            f'#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/bin/{APP_NAME}" "$@"\n',
            encoding="utf-8",
        )
    apprun.chmod(0o755)

    desktop_content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Cross-platform proxy connectivity and multi-source IP checker\n"
        f"Exec={APP_NAME}\n"
        "Icon=proxyping\n"
        "Categories=Network;\n"
        "Terminal=false\n"
    )
    (appdir / "proxyping.desktop").write_text(desktop_content, encoding="utf-8")
    (usr_apps / "proxyping.desktop").write_text(desktop_content, encoding="utf-8")

    icon_root = appdir / "proxyping.png"
    _write_png_icon(icon_root, size=256)
    shutil.copy2(icon_root, usr_icons / "proxyping.png")

    out_appimage = RELEASE_DIR / f"{APP_NAME}-linux-{arch_label}.AppImage"
    env = os.environ.copy()
    env["ARCH"] = "aarch64" if arch_label == "arm64" else ("x86_64" if arch_label == "x64" else machine_arch)
    env["APPIMAGE_EXTRACT_AND_RUN"] = "1"

    print(f"Building AppImage using {tool} (ARCH={env['ARCH']})...")
    subprocess.check_call([tool, str(appdir), str(out_appimage)], env=env)
    out_appimage.chmod(0o755)
    return out_appimage


def package_artifact(artifact: Path, require_appimage: bool = False) -> Path:
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch_label = "x64"
    elif machine in ("arm64", "aarch64"):
        arch_label = "arm64"
    else:
        arch_label = machine

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

    return _build_linux_appimage(artifact, arch_label, machine, require_appimage=require_appimage)


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
    require_appimage = "--require-appimage" in sys.argv[1:]
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

    sys_name = platform.system().lower()
    use_appimage = sys_name == "linux" and (require_appimage or _find_appimagetool() is not None)
    use_onedir = sys_name == "darwin" or use_appimage

    artifact = run_pyinstaller(onedir=use_onedir)
    archive = package_artifact(artifact, require_appimage=require_appimage)
    print(f"Created release package: {archive}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Patch an .ipa with the ProxyRedirect dylib.

    python3 tools/pack_ipa.py MyApp.ipa
    python3 tools/pack_ipa.py MyApp.ipa --output out/MyApp_proxy.ipa --no-sign

Pipeline: extract to work/ -> add LC_LOAD_DYLIB for ProxyRedirect.dylib ->
ad-hoc sign the .app -> re-zip (symlink-preserving) next to the input.
Requires `make` to have produced out/ProxyRedirect.dylib.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DYLIB = ROOT / "out" / "ProxyRedirect.dylib"

CHUNK = 1 << 20


def die(msg: str) -> None:
    raise SystemExit(f"error: {msg}")


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


class Progress:
    """Single-line byte progress bar, printed only on a TTY (stderr)."""

    REDRAW_EVERY_S = 0.12

    def __init__(self, total: int, desc: str, width: int = 32):
        self.total = max(total, 1)
        self.done = 0
        self.desc = desc
        self.width = width
        self.enabled = sys.stderr.isatty()
        self.last_t = 0.0

    def add(self, n: int) -> None:
        if not self.enabled:
            return
        self.done += n
        now = time.monotonic()
        if self.done >= self.total or now - self.last_t >= Progress.REDRAW_EVERY_S:
            pct = self.done * 100.0 / self.total
            self.last_t = now
            filled = int(self.width * pct / 100)
            bar = "█" * filled + "░" * (self.width - filled)
            sys.stderr.write(
                f"\r{self.desc} [{bar}] {pct:5.1f}% "
                f"({fmt_bytes(self.done)}/{fmt_bytes(self.total)})"
            )
            if self.done >= self.total:
                sys.stderr.write("\n")
            sys.stderr.flush()


def find_main_binary(app: Path) -> Path:
    info = app / "Info.plist"
    if not info.exists():
        die(f"no Info.plist at {info}")
    with info.open("rb") as f:
        plist = plistlib.load(f)
    name = plist.get("CFBundleExecutable")
    if not name:
        die(f"CFBundleExecutable missing in {info}")
    exe = app / name
    if not exe.exists():
        die(f"main binary not found: {exe}")
    return exe


def extract_ipa(ipa: Path, work_root: Path) -> Path:
    work_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ipa) as zf:
        entries = [
            i for i in zf.infolist()
            if not (i.filename.startswith("._") or i.filename.startswith("__MACOSX"))
        ]
        total = sum(i.file_size for i in entries)
        prog = Progress(total, "extracting ipa")
        for info in entries:
            target = (work_root / info.filename).resolve()
            if not target.is_relative_to(work_root.resolve()):
                die(f"unsafe entry in {ipa}: {info.filename}")
            zf.extract(info, work_root)
            prog.add(info.file_size)
    apps = [p for p in (work_root / "Payload").glob("*.app") if p.is_dir()]
    if len(apps) != 1:
        die(f"expected exactly one .app under Payload/, found {len(apps)}")
    print(f"extracted {ipa} -> {apps[0]}")
    return apps[0]


def inject_dylib(app: Path, dylib: Path, main_binary: Path) -> None:
    dst = app / dylib.name
    if dst.exists():
        dst.unlink()
    shutil.copy2(dylib, dst)
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "insert_load_dylib.py"),
         str(main_binary), f"@executable_path/{dylib.name}"],
        check=True,
    )


def sign(app: Path) -> None:
    print(f"codesigning {app} (no progress; can take a while) ...", end="", flush=True)
    subprocess.run(
        ["codesign", "--force", "--sign", "-", "--timestamp=none", str(app)],
        check=True,
    )
    print(" done")


def zip_payload(work_root: Path, out_ipa: Path) -> None:
    payload = work_root / "Payload"
    if not payload.is_dir():
        die(f"missing Payload under {work_root}")
    out_ipa.parent.mkdir(parents=True, exist_ok=True)
    if out_ipa.exists():
        out_ipa.unlink()

    symlinks, files, total = [], [], 0
    for path in payload.rglob("*"):
        if path.name.startswith("._"):
            continue
        rel = path.relative_to(work_root).as_posix()
        if path.is_symlink():
            symlinks.append((rel, os.readlink(path)))
        elif path.is_file():
            files.append((path, rel, path.stat().st_size))
            total += path.stat().st_size

    prog = Progress(total, "zipping ipa")
    with zipfile.ZipFile(out_ipa, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, target in symlinks:
            info = zipfile.ZipInfo(rel)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o755) << 16
            zf.writestr(info, target)
        for path, rel, size in files:
            info = zipfile.ZipInfo.from_file(path, rel)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            with zf.open(info, "w") as out:
                with open(path, "rb") as src:
                    while True:
                        chunk = src.read(CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        prog.add(len(chunk))
    prog.add(prog.total)
    print(f"wrote {out_ipa} ({out_ipa.stat().st_size} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ipa", type=Path, help="path to the .ipa to patch")
    ap.add_argument("--output", type=Path, default=None,
                    help="output path (default: <name>_proxy.ipa next to input)")
    ap.add_argument("--dylib", type=Path, default=DEFAULT_DYLIB,
                    help=f"built loader dylib (default: {DEFAULT_DYLIB.relative_to(ROOT)})")
    ap.add_argument("--no-sign", action="store_true",
                    help="skip ad-hoc codesigning of the .app")
    args = ap.parse_args()

    ipa = args.ipa
    if not ipa.is_file():
        die(f"{ipa} is not a file")
    if not args.dylib.is_file():
        die(f"{args.dylib} missing — run `make` first")

    work_root = ROOT / "work" / ipa.stem
    if work_root.exists():
        shutil.rmtree(work_root)
    app = extract_ipa(ipa, work_root)
    inject_dylib(app, args.dylib, find_main_binary(app))
    if not args.no_sign:
        sign(app)
    out = args.output if args.output is not None \
        else ipa.with_name(f"{ipa.stem}_proxy.ipa")
    zip_payload(work_root, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

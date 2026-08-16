#!/usr/bin/env python3
"""Insert an LC_LOAD_DYLIB command into a thin arm64 Mach-O binary.

Usage:
  insert_load_dylib.py <macho> @executable_path/ProxyRedirect.dylib
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_CODE_SIGNATURE = 0x1D
LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x18
LC_REEXPORT_DYLIB = 0x1F
LC_LOAD_UPWARD_DYLIB = 0x23
LC_LAZY_LOAD_DYLIB = 0x20

DYLIB_CMDS = {
    LC_LOAD_DYLIB,
    LC_LOAD_WEAK_DYLIB,
    LC_REEXPORT_DYLIB,
    LC_LOAD_UPWARD_DYLIB,
    LC_LAZY_LOAD_DYLIB,
}


def align(n: int, a: int = 8) -> int:
    return (n + a - 1) & ~(a - 1)


def first_section_file_offset(data: bytes, ncmds: int) -> int:
    """Lowest positive section offset (usually __TEXT,__text)."""
    offset = 32
    best = None
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, offset)
        if cmd == LC_SEGMENT_64 and cmdsize >= 72:
            nsects = struct.unpack_from("<I", data, offset + 64)[0]
            sect = offset + 72
            for _s in range(nsects):
                soff = struct.unpack_from("<I", data, sect + 48)[0]
                if soff > 0:
                    best = soff if best is None else min(best, soff)
                sect += 80
        offset += cmdsize
    if best is None:
        raise SystemExit("no Mach-O sections with positive file offset")
    return best


def dylib_name_at(cmds: bytes, offset: int, cmdsize: int) -> bytes:
    name_off = struct.unpack_from("<I", cmds, offset + 8)[0]
    start = offset + name_off
    end = cmds.find(b"\x00", start, offset + cmdsize)
    if end < 0:
        end = offset + cmdsize
    return cmds[start:end]


def insert(path: Path, dylib: str) -> None:
    data = bytearray(path.read_bytes())
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != MH_MAGIC_64:
        raise SystemExit(f"unsupported magic {magic:#x} (need thin arm64 MH_MAGIC_64)")

    cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags = struct.unpack_from(
        "<IIIIII", data, 4
    )
    header_size = 32
    cmds_start = header_size
    cmds_end = header_size + sizeofcmds
    old_cmds = bytes(data[cmds_start:cmds_end])
    content_off = first_section_file_offset(data, ncmds)

    rebuilt = bytearray()
    removed = 0
    offset = 0
    needle = dylib.encode("utf-8")
    already = False
    while offset + 8 <= len(old_cmds):
        cmd, cmdsize = struct.unpack_from("<II", old_cmds, offset)
        if cmdsize < 8 or offset + cmdsize > len(old_cmds):
            raise SystemExit("corrupt load commands")
        blob = old_cmds[offset : offset + cmdsize]
        if cmd == LC_CODE_SIGNATURE:
            removed += 1
        else:
            if cmd in DYLIB_CMDS and dylib_name_at(old_cmds, offset, cmdsize) == needle:
                already = True
            rebuilt.extend(blob)
        offset += cmdsize

    if not already:
        name_offset = 24
        name_bytes = dylib.encode("utf-8") + b"\x00"
        cmdsize = align(name_offset + len(name_bytes), 8)
        pad = cmdsize - (name_offset + len(name_bytes))
        load_cmd = struct.pack(
            "<IIIIII",
            LC_LOAD_DYLIB,
            cmdsize,
            name_offset,
            0,
            0x10000,
            0x10000,
        )
        load_cmd += name_bytes + (b"\x00" * pad)
        rebuilt.extend(load_cmd)

    new_ncmds = (ncmds - removed) + (0 if already else 1)
    new_sizeofcmds = len(rebuilt)
    if header_size + new_sizeofcmds > content_off:
        raise SystemExit(
            f"not enough header space: need {header_size + new_sizeofcmds}, "
            f"first section at {content_off}.\n"
            "Rebuild the binary with spare header space, e.g. add "
            "-Wl,-headerpad,0x1000 to the final link, then retry."
        )

    out = bytearray()
    out += struct.pack(
        "<IIIIIIII",
        MH_MAGIC_64,
        cputype,
        cpusubtype,
        filetype,
        new_ncmds,
        new_sizeofcmds,
        flags,
        0,
    )
    out += rebuilt
    out.extend(b"\x00" * (content_off - len(out)))
    out += data[content_off:]
    path.write_bytes(out)

    action = "kept" if already else "inserted"
    print(
        f"{action} {dylib} in {path} "
        f"(ncmds {ncmds}->{new_ncmds}, sizeofcmds {sizeofcmds}->{new_sizeofcmds}, "
        f"stripped_sig={removed})"
    )


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    insert(Path(sys.argv[1]), sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

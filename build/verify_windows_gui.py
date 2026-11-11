"""Validate the built Windows EXE uses GUI subsystem, not Console."""
from pathlib import Path
import struct
import sys


def subsystem(path: Path) -> int:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise RuntimeError(f"Not a PE executable: {path}")
        stream.seek(0x3C)
        pe_offset, = struct.unpack("<I", stream.read(4))
        stream.seek(pe_offset)
        if stream.read(4) != bytes((80, 69, 0, 0)):
            raise RuntimeError(f"Invalid PE signature: {path}")
        # PE signature (4) + COFF (20) + optional-header Subsystem field (68)
        stream.seek(pe_offset + 4 + 20 + 68)
        value, = struct.unpack("<H", stream.read(2))
        return value


if __name__ == "__main__":
    exe = Path(sys.argv[1])
    value = subsystem(exe)
    if value != 2:
        raise SystemExit(f"FAIL: {exe} uses subsystem {value}; expected Windows GUI (2)")
    print(f"PASS: {exe} is a native Windows GUI executable (subsystem {value})")

"""Conservative header-based ROM/disc identification; never executes or moves images."""
from __future__ import annotations

from pathlib import Path
from typing import Any


GB_LOGO = bytes.fromhex(
    "CE ED 66 66 CC 0D 00 0B 03 73 00 83 00 0C 00 0D 00 08 11 "
    "1F 88 89 00 0E DC CC 6E E6 DD DD D9 99 BB BB 67 63 6E 0E "
    "EC CC DD DC 99 9F BB B9 33 3E"
)

EMULATORS = {
    "Xbox 360": ["Xenia"],
    "Wii": ["Dolphin"],
    "Game Boy / Game Boy Color": ["SameBoy", "RetroArch"],
    "Game Boy Advance": ["mGBA", "RetroArch"],
    "Nintendo 64": ["Mupen64Plus", "RetroArch"],
    "Nintendo Entertainment System": ["Mesen", "RetroArch"],
    "PlayStation Portable": ["PPSSPP"],
    "Nintendo 3DS": ["Azahar"],
    "Nintendo Switch": ["Ryujinx", "Sudachi"],
    "Dreamcast": ["Flycast"],
}


def identify_rom(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    extension = path.suffix.casefold()
    try:
        size = path.stat().st_size
        if not path.is_file() or size < 4 or size > 200 * 1024**3:
            return {"identified": False, "format": extension.lstrip("."), "platform": "", "evidence": "Invalid or unsupported file size"}
        with path.open("rb") as stream:
            header = stream.read(0x200)
    except OSError:
        return {"identified": False, "format": extension.lstrip("."), "platform": "", "evidence": "File is unavailable"}

    platform = ""
    evidence = ""
    if extension == ".xex" and header.startswith(b"XEX2"):
        platform, evidence = "Xbox 360", "XEX2 executable header"
    elif extension == ".wbfs" and header.startswith(b"WBFS"):
        platform, evidence = "Wii", "WBFS disc header"
    elif extension == ".rvz" and header.startswith(b"RVZ"):
        platform, evidence = "Wii", "Dolphin RVZ container header"
    elif extension == ".cso" and header.startswith(b"CISO"):
        platform, evidence = "PlayStation Portable", "CISO compressed-disc header"
    elif extension == ".nes" and header.startswith(b"NES\x1a"):
        platform, evidence = "Nintendo Entertainment System", "iNES/NES 2.0 header"
    elif extension in (".z64", ".v64", ".n64") and header[:4] in (
        bytes.fromhex("80 37 12 40"), bytes.fromhex("37 80 40 12"), bytes.fromhex("40 12 37 80")
    ):
        platform, evidence = "Nintendo 64", "Recognized N64 byte-order signature"
    elif extension in (".gb", ".gbc") and len(header) >= 0x134 and header[0x104:0x134] == GB_LOGO:
        platform, evidence = "Game Boy / Game Boy Color", "Nintendo cartridge logo header"
    elif extension == ".3ds" and len(header) >= 0x104 and header[0x100:0x104] == b"NCSD":
        platform, evidence = "Nintendo 3DS", "NCSD cartridge image header"
    elif extension == ".nsp" and header.startswith(b"PFS0"):
        platform, evidence = "Nintendo Switch", "PFS0 package header"
    elif extension == ".gdi":
        try:
            first = header.decode("ascii", "strict").splitlines()[0].strip()
            if first.isdigit() and 1 <= int(first) <= 99:
                platform, evidence = "Dreamcast", "GDI track table"
        except (UnicodeError, IndexError, ValueError):
            pass
    elif extension == ".chd" and header.startswith(b"MComprHD"):
        evidence = "CHD compressed-disc container; console is not encoded in the header"
    elif extension in (".iso", ".cue", ".bin", ".img"):
        evidence = "Generic optical-disc image; platform requires filesystem/header inspection"

    return {
        "identified": bool(platform),
        "format": extension.lstrip("."),
        "platform": platform,
        "evidence": evidence or "No recognized platform signature",
        "recommendedEmulators": EMULATORS.get(platform, []),
        "reviewRequired": True,
    }


def summarize_roms(paths: list[str | Path]) -> dict[str, Any]:
    results = [identify_rom(path) for path in paths[:16]]
    platforms = sorted({item["platform"] for item in results if item["platform"]})
    if len(platforms) == 1:
        platform = platforms[0]
        return {
            "platform": platform,
            "emulators": EMULATORS.get(platform, []),
            "identified": sum(1 for item in results if item["identified"]),
            "total": len(results),
            "reason": f"{platform} format evidence; suggested emulator(s): {', '.join(EMULATORS.get(platform, []))}. Manual review required.",
        }
    if len(platforms) > 1:
        return {"platform": "Mixed/unknown", "emulators": [], "identified": len(platforms),
                "total": len(results), "reason": "Mixed ROM platforms detected; each image needs manual mapping."}
    return {"platform": "Unknown", "emulators": [], "identified": 0, "total": len(results),
            "reason": "Disc/ROM image found, but its platform could not be established from the available header."}

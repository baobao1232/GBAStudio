from pathlib import Path
import hashlib

class GbaRom:
    HEADER_SIZE = 0xC0

    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        if len(self.data) < self.HEADER_SIZE:
            raise ValueError("File is smaller than a valid GBA header.")
        self.sha256 = hashlib.sha256(self.data).hexdigest()

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError(f"Read outside ROM: offset={offset:#x}, size={size:#x}")
        return self.data[offset:offset + size]

    def header_info(self):
        h = self.data[:self.HEADER_SIZE]
        game_code = h[0xAC:0xB0].decode("ascii", "replace")
        known = {
            "BFGE": "Harvest Moon: More Friends of Mineral Town",
            "BPRE": "Pokémon FireRed (USA)",
            "BPGE": "Pokémon LeafGreen (USA)",
            "AXVE": "Pokémon Ruby (USA)",
            "AXPE": "Pokémon Sapphire (USA)",
            "BPEE": "Pokémon Emerald (USA)",
        }
        title = h[0xA0:0xAC].split(b"\0", 1)[0].decode("ascii", "replace").strip()
        detected_game = known.get(game_code, f"Unknown / chưa có profile: {title or 'GBA ROM'}")
        return {
            "file": self.path.name,
            "path": str(self.path),
            "size_bytes": len(self.data),
            "size_mib": round(len(self.data) / (1024 * 1024), 3),
            "title": title,
            "game_code": game_code,
            "detected_game": detected_game,
            "maker_code": h[0xB0:0xB2].decode("ascii", "replace"),
            "header_complement": f"0x{h[0xBD]:02X}",
            "fixed_value": f"0x{h[0xB2]:02X}",
            "unit_code": h[0xB3],
            "device_type": f"0x{h[0xB4]:02X}",
            "software_version": h[0xBC],
            "header_checksum_valid": ((-sum(h[0xA0:0xBD]) - 0x19) & 0xFF) == h[0xBD],
            "sha256": self.sha256,
        }

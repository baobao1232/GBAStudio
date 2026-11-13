"""Portable community profiles and signature-assisted discovery.

Profiles are intentionally transparent JSON rules. A profile signature is an
exact byte sequence sampled from a user-selected binary candidate; matches are
reported as candidates and never silently promoted to confirmed assets.
"""
from __future__ import annotations
import hashlib, json, re, shutil
from pathlib import Path
from datetime import datetime, timezone

SCHEMA = "gba-studio-profile-v1"
MAX_PROFILE_BYTES = 4096
MAX_SIGNATURE_BYTES = 256


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return slug[:64] or "game_profile"


def build_profile(sample_path, name, asset_type, game_code="", game_title="", tags=None):
    path = Path(sample_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size < 16:
        raise ValueError("Mẫu phải có ít nhất 16 byte")
    if size > MAX_PROFILE_BYTES and path.suffix.lower() not in {".bin", ".dat", ".gba", ".rom"}:
        raise ValueError("Chỉ dùng file nhị phân làm mẫu profile")
    with path.open("rb") as stream:
        signature = stream.read(MAX_SIGNATURE_BYTES)
    if len(signature) < 16:
        raise ValueError("Chữ ký mẫu quá ngắn")
    return {
        "schema": SCHEMA,
        "name": name.strip(),
        "asset_type": asset_type.strip().lower(),
        "game_code": game_code.strip().upper()[:4],
        "game_title": game_title.strip(),
        "tags": list(tags or []),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample": {"filename": path.name, "size": size,
                   "signature_hex": signature.hex(),
                   "signature_sha256": hashlib.sha256(signature).hexdigest(),
                   "signature_length": len(signature)},
        "matching": {"mode": "exact_signature", "min_rom_offset": 0,
                     "max_matches": 1000},
        "limitations": ["Exact signature matching only; not semantic decoding.",
                        "A decompressed candidate may not occur verbatim in the original ROM.",
                        "Review every match before treating it as a confirmed asset."]
    }


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get("schema") != SCHEMA:
        raise ValueError("Sai schema profile hoặc phiên bản không hỗ trợ")
    for key in ("name", "asset_type", "sample", "matching"):
        if key not in profile:
            raise ValueError(f"Profile thiếu trường: {key}")
    try:
        signature = bytes.fromhex(profile["sample"]["signature_hex"])
    except Exception as exc:
        raise ValueError("signature_hex không hợp lệ") from exc
    if not 16 <= len(signature) <= MAX_SIGNATURE_BYTES:
        raise ValueError("Độ dài chữ ký profile không hợp lệ")
    if hashlib.sha256(signature).hexdigest() != profile["sample"].get("signature_sha256"):
        raise ValueError("Chữ ký profile không khớp checksum")
    return profile


def save_profile(profile, folder):
    validate_profile(profile)
    root = Path(folder); root.mkdir(parents=True, exist_ok=True)
    target = root / (_safe_slug(profile["name"]) + ".gbaprofile.json")
    if target.exists():
        stem = target.stem; n = 2
        while (root / f"{stem}_{n}.json").exists(): n += 1
        target = root / f"{stem}_{n}.json"
    target.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_profile(path):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_profile(profile)


def import_profile(path, library_folder):
    profile = load_profile(path)
    return save_profile(profile, library_folder)


def export_profile(profile_path, destination):
    profile = load_profile(profile_path)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def list_profiles(folder):
    root = Path(folder)
    if not root.exists(): return []
    found = []
    for path in sorted(root.glob("*.json")):
        try:
            profile = load_profile(path)
            found.append({"path": path, "name": profile["name"],
                          "asset_type": profile["asset_type"], "game_code": profile.get("game_code", "")})
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return found


def scan_rom_with_profile(rom_data: bytes, profile: dict, game_code=""):
    validate_profile(profile)
    expected = profile.get("game_code", "").upper()
    if expected and game_code and expected != game_code.upper():
        return []
    sig = bytes.fromhex(profile["sample"]["signature_hex"])
    start = max(0, int(profile.get("matching", {}).get("min_rom_offset", 0)))
    limit = max(1, min(10000, int(profile.get("matching", {}).get("max_matches", 1000))))
    results = []; pos = start
    while len(results) < limit:
        pos = rom_data.find(sig, pos)
        if pos < 0: break
        results.append({"offset": pos, "length": len(sig), "asset_type": profile["asset_type"],
                        "profile": profile["name"], "confidence": "exact_signature_candidate"})
        pos += 1
    return results


def scan_all_profiles(rom_data, profile_folder, game_code=""):
    results = []
    for item in list_profiles(profile_folder):
        profile = load_profile(item["path"])
        for match in scan_rom_with_profile(rom_data, profile, game_code):
            match["profile_file"] = item["path"].name
            results.append(match)
    return results

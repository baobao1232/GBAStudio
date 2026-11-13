"""Heuristic graphics and palette candidate discovery for GBA ROMs."""
from collections import Counter
from .graphics import decode_tiles, decode_palette


def _entropy_score(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    import math
    return -sum((c/n) * math.log2(c/n) for c in counts.values())


def _tile_score(raw: bytes, bpp: int) -> tuple[float, dict]:
    tiles = decode_tiles(raw, bpp)
    flat = [p for tile in tiles for p in tile]
    unique = len(set(flat))
    nonzero = sum(v != 0 for v in flat) / max(1, len(flat))
    tile_signatures = len({bytes(tile) for tile in tiles})
    diversity = tile_signatures / max(1, len(tiles))
    # Graphics tend to use a subset of the index range, with repeated but non-identical tiles.
    score = min(unique / (16 if bpp == 4 else 64), 1.0) * 35
    score += min(nonzero / 0.45, 1.0) * 25
    score += min(diversity / 0.7, 1.0) * 25
    score += min(_entropy_score(raw) / 6.0, 1.0) * 15
    return round(score, 2), {
        "unique_indices": unique,
        "nonzero_ratio": round(nonzero, 3),
        "unique_tiles": tile_signatures,
        "tile_count": len(tiles),
    }


def scan_graphics(data: bytes, bpp: int = 4, block_size: int = 0x400,
                  step: int = 0x100, max_results: int = 500, progress_callback=None) -> list[dict]:
    if bpp not in (4, 8):
        raise ValueError("BPP must be 4 or 8")
    unit = 32 if bpp == 4 else 64
    block_size = max(unit * 4, (block_size // unit) * unit)
    step = max(unit, (step // unit) * unit)
    results = []
    end = len(data) - block_size
    offsets = range(0, max(0, end) + 1, step)
    total = max(1, len(offsets))
    for index, offset in enumerate(offsets):
        raw = data[offset:offset + block_size]
        score, stats = _tile_score(raw, bpp)
        if score >= 35:
            results.append({"offset": offset, "offset_hex": f"0x{offset:08X}",
                            "size": block_size, "size_hex": f"0x{block_size:X}",
                            "bpp": bpp, "score": score, **stats})
        if progress_callback and (index % 64 == 0 or index + 1 == total):
            progress_callback(index + 1, total)
    results.sort(key=lambda x: (-x["score"], x["offset"]))
    return results[:max_results]


def scan_palettes(data: bytes, max_results: int = 200, progress_callback=None, step: int = 32) -> list[dict]:
    """Find aligned 16-color BGR555 palette-like blocks; heuristic only."""
    results = []
    step = max(2, int(step))
    offsets = range(0, len(data) - 32, step)
    total = max(1, len(offsets))
    for index, offset in enumerate(offsets):
        raw = data[offset:offset + 32]
        colors = decode_palette(raw)
        unique = len(set(colors))
        nonblack = sum(c != (0, 0, 0) for c in colors)
        # Palette blocks usually contain repeated colors and varied RGB values.
        channel_spread = sum(max(c[i] for c in colors) - min(c[i] for c in colors) for i in range(3))
        score = min(unique / 12, 1) * 50 + min(nonblack / 12, 1) * 20 + min(channel_spread / 765, 1) * 30
        if score >= 45:
            results.append({"offset": offset, "offset_hex": f"0x{offset:08X}",
                            "score": round(score, 2), "unique_colors": unique,
                            "nonblack_colors": nonblack})
        if progress_callback and (index % 256 == 0 or index + 1 == total):
            progress_callback(index + 1, total)
    results.sort(key=lambda x: (-x["score"], x["offset"]))
    # Nearby overlapping candidates are redundant; keep the strongest in each 32-byte neighborhood.
    filtered = []
    for item in results:
        if all(abs(item["offset"] - old["offset"]) >= 32 for old in filtered):
            filtered.append(item)
            if len(filtered) >= max_results:
                break
    return filtered

"""Heuristic extractors for generic GBA text, map and audio data.

These scanners export candidates and preserve source offsets. They do not claim
that every candidate is a confirmed in-game resource; game-specific encodings
still require a profile.
"""
from __future__ import annotations
import csv
import math
import struct
import wave
from pathlib import Path


def _printable_ascii_run(data: bytes, start: int, min_len: int = 4):
    i = start
    while i < len(data) and 0x20 <= data[i] <= 0x7E:
        i += 1
    return data[start:i] if i - start >= min_len else b""


def extract_text_candidates(data: bytes, out_dir: Path, max_strings: int = 12000):
    folder = out_dir / "Text"
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    i = 0
    while i < len(data) and len(rows) < max_strings:
        if 0x20 <= data[i] <= 0x7E:
            raw = _printable_ascii_run(data, i)
            if raw:
                text = raw.decode("ascii")
                if any(ch.isalpha() for ch in text):
                    rows.append({"offset": i, "encoding": "ASCII", "text": text})
                i += len(raw)
        i += 1
    # UTF-16LE strings are common in some homebrew / converted titles, but not
    # the standard encoding used by most commercial GBA games.
    i = 0
    while i + 8 <= len(data) and len(rows) < max_strings:
        if data[i] >= 0x20 and data[i] <= 0x7E and data[i + 1] == 0:
            j = i
            chars = []
            while j + 1 < len(data) and 0x20 <= data[j] <= 0x7E and data[j + 1] == 0:
                chars.append(chr(data[j])); j += 2
            if len(chars) >= 4 and any(c.isalpha() for c in chars):
                rows.append({"offset": i, "encoding": "UTF-16LE", "text": "".join(chars)})
                i = j
        i += 2
    rows.sort(key=lambda x: x["offset"])
    with (folder / "text_strings.txt").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"[0x{r['offset']:08X}] [{r['encoding']}] {r['text']}\n")
    with (folder / "text_strings.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["offset", "encoding", "text"]); w.writeheader()
        for r in rows: w.writerow({**r, "offset": f"0x{r['offset']:08X}"})
    return len(rows)


def _map_score(block: bytes):
    words = struct.unpack("<" + "H" * (len(block)//2), block)
    low = [v & 0x03FF for v in words]
    nonzero = sum(v != 0 for v in low) / len(low)
    unique = len(set(low))
    # Tilemap chunks tend to reuse a modest set of tile IDs. This is a
    # heuristic and deliberately rejects very sparse / nearly random blocks.
    ratio = unique / len(low)
    if nonzero < 0.08 or unique < 8 or unique > 700 or ratio > 0.70:
        return 0.0
    return (1.0 - abs(0.28 - ratio)) * min(1.0, nonzero / 0.5)


def extract_map_candidates(data: bytes, out_dir: Path, max_candidates: int = 80):
    folder = out_dir / "Maps" / "Tilemap_Candidates"
    folder.mkdir(parents=True, exist_ok=True)
    candidates = []
    # Standard GBA BG maps commonly use 32x32 (0x800 bytes) screenblocks.
    # Also inspect 64x32 / 32x64 sized chunks for larger layouts.
    for size, width, height in ((0x800, 32, 32), (0x1000, 32, 64), (0x1000, 64, 32)):
        for off in range(0, len(data) - size + 1, 0x800):
            block = data[off:off+size]
            score = _map_score(block)
            if score >= 0.40:
                candidates.append((score, off, block, width, height))
    # Non-maximum suppression: overlapping windows usually describe the same map.
    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = []
    for item in candidates:
        if all(abs(item[1] - old[1]) >= 0x800 for old in selected):
            selected.append(item)
        if len(selected) >= max_candidates: break
    try:
        from PIL import Image
    except Exception:
        Image = None
    manifest = []
    for idx, (score, off, block, width, height) in enumerate(selected, 1):
        stem = f"MapCandidate_{idx:03d}_{off:08X}"
        (folder / f"{stem}.bin").write_bytes(block)
        if Image:
            vals = struct.unpack("<" + "H" * (len(block)//2), block)
            # Diagnostic tile-index heatmap only; not a rendered in-game map.
            pixels = bytes(min(255, (v & 0x03FF) // 4) for v in vals)
            Image.frombytes("L", (width, height), pixels).save(folder / f"{stem}_index_preview.png")
        manifest.append({"offset": f"0x{off:08X}", "width": width, "height": height,
                         "bytes": len(block), "score": round(score, 4), "file": f"{stem}.bin"})
    with (folder / "map_candidates.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["offset", "width", "height", "bytes", "score", "file"])
        w.writeheader(); w.writerows(manifest)
    return len(manifest)


def extract_audio_candidates(data: bytes, out_dir: Path, max_pcm: int = 24):
    folder = out_dir / "Audio"
    folder.mkdir(parents=True, exist_ok=True)
    found = 0
    # Preserve standard embedded RIFF/WAVE and Standard MIDI files where present.
    for sig, ext in ((b"RIFF", ".wav"), (b"MThd", ".mid")):
        pos = 0
        while True:
            off = data.find(sig, pos)
            if off < 0: break
            if sig == b"RIFF" and off + 12 <= len(data) and data[off+8:off+12] == b"WAVE":
                size = min(len(data) - off, struct.unpack_from("<I", data, off+4)[0] + 8)
            elif sig == b"MThd" and off + 8 <= len(data):
                # MIDI length is not trivially known from the header; preserve
                # from signature to the next 0x1000 boundary as a candidate.
                size = min(0x10000, len(data) - off)
            else:
                pos = off + 4; continue
            (folder / f"Embedded_{found+1:03d}_{off:08X}{ext}").write_bytes(data[off:off+size])
            found += 1; pos = off + size
    # GBA sample banks are often raw 8-bit PCM with no file signature. Inspect
    # aligned blocks and export only plausible waveform candidates as WAV.
    pcm_dir = folder / "PCM_Candidates"
    pcm_dir.mkdir(exist_ok=True)
    selected = []
    block_size = 0x1000
    for off in range(0, len(data) - block_size + 1, block_size):
        raw = data[off:off+block_size]
        if len(set(raw)) < 12: continue
        mean = sum(raw) / len(raw)
        if not 80 <= mean <= 176: continue
        crossings = sum((raw[i] < 128) != (raw[i-1] < 128) for i in range(1, len(raw))) / (len(raw)-1)
        if not 0.015 <= crossings <= 0.48: continue
        # Entropy filter helps reject flat / highly structured non-audio blocks.
        counts = [0] * 256
        for b in raw: counts[b] += 1
        entropy = -sum((c/len(raw))*math.log2(c/len(raw)) for c in counts if c)
        if entropy < 3.0: continue
        selected.append((entropy, off, raw))
    selected.sort(reverse=True)
    for n, (_, off, raw) in enumerate(selected[:max_pcm], 1):
        # WAV PCM 8-bit is unsigned; center the likely signed GBA samples.
        wav_data = bytes((b ^ 0x80) for b in raw)
        path = pcm_dir / f"PCM_Candidate_{n:03d}_{off:08X}.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(1); wf.setframerate(11025); wf.writeframes(wav_data)
        found += 1
    return found


def export_extended_assets(data: bytes, out_dir: Path):
    return {
        "text_strings": extract_text_candidates(data, out_dir),
        "map_candidates": extract_map_candidates(data, out_dir),
        "audio_candidates": extract_audio_candidates(data, out_dir),
    }

"""Cross-reference generic discovery results without claiming semantic certainty."""
from __future__ import annotations
import csv, json
from pathlib import Path


def correlate_discoveries(pointer_info, compressed, palettes, graphics, output_dir):
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    targets = [r["target"] for r in pointer_info.get("references", [])]
    streams = [{"offset": x.get("offset", 0), "format": x.get("format"),
                "size": x.get("decoded_size", len(x.get("data", b"")))} for x in compressed]
    gfx = []
    for bpp, entries in graphics.items():
        for entry in entries:
            off = int(entry.get("offset", 0))
            nearest = min(palettes, key=lambda p: abs(int(p["offset"])-off), default=None)
            near_ptr = min(targets, key=lambda p: abs(p-off), default=None)
            near_stream = min(streams, key=lambda s: abs(s["offset"]-off), default=None)
            gfx.append({"graphics_offset": off, "bpp": int(bpp),
                        "nearest_palette_offset": nearest.get("offset") if nearest else None,
                        "palette_distance": abs(nearest["offset"]-off) if nearest else None,
                        "nearest_pointer_target": near_ptr,
                        "pointer_distance": abs(near_ptr-off) if near_ptr is not None else None,
                        "nearest_compressed_stream": near_stream,
                        "classification": "correlated_candidate"})
    report = {"method": "nearest-offset correlation; heuristic only",
              "graphics_relationships": gfx,
              "pointer_reference_count": pointer_info.get("reference_count", 0),
              "compressed_stream_count": len(streams), "palette_count": len(palettes)}
    (out / "candidate_correlations.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "candidate_correlations.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["graphics_offset", "bpp", "nearest_palette_offset", "palette_distance",
                                         "nearest_pointer_target", "pointer_distance", "classification"])
        w.writeheader()
        for row in gfx:
            w.writerow({k: row.get(k) for k in w.fieldnames})
    return report

"""Universal GBA auto asset extraction.

Extracts verifiable container formats (BIOS LZ77 0x10 and RLE 0x30),
then generates visual candidates from decoded streams and raw ROM regions.
It deliberately labels heuristic images as candidates, never as confirmed assets.
"""
from __future__ import annotations
import json
from pathlib import Path
from .lz77 import decompress_lz10
from .graphics_scanner import scan_graphics, scan_palettes
from .graphics import decode_tiles, decode_palette, save_tiles_png


def decompress_rle30(data: bytes, offset: int = 0, max_output: int = 32*1024*1024):
    if offset < 0 or offset + 4 > len(data) or data[offset] != 0x30:
        raise ValueError("Invalid GBA RLE header")
    size = data[offset+1] | (data[offset+2] << 8) | (data[offset+3] << 16)
    if size <= 0 or size > max_output:
        raise ValueError("RLE output size outside safety limit")
    src, out = offset+4, bytearray()
    while len(out) < size:
        if src >= len(data): raise ValueError("Unexpected end of RLE stream")
        flag = data[src]; src += 1
        count = (flag & 0x7F) + (3 if flag & 0x80 else 1)
        if flag & 0x80:
            if src >= len(data): raise ValueError("Missing RLE run byte")
            value=data[src]; src+=1
            out.extend(bytes([value])*min(count,size-len(out)))
        else:
            if src+count > len(data): raise ValueError("Truncated RLE literal")
            out.extend(data[src:src+min(count,size-len(out))]); src+=count
    return {"data":bytes(out),"consumed":src-offset,"declared_size":size}


def scan_compressed_streams(data: bytes, max_candidates=5000, max_output=4*1024*1024, progress_callback=None):
    found=[]; signatures=(0x10,0x30)
    # Walk every byte once. False positives are filtered by strict decoder validation.
    total=len(data)
    for off,b in enumerate(data):
        if b not in signatures or off+4>total: continue
        size=data[off+1] | data[off+2]<<8 | data[off+3]<<16
        if size<0x20 or size>max_output: continue
        try:
            result = decompress_lz10(data,off,max_output) if b==0x10 else decompress_rle30(data,off,max_output)
        except (ValueError, IndexError):
            continue
        if result["consumed"] < (5 if b==0x30 else 8): continue
        found.append({"format":"LZ77" if b==0x10 else "RLE","offset":off,
                      "compressed_size":result["consumed"],"decoded_size":len(result["data"]),
                      "data":result["data"]})
        if len(found)>=max_candidates: break
        if progress_callback and off % 0x10000 == 0:
            progress_callback(off,total)
    found.sort(key=lambda x:(-x["decoded_size"],x["offset"]))
    return found


def _nearest_palette(data, palettes, offset, bpp):
    need=32 if bpp==4 else 512
    choices=[p for p in palettes if abs(p["offset"]-offset)<=0x20000 and p["offset"]+need<=len(data)]
    if not choices: return None,None
    chosen=min(choices,key=lambda p:abs(p["offset"]-offset))
    return decode_palette(data[chosen["offset"]:chosen["offset"]+need]),chosen["offset"]



def scan_rom_pointers(data: bytes, max_refs: int = 250000):
    """Find aligned GBA ROM pointers (0x08000000-0x09FFFFFF) and likely tables.

    This is structural discovery, not proof that a pointer targets a sprite.
    Consecutive pointer slots are grouped as candidate tables for later profiles.
    """
    import struct
    refs = []
    table_runs = []
    run = []
    for slot in range(0, len(data) - 3, 4):
        value = struct.unpack_from('<I', data, slot)[0]
        if 0x08000000 <= value < 0x0A000000:
            target = value - 0x08000000
            if target < len(data):
                ref = {"slot": slot, "target": target, "value": value}
                refs.append(ref)
                if run and slot == run[-1]["slot"] + 4:
                    run.append(ref)
                else:
                    if len(run) >= 3:
                        table_runs.append(run)
                    run = [ref]
                if len(refs) >= max_refs:
                    break
        else:
            if len(run) >= 3:
                table_runs.append(run)
            run = []
    if len(run) >= 3:
        table_runs.append(run)
    tables = [{"start": r[0]["slot"], "end": r[-1]["slot"] + 4,
               "count": len(r), "targets": [x["target"] for x in r]}
              for r in table_runs]
    return {"references": refs, "tables": tables,
            "reference_count": len(refs), "table_count": len(tables)}

def run_full_auto_scan(rom, progress_callback=None, max_candidates=240):
    data=rom.data
    # MFoMT (BFGE) has a known DefinedSprite/OAM/tile/palette data model.
    # Use the game-specific renderer instead of presenting raw 4BPP/8BPP blocks.
    header = rom.header_info()
    def report(stage, pct, detail):
        if progress_callback:
            progress_callback(stage, pct, detail)

    if header.get("game_code") == "BFGE":
        report("MFoMT sprite reconstruction", 10, "Reading sprite definitions")
        from .mfomt_sprite_re import trace_and_parse_rom
        mfomt_report = trace_and_parse_rom(rom.path)
        if progress_callback:
            progress_callback("MFoMT sprite reconstruction", 100,
                              f"{mfomt_report.get('static_definition_count', 0)} definitions found")
        return {"profile": "MFoMT", "rom": rom.path.name, "header": header,
                "mfomt_report": mfomt_report}
    if header.get("game_code") == "BPRE":
        report("Pokémon FireRed profile", 10, "Reading Gen III sprite and palette tables")
        from .pokemon_gen3 import scan_pokemon_gen3
        result = scan_pokemon_gen3(rom)
        report("Pokémon FireRed profile", 100, "Sprite tables loaded")
        return result
    report("ROM header", 2, "Reading game identity and ROM metadata")
    header=rom.header_info()
    report("Pointer discovery",4,"Finding GBA ROM pointers and candidate pointer tables")
    pointers = scan_rom_pointers(data)
    report("Compressed streams",7,"Validating GBA LZ77 and RLE streams")
    compressed=scan_compressed_streams(data,max_candidates=max_candidates,
        progress_callback=lambda n,t:report("Compressed streams",5+int(25*n/max(1,t)),f"{n:,}/{t:,} bytes"))
    report("Palette discovery",32,"Scanning BGR555 palette candidates")
    palettes=scan_palettes(data,max_results=500,step=0x100,
        progress_callback=lambda n,t:report("Palette discovery",32+int(12*n/max(1,t)),f"{n:,}/{t:,} blocks"))
    report("Raw 4BPP discovery",45,"Scoring raw 4BPP tile regions")
    raw4=scan_graphics(data,4,block_size=0x800,step=0x800,max_results=100,
        progress_callback=lambda n,t:report("Raw 4BPP discovery",45+int(18*n/max(1,t)),f"{n:,}/{t:,} blocks"))
    report("Raw 8BPP discovery",64,"Scoring raw 8BPP tile regions")
    raw8=scan_graphics(data,8,block_size=0x1000,step=0x1000,max_results=60,
        progress_callback=lambda n,t:report("Raw 8BPP discovery",64+int(16*n/max(1,t)),f"{n:,}/{t:,} blocks"))
    report("Reconstruction",82,"Preparing candidate images and metadata")
    result={"profile":"generic_gba","rom":rom.path.name,"header":header,"pointers":pointers,
            "compressed":compressed,"palettes":palettes,"raw_4bpp":raw4,"raw_8bpp":raw8}
    report("Complete",100,f"{len(compressed)} compressed, {len(raw4)+len(raw8)} raw graphics candidates")
    return result


def export_full_auto_scan(result, rom, output_dir):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    # Preserve the complete original ROM byte-for-byte. This guarantees no
    # source bytes are silently discarded even when a game-specific decoder is
    # not yet available. Semantic extraction remains profile/heuristic based.
    import shutil
    raw_dir = out / "ROM_Dump"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_dump = raw_dir / rom.path.name
    if not raw_dump.exists():
        shutil.copy2(rom.path, raw_dump)
    raw_dump_rel = str(raw_dump.relative_to(out))
    # Shared extraction runs for every ROM profile, including MFoMT and Pokémon.
    from .extended_assets import export_extended_assets
    extended = export_extended_assets(rom.data, out)
    # Apply imported community profiles to every ROM, independently of built-in profiles.
    from .profile_manager import scan_all_profiles
    profile_dir = Path(__file__).resolve().parent.parent / "profiles"
    profile_matches = scan_all_profiles(rom.data, profile_dir, rom.header_info().get("game_code", ""))
    profile_out = out / "Community_Profile_Matches"
    profile_out.mkdir(parents=True, exist_ok=True)
    (profile_out / "matches.json").write_text(json.dumps({
        "matches": profile_matches,
        "note": "Exact signature matches are candidates; review before confirmation."
    }, indent=2), encoding="utf-8")
    if result.get("profile") == "pokemon_gen3":
        from .pokemon_gen3 import export_pokemon_gen3
        info = export_pokemon_gen3(result, rom, out)
        info.setdefault("summary", {}).update(extended)
        info.setdefault("summary", {})["community_profile_matches"] = len(profile_matches)
        manifest_path = Path(info["manifest"])
        try:
            pokemon_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            pokemon_manifest.setdefault("summary", {}).update(extended)
            pokemon_manifest["summary"]["community_profile_matches"] = len(profile_matches)
            pokemon_manifest["raw_rom_dump"] = raw_dump_rel
            pokemon_manifest["limitations"] = ["The original ROM is preserved byte-for-byte in ROM_Dump.",
                "The profile exports supported Pokémon sprite tables; remaining game data is preserved in the raw ROM dump and is not all semantically decoded."]
            pokemon_manifest["extended_extraction"] = {
                "note": "Map, audio and text outputs are heuristic candidates; game-specific sound engines and text encodings may require a dedicated profile."
            }
            manifest_path.write_text(json.dumps(pokemon_manifest, indent=2), encoding="utf-8")
        except (OSError, ValueError, KeyError):
            pass
        info["raw_rom_dump"] = raw_dump_rel
        info.setdefault("limitations", []).append("A byte-for-byte ROM dump is included; this preserves all source bytes but is not equivalent to semantic decoding of every asset.")
        return info
    if result.get("profile") == "MFoMT":
        from .mfomt_sprite_re import export_all_reconstructed
        sprites_dir = out / "Sprites"
        sprites_dir.mkdir(parents=True, exist_ok=True)
        reconstructed = export_all_reconstructed(rom.path, result["mfomt_report"], sprites_dir)
        assets = []
        for definition in reconstructed:
            for frame in definition.get("frames", []):
                rel = str(Path(frame["png"]).relative_to(out))
                assets.append({"kind": "sprite_frame", "definition": definition["definition_offset"],
                               "frame": frame["frame"], "png": rel,
                               "width": frame["width"], "height": frame["height"]})
        report = {"rom": rom.path.name, "profile": "Harvest Moon: More Friends of Mineral Town (BFGE)",
                  "summary": {"sprite_definitions": len(reconstructed), "rendered_assets": len(assets),
                              "png_assets": len(assets)}, "assets": assets,
                  "note": "PNG frames reconstructed from DefinedSprite metadata, OAM entries, tile data and palette banks."}
        (out / "asset_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        import csv
        with (out / "asset_manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
            fields = ["kind", "definition", "frame", "png", "width", "height"]
            writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(assets)
        report["summary"].update(extended)
        report["summary"]["community_profile_matches"] = len(profile_matches)
        report["extended_extraction"] = {
            "note": "Map, audio and text outputs are heuristic candidates; verify before treating them as confirmed game assets."
        }
        (out / "asset_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["raw_rom_dump"] = raw_dump_rel
        report["limitations" ] = ["The original ROM is preserved byte-for-byte in ROM_Dump.",
            "Map/audio/text outputs are heuristic candidates; complete semantic decoding requires a game-specific profile."]
        (out / "asset_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return {"directory": str(out), "manifest": str(out / "asset_manifest.json"),
                "csv": str(out / "asset_manifest.csv"), "exported": len(assets),
                "summary": report["summary"], "raw_rom_dump": raw_dump_rel}
    folders={k:out/k for k in ("Compressed","Graphics_4BPP","Graphics_8BPP","Pointer_Tables")}
    for p in folders.values(): p.mkdir(exist_ok=True)
    manifest=[]; palettes=result["palettes"]; data=rom.data
    pointer_info = result.get("pointers", {"references": [], "tables": [], "reference_count": 0, "table_count": 0})
    pointer_json = {"rom": rom.path.name, "game": result.get("header", {}).get("detected_game"),
                    "reference_count": pointer_info.get("reference_count", 0),
                    "table_count": pointer_info.get("table_count", 0),
                    "tables": [{"start": f"0x{x['start']:08X}", "end": f"0x{x['end']:08X}",
                                "count": x["count"], "targets": [f"0x{v:08X}" for v in x["targets"]]}
                               for x in pointer_info.get("tables", [])]}
    (folders["Pointer_Tables"] / "pointer_tables.json").write_text(json.dumps(pointer_json, indent=2), encoding="utf-8")
    with (folders["Pointer_Tables"] / "pointer_references.csv").open("w", newline="", encoding="utf-8-sig") as pf:
        import csv as _csv
        pw = _csv.writer(pf); pw.writerow(["pointer_slot", "rom_target"])
        pw.writerows([(f"0x{x['slot']:08X}", f"0x{x['target']:08X}") for x in pointer_info.get("references", [])])
    # Preserve every validated decompressed stream returned by the scanner.
    all_streams_dir = folders["Compressed"] / "All_Streams"
    all_streams_dir.mkdir(parents=True, exist_ok=True)
    stream_index = []
    for idx, entry in enumerate(result.get("compressed", []), 1):
        raw = entry.get("data", b"")
        off = entry.get("offset", 0)
        fmt = entry.get("format", "compressed")
        name = f"{idx:05d}_{fmt}_{off:08X}.bin"
        (all_streams_dir / name).write_bytes(raw)
        stream_index.append({"index": idx, "format": fmt, "rom_offset": f"0x{off:08X}",
                             "decoded_bytes": len(raw), "file": name})
    (all_streams_dir / "index.json").write_text(json.dumps(stream_index, indent=2), encoding="utf-8")
    # Rebuild decoded compressed streams in 4bpp/8bpp arrangements when possible.
    renderable = [e for e in result["compressed"] if len(e["data"]) <= 0x10000][:100]
    for i,e in enumerate(renderable,1):
        raw=e["data"]; fmt=e["format"]; off=e["offset"]
        stem=f"{fmt}_{off:08X}_{len(raw)}B"
        folder=folders["Compressed"]
        (folder/(stem+".bin")).write_bytes(raw)
        entry={"kind":"decompressed_"+fmt,"offset":f"0x{off:08X}","decoded_size":len(raw),
               "bin":str((folder/(stem+".bin")).relative_to(out)),"images":[]}
        for bpp in (4,8):
            unit=32 if bpp==4 else 64
            if len(raw)<unit*4 or len(raw)%unit: continue
            palette,paloff=_nearest_palette(data,palettes,off,bpp)
            if palette is None: palette=[(i*17,i*17,i*17) for i in range(16 if bpp==4 else 256)]
            tiles=decode_tiles(raw,bpp)
            cols=8 if len(tiles)<=64 else 16
            png=folder/f"{stem}_{bpp}bpp.png"
            save_tiles_png(tiles,cols,png,palette=palette,scale=2,transparent_index=0)
            entry["images"].append({"bpp":bpp,"png":str(png.relative_to(out)),
                "palette_offset":f"0x{paloff:08X}" if paloff is not None else None,
                "palette_status":"nearest heuristic" if paloff is not None else "grayscale fallback"})
        manifest.append(entry)
    for key,bpp in (("raw_4bpp",4),("raw_8bpp",8)):
        folder=folders["Graphics_4BPP" if bpp == 4 else "Graphics_8BPP"]
        for i,e in enumerate(result[key],1):
            off=e["offset"]; size=e["size"]; raw=data[off:off+size]
            palette,paloff=_nearest_palette(data,palettes,off,bpp)
            if palette is None: palette=[(i*17,i*17,i*17) for i in range(16 if bpp==4 else 256)]
            tiles=decode_tiles(raw,bpp); cols=16
            stem=f"{bpp}bpp_{off:08X}"
            png=folder/(stem+".png"); save_tiles_png(tiles,cols,png,palette=palette,scale=2,transparent_index=0)
            (folder/(stem+".bin")).write_bytes(raw)
            manifest.append({"kind":"raw_graphics_candidate","bpp":bpp,"offset":f"0x{off:08X}",
                "png":str(png.relative_to(out)),"bin":str((folder/(stem+".bin")).relative_to(out)),
                "score":e.get("score"),"palette_offset":f"0x{paloff:08X}" if paloff is not None else None,
                "palette_status":"nearest heuristic" if paloff is not None else "grayscale fallback"})
    # Cross-correlate pointer targets, streams, palettes and graphics by proximity.
    from .correlation import correlate_discoveries
    correlation = correlate_discoveries(pointer_info, result.get("compressed", []), palettes,
        {"4": result.get("raw_4bpp", []), "8": result.get("raw_8bpp", [])}, out / "Correlations")
    report={"rom":result["rom"],"header":result["header"],"raw_rom_dump":raw_dump_rel,
        "pointer_discovery":{"references":pointer_info.get("reference_count",0),"candidate_tables":pointer_info.get("table_count",0)},
        "summary":{"compressed_streams":sum(1 for item in manifest if item.get("kind", "").startswith("decompressed_")),
                   "raw_4bpp_candidates":len(result["raw_4bpp"]),
                   "raw_8bpp_candidates":len(result["raw_8bpp"]),
                   "palette_candidates":len(palettes),"rendered_assets":len(manifest),
                   "compressed_streams_found":len(result["compressed"]),
                   "community_profile_matches":len(profile_matches),
                   "correlated_graphics_candidates":len(correlation.get("graphics_relationships", []))},
        "assets":manifest,
        "limitations":["Generic extraction renders graphics candidates; not every image is a confirmed in-game asset.",
        "Nearest palette is a visual hint, not a verified association.",
        "Custom codecs, encrypted data, tilemaps, OAM and game-specific runtime structures need profiles."]}
    report["summary"].update(extended)
    report["extended_extraction"] = {
        "note": "Map, audio and text outputs are heuristic candidates; verify before treating them as confirmed game assets."
    }
    (out/"asset_manifest.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    import csv
    with (out/"asset_manifest.csv").open("w",newline="",encoding="utf-8-sig") as f:
        fields=["kind","offset","decoded_size","bpp","score","png","bin","palette_offset","palette_status"]
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for item in manifest:
            if item.get("images"):
                for image in item["images"]:
                    writer.writerow({"kind":item["kind"],"offset":item["offset"],
                        "decoded_size":item["decoded_size"],"bpp":image["bpp"],
                        "png":image["png"],"bin":item["bin"],
                        "palette_offset":image["palette_offset"],"palette_status":image["palette_status"]})
            else:
                writer.writerow({k:item.get(k,"") for k in fields})
    return {"directory":str(out),"manifest":str(out/"asset_manifest.json"),
            "csv":str(out/"asset_manifest.csv"),"exported":len(manifest),"summary":report["summary"]}

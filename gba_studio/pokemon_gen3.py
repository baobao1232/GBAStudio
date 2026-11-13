"""Pokémon FireRed (USA, BPRE) asset profile.

Extraction logic adapted from tjtwl/ROM-Asset-Extractor (GPL-3.0):
https://github.com/tjtwl/ROM-Asset-Extractor
Copyright (C) 2021 TheJjokerR. See THIRD_PARTY_LICENSES/GPL-3.0.txt.
This Python implementation is a focused port of the Gen-III sprite/palette
pipeline; it does not claim full parity with the original C# application.
"""
from __future__ import annotations
import json, struct
from pathlib import Path
from PIL import Image

ROM_BASE = 0x08000000
# FireRed USA BPRE offsets from the upstream pokeroms.yml profile.
PROFILES = {
    "BPRE": {
        "name": "Pokémon FireRed (USA)",
        "species_sprites": 0x2350AC,
        "species_palettes": 0x23730C,
        "species_shiny_palettes": 0x2380CC,
        "species_back_sprites": 0x23654C,
        "trainer_sprites": 0x23957C,
        "trainer_palettes": 0x239A1C,
        "trainer_count": 147,
        "species_count": 440,
    }
}


def _ptr(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        raise ValueError(f"Pointer table outside ROM at 0x{off:X}")
    value = struct.unpack_from('<I', data, off)[0]
    if value < ROM_BASE or value >= ROM_BASE + len(data):
        raise ValueError(f"Invalid GBA ROM pointer 0x{value:08X}")
    return value - ROM_BASE


def _lz77(data: bytes, off: int, max_size=8 * 1024 * 1024) -> bytes:
    if off < 0 or off + 4 > len(data) or data[off] != 0x10:
        raise ValueError(f"Missing LZ77 stream at 0x{off:X}")
    size = data[off+1] | data[off+2] << 8 | data[off+3] << 16
    if size <= 0 or size > max_size:
        raise ValueError("Invalid LZ77 decompressed size")
    src = off + 4
    out = bytearray()
    while len(out) < size:
        if src >= len(data): raise ValueError("Truncated LZ77 flags")
        flags = data[src]; src += 1
        for bit in range(7, -1, -1):
            if len(out) >= size: break
            if flags & (1 << bit):
                if src + 2 > len(data): raise ValueError("Truncated LZ77 back-reference")
                a, b = data[src], data[src+1]; src += 2
                count = (a >> 4) + 3
                disp = ((a & 0x0F) << 8 | b) + 1
                if disp > len(out): raise ValueError("Invalid LZ77 displacement")
                for _ in range(count):
                    if len(out) >= size: break
                    out.append(out[-disp])
            else:
                if src >= len(data): raise ValueError("Truncated LZ77 literal")
                out.append(data[src]); src += 1
    return bytes(out)


def _palette(data: bytes, off: int) -> list[tuple[int,int,int,int]]:
    raw = _lz77(data, off, 0x1000)
    if len(raw) < 32: raise ValueError("Palette stream is shorter than 16 colors")
    colors=[]
    for i in range(16):
        c = raw[i*2] | raw[i*2+1] << 8
        r = (c & 31) * 255 // 31
        g = ((c >> 5) & 31) * 255 // 31
        b = ((c >> 10) & 31) * 255 // 31
        colors.append((r,g,b,0 if i == 0 else 255))
    return colors


def _sprite_image(raw: bytes, palette, width=64) -> Image.Image:
    # GBA 4bpp tiled graphics: 8x8 tiles, 32 bytes per tile.
    tile_bytes = 32
    if not raw or len(raw) % tile_bytes:
        raw = raw[:len(raw)//tile_bytes*tile_bytes]
    tiles = len(raw) // tile_bytes
    if tiles == 0: raise ValueError("Empty sprite graphics")
    tiles_wide = width // 8
    tiles_high = (tiles + tiles_wide - 1) // tiles_wide
    img = Image.new('RGBA', (width, tiles_high*8), (0,0,0,0))
    px = img.load()
    for t in range(tiles):
        tx, ty = t % tiles_wide, t // tiles_wide
        base = t * 32
        for y in range(8):
            for x in range(4):
                v = raw[base + y*4 + x]
                for half, idx in ((0, v & 15), (1, v >> 4)):
                    px[tx*8+x*2+half, ty*8+y] = palette[idx]
    # Crop padding to full 8px rows only; sprite source data may include padded tile rows.
    return img


def _read_refs(data: bytes, table: int, count: int):
    refs=[]
    for i in range(count):
        off = table + i*8
        ptr = _ptr(data, off)
        game_index = struct.unpack_from('<H', data, off+6)[0]
        refs.append((ptr, game_index))
    return refs


def scan_pokemon_gen3(rom):
    data = rom.data
    code = data[0xAC:0xB0].decode('ascii', errors='replace')
    if code not in PROFILES:
        raise ValueError(f"Pokémon Gen 3 profile chưa hỗ trợ game code {code}")
    return {"profile":"pokemon_gen3", "game_code":code, "profile_data":PROFILES[code],
            "rom":rom.path.name}


def export_pokemon_gen3(result, rom, output_dir):
    data=rom.data; cfg=result['profile_data']; out=Path(output_dir)
    dirs={name:out/name for name in ('Pokemon/Front','Pokemon/Back','Pokemon/Shiny','Trainers/Front')}
    for p in dirs.values(): p.mkdir(parents=True,exist_ok=True)
    assets=[]; errors=[]
    # Species sprite pointers are records of 8 bytes: pointer, unused halfword, National/game index.
    fronts=_read_refs(data,cfg['species_sprites'],cfg['species_count'])
    backs=_read_refs(data,cfg['species_back_sprites'],cfg['species_count'])
    for i,((front,game_idx),(back,_)) in enumerate(zip(fronts,backs)):
        try:
            pal_off=_ptr(data,cfg['species_palettes']+i*8)
            shiny_off=_ptr(data,cfg['species_shiny_palettes']+i*8)
            pal=_palette(data,pal_off); shiny=_palette(data,shiny_off)
            front_img=_sprite_image(_lz77(data,front),pal)
            back_img=_sprite_image(_lz77(data,back),pal)
            shiny_img=_sprite_image(_lz77(data,front),shiny)
            # Stable index names avoid depending on localized game text decoding.
            for folder, image, suffix in ((dirs['Pokemon/Front'],front_img,'front'),
                                          (dirs['Pokemon/Back'],back_img,'back'),
                                          (dirs['Pokemon/Shiny'],shiny_img,'shiny')):
                name=f'{i:03d}_{game_idx:03d}_{suffix}.png'; image.save(folder/name)
                assets.append({"category":"pokemon","variant":suffix,"index":i,"game_index":game_idx,
                               "png":str((folder/name).relative_to(out)),"width":image.width,"height":image.height})
        except Exception as exc:
            errors.append({"category":"pokemon","index":i,"error":str(exc)})
    # Trainer sprite/palette pointer tables contain 4-byte pointers.
    for i in range(cfg['trainer_count']):
        try:
            sp=_ptr(data,cfg['trainer_sprites']+i*4)
            po=_ptr(data,cfg['trainer_palettes']+i*4)
            img=_sprite_image(_lz77(data,sp),_palette(data,po))
            name=f'{i:03d}_trainer.png'; img.save(dirs['Trainers/Front']/name)
            assets.append({"category":"trainer","index":i,"png":str((dirs['Trainers/Front']/name).relative_to(out)),
                           "width":img.width,"height":img.height})
        except Exception as exc:
            errors.append({"category":"trainer","index":i,"error":str(exc)})
    manifest={"rom":rom.path.name,"profile":cfg['name'],"game_code":result['game_code'],
              "summary":{"rendered_assets":len(assets),"png_assets":len(assets),"failed_entries":len(errors)},"assets":assets,"errors":errors,
              "scope":"Pokémon species front/back/shiny sprites and trainer front sprites. Maps, overworld animations, battle effects and item icons are not included in this profile build."}
    (out/'asset_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return {"directory":str(out),"manifest":str(out/'asset_manifest.json'),"exported":len(assets),"summary":manifest['summary']}

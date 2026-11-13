"""MFoMT(U) DefinedSprite constructor cross-reference scanner.

Based on StanHash/FOMT-DOC Sprites.txt. This identifies Thumb BL call sites
for DefinedSprite_construct (ROM offset 0x061448). It deliberately does not
pretend call sites are item icons: each call must still be traced to its
sprite-definition argument and item/UI usage.
"""
from __future__ import annotations
import csv, json
from pathlib import Path

ROM_BASE = 0x08000000
DEFINED_SPRITE_CONSTRUCT = 0x08061448


def thumb_bl_targets(data: bytes):
    for off in range(0xC0, len(data) - 3, 2):
        h1 = int.from_bytes(data[off:off+2], 'little')
        h2 = int.from_bytes(data[off+2:off+4], 'little')
        if (h1 & 0xF800) != 0xF000 or (h2 & 0xF800) != 0xF800:
            continue
        imm = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
        if imm & 0x400000:
            imm -= 0x800000
        target = (ROM_BASE + off + 4 + imm) & 0xFFFFFFFF
        yield off, target, h1, h2


def scan_rom(rom_path: str | Path):
    data = Path(rom_path).read_bytes()
    calls = []
    for off, target, h1, h2 in thumb_bl_targets(data):
        if target != DEFINED_SPRITE_CONSTRUCT:
            continue
        start, end = max(0, off - 16), min(len(data), off + 4)
        calls.append({
            'callsite_offset': off,
            'callsite_hex': f'0x{off:06X}',
            'callsite_address': f'0x{ROM_BASE + off:08X}',
            'target_address': f'0x{target:08X}',
            'thumb_bl': f'{h1:04X} {h2:04X}',
            'context_hex': data[start:end].hex(' '),
        })
    return {
        'rom': Path(rom_path).name,
        'rom_size': len(data),
        'game_code': data[0xAC:0xB0].decode('ascii', errors='replace'),
        'game_title': data[0xA0:0xAC].decode('ascii', errors='replace').rstrip('\0'),
        'method': 'Thumb BL cross-reference to DefinedSprite_construct',
        'constructor_rom_offset': '0x061448',
        'constructor_address': '0x08061448',
        'callsite_count': len(calls),
        'callsites': calls,
        'definition_layout': {
            'frame_data': {'oam_ptr': '+0x00', 'oam_count': '+0x04', 'tile_ptr': '+0x08', 'tile_size_bytes': '+0x0C', 'palette_ptr': '+0x10', 'palette_size_bytes': '+0x14', 'rotscale_ptr': '+0x18', 'rotscale_count': '+0x1C'},
            'defined_sprite': {'vtable': '+0x00', 'animation_array_ptr': '+0x04', 'frame_metadata_ptr': '+0x08', 'oam_pool_ptr': '+0x0C', 'tile_pool_ptr': '+0x10', 'palette_pool_ptr': '+0x14', 'rotscale_pool_ptr': '+0x18', 'animation_instruction_pool_ptr': '+0x1C', 'counts': '+0x20..+0x2C'},
            'frame_metadata_size': 16,
            'oam_entry_size': 8,
            'tile_entry_size': 32,
            'palette_entry_size': 32,
            'animation_instruction_size': 4,
        },
        'limitations': [
            'A constructor call is not proof that the object is an item icon.',
            'The constructor argument must be traced to the seven serialized arrays.',
            'The item-icon path may use a separate BG graphics pipeline rather than DefinedSprite.',
        ],
    }


def write_report(rom_path: str | Path, out_dir: str | Path):
    report = scan_rom(rom_path)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / 'mfomt_sprite_constructor_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (out / 'mfomt_sprite_constructor_calls.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['callsite_offset','callsite_hex','callsite_address','target_address','thumb_bl','context_hex'])
        w.writeheader(); w.writerows(report['callsites'])
    return report


# ---- Static Thumb argument tracing and serialized definition parser ----
import struct

ROM_END = 0x0A000000
ARRAY_LAYOUT = [
    ("animation", 4), ("frame_metadata", 16), ("oam", 8),
    ("tile", 32), ("palette", 32), ("rotscale", 8),
    ("animation_instructions", 4),
]

def _u16(data, off):
    return struct.unpack_from('<H', data, off)[0] if 0 <= off <= len(data)-2 else None

def _u32(data, off):
    return struct.unpack_from('<I', data, off)[0] if 0 <= off <= len(data)-4 else None

def _thumb_len(h):
    return 4 if (h & 0xF800) == 0xF000 else 2

def _thumb_step(data, off, regs):
    """Small, conservative Thumb-1 interpreter for straight-line argument setup."""
    h = _u16(data, off)
    if h is None: return 2
    pc = (off + 4) & ~3
    # LDR literal Rd, [PC, #imm*4]
    if (h & 0xF800) == 0x4800:
        rd=(h>>8)&7; addr=pc+((h&0xff)*4); val=_u32(data,addr)
        regs[rd] = val if val is not None else f"literal@0x{addr:X}"
        return 2
    # MOVS Rd, #imm8
    if (h & 0xF800) == 0x2000:
        regs[(h>>8)&7]=h&0xff; return 2
    # ADDS/SUBS Rd, #imm8
    if (h & 0xF800) in (0x3000,0x3800):
        rd=(h>>8)&7; imm=h&0xff; old=regs[rd]
        regs[rd] = old + imm if isinstance(old,int) and (h&0xF800)==0x3000 else old-imm if isinstance(old,int) else f"({old}{'+' if (h&0xF800)==0x3000 else '-'}0x{imm:X})"
        return 2
    # ADD/SUB register or imm3
    if (h & 0xFE00) == 0x1800:
        rd=h&7; rn=(h>>3)&7; op=(h>>9)&1
        if h & 0x0400: rhs=(h>>6)&7
        else: rhs=regs[(h>>6)&7]
        lhs=regs[rn]
        if isinstance(lhs,int) and isinstance(rhs,int): regs[rd]=lhs-rhs if op else lhs+rhs
        else: regs[rd]=f"({lhs}{'-' if op else '+'}{rhs})"
        return 2
    # ADD Rd, Rs (low regs) / MOV high registers
    if (h & 0xFC00) == 0x4400:
        op=(h>>8)&3; rd=(h&7) | ((h>>4)&8); rs=(h>>3)&15
        if op == 2: regs[rd]=regs[rs]
        elif op == 0:
            a,b=regs[rd],regs[rs]
            regs[rd]=a+b if isinstance(a,int) and isinstance(b,int) else f"({a}+{b})"
        return 2
    # LSL immediate
    if (h & 0xF800) == 0x0000:
        rd=h&7; rs=(h>>3)&7; sh=(h>>6)&31; v=regs[rs]
        regs[rd]=v<<sh if isinstance(v,int) else f"({v}<<{sh})"; return 2
    # LDR word immediate
    if (h & 0xF800) == 0x6800:
        rd=(h>>8)&7; rn=(h>>3)&7; imm=((h>>6)&31)*4; base=regs[rn]
        if isinstance(base,int) and ROM_BASE <= base < ROM_END:
            val=_u32(data,base-ROM_BASE+imm); regs[rd]=val if val is not None else f"mem[{base:#x}+{imm:#x}]"
        else: regs[rd]=f"mem[{base}+0x{imm:X}]"
        return 2
    # ADD Rd, Rs, #0
    if (h & 0xFE00) == 0x1C00:
        rd=h&7; rs=(h>>3)&7; regs[rd]=regs[rs]; return 2
    # BL clobbers caller-saved registers. Keep r4-r11.
    if (h & 0xF800) == 0xF000:
        for i in range(4): regs[i]=f"clobbered@{off:#x}"
        return 4
    # Most other instructions do not alter the tracked source registers; conservatively
    # invalidate destinations for common data-processing/load forms.
    if (h & 0xF800) in (0x6000,0x7800,0x8000,0x8800):
        regs[(h>>8)&7]=f"unknown@{off:#x}"
    return 2

def trace_call_arguments(data: bytes, call_off: int, lookback=0x180):
    start=max(0,call_off-lookback)
    # Find nearest PUSH with LR, normally the function prologue.
    candidates=[]
    for o in range(start,call_off,2):
        h=_u16(data,o)
        if h is not None and (h & 0xFE00)==0xB400 and (h & 0x0100): candidates.append(o)
    start=candidates[-1] if candidates else start
    regs={i:f"entry_r{i}" for i in range(16)}
    for o in range(start,call_off,2):
        h=_u16(data,o)
        if h is None: break
        if (h & 0xF800)==0xF000:
            # Skip BL as one instruction; second halfword is not independently decoded.
            _thumb_step(data,o,regs); continue
        _thumb_step(data,o,regs)
    return {"r0":regs[0],"r1":regs[1],"trace_start":start}

def _rom_offset(value):
    return value-ROM_BASE if isinstance(value,int) and ROM_BASE <= value < ROM_END else None

def parse_defined_sprite_definition(data: bytes, ptr: int):
    off=_rom_offset(ptr)
    if off is None or off < 0 or off+4 > len(data):
        return {"valid":False,"reason":"Definition pointer is not a static ROM address.","pointer":ptr}
    pos=off; arrays=[]
    for name, entry_size in ARRAY_LAYOUT:
        count=_u16(data,pos)
        if count is None or count > 0x4000:
            return {"valid":False,"reason":f"Invalid {name} count at ROM offset 0x{pos:X}.","pointer":ptr}
        entries=pos+4; end=entries+count*entry_size
        if end > len(data): return {"valid":False,"reason":f"{name} array exceeds ROM bounds.","pointer":ptr}
        arrays.append({"name":name,"count":count,"offset":entries,"entry_size":entry_size,"end":end})
        pos=end
    # Require plausible populated metadata or animation data; empty structures are often false pointers.
    total=sum(a['count'] for a in arrays)
    if total == 0: return {"valid":False,"reason":"All seven arrays are empty.","pointer":ptr}
    return {"valid":True,"pointer":ptr,"rom_offset":off,"arrays":arrays,"end_offset":pos}

def trace_and_parse_rom(rom_path: str | Path):
    data=Path(rom_path).read_bytes(); base=scan_rom(rom_path)
    definitions=[]
    for call in base['callsites']:
        off=call['callsite_offset']; args=trace_call_arguments(data,off)
        call['arg_r0']=str(args['r0']); call['arg_r1']=str(args['r1'])
        call['trace_start']=f"0x{args['trace_start']:06X}"
        ptr=_rom_offset(args['r1'])
        if ptr is not None:
            parsed=parse_defined_sprite_definition(data,args['r1'])
            call['definition_offset']=f"0x{ptr:06X}"
            call['definition_valid']=parsed['valid']
            if parsed['valid']:
                definitions.append({"callsite":call['callsite_hex'],**parsed})
        else:
            call['definition_offset']=""
            call['definition_valid']=False
    base['argument_trace_count']=sum(1 for c in base['callsites'] if c.get('arg_r1'))
    base['static_definition_count']=len(definitions)
    base['definitions']=definitions
    base['analysis_note']=("r0/r1 values are conservative straight-line Thumb traces. "
        "Static ROM pointers are parsed as seven serialized arrays. Runtime/RAM expressions are not dereferenced; "
        "those require tracing the manager initialization and runtime copy path.")
    return base

def export_definition_tiles(rom_path: str | Path, definition: dict, out_dir: str | Path):
    """Export raw tile and palette pool sheets for a validated definition."""
    from PIL import Image
    data=Path(rom_path).read_bytes(); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    arrays={a['name']:a for a in definition['arrays']}
    tile_a=arrays['tile']; pal_a=arrays['palette']
    tile_bytes=data[tile_a['offset']:tile_a['end']]
    # Raw 4bpp GBA tiles are 8x8, 32 bytes each. Preserve every tile in a contact sheet.
    tile_count=len(tile_bytes)//32
    cols=16; rows=max(1,(tile_count+cols-1)//cols)
    sheet=Image.new('RGBA',(cols*8,rows*8),(0,0,0,0))
    for ti in range(tile_count):
        chunk=tile_bytes[ti*32:(ti+1)*32]
        x0=(ti%cols)*8; y0=(ti//cols)*8
        for y in range(8):
            for x in range(8):
                b=chunk[y*4+x//2]; n=(b>>4)&15 if x&1 else b&15
                sheet.putpixel((x0+x,y0+y),(n*17,n*17,n*17,0 if n==0 else 255))
    tile_path=out/f"definition_{definition['rom_offset']:06X}_tiles_raw.png"; sheet.save(tile_path)
    # Palette bytes are exported as a swatch strip; BGR555 conversion.
    pal_bytes=data[pal_a['offset']:pal_a['end']]
    colors=[]
    for i in range(0,len(pal_bytes)-1,2):
        v=int.from_bytes(pal_bytes[i:i+2],'little'); r=(v&31)*255//31; g=((v>>5)&31)*255//31; b=((v>>10)&31)*255//31
        colors.append((r,g,b,255))
    if colors:
        sw=Image.new('RGBA',(16*8,max(1,((len(colors)+15)//16)*8)),(0,0,0,0))
        for i,c in enumerate(colors):
            x=(i%16)*8; y=(i//16)*8
            for yy in range(8):
                for xx in range(8): sw.putpixel((x+xx,y+yy),c)
        palette_path=out/f"definition_{definition['rom_offset']:06X}_palettes.png"; sw.save(palette_path)
    else: palette_path=None
    return {"tiles_png":str(tile_path),"palette_png":str(palette_path) if palette_path else None,"tile_count":tile_count,"palette_color_count":len(colors)}

def _gba_palette(data, offset, count=16):
    from PIL import ImageColor
    out=[]
    for i in range(count):
        v=_u16(data,offset+i*2) or 0
        out.append(((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31,0 if i==0 else 255))
    return out

def _tile_pixel(data, tile_base, tile_index, x, y, palette):
    off=tile_base+tile_index*32+(y//8)*32+(x//8)*32
    # x/y are local to an individual 8x8 tile; caller selects tile index.
    b=data[off+(y%8)*4+(x%8)//2]
    n=(b>>4)&15 if x&1 else b&15
    return palette[n]

def render_definition_frames(rom_path: str | Path, definition: dict, out_dir: str | Path):
    """Rebuild frame PNGs from frame metadata + OAM + 4bpp tile/palette pools."""
    from PIL import Image
    data=Path(rom_path).read_bytes(); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    a={x['name']:x for x in definition['arrays']}
    fm=a['frame_metadata']; oa=a['oam']; ta=a['tile']; pa=a['palette']
    frames=[]
    for fi in range(fm['count']):
        mo=fm['offset']+fi*16
        oam_count=_u16(data,mo) or 0; oam_index=_u16(data,mo+2) or 0
        tile_index=_u16(data,mo+6) or 0; tile_count=_u16(data,mo+4) or 0
        pal_index=_u16(data,mo+10) or 0; pal_count=_u16(data,mo+8) or 0
        if oam_count==0 or oam_count>128 or oam_index+oam_count>oa['count'] or tile_index>ta['count'] or tile_count>ta['count']-tile_index:
            continue
        # Compose each OAM object into a shared transparent canvas, then crop to visible bounds.
        decoded=[]
        minx=miny=9999; maxx=maxy=-9999
        for oi in range(oam_count):
            oo=oa['offset']+(oam_index+oi)*8
            attr0,attr1,attr2=struct.unpack_from('<HHH',data,oo)
            shape=(attr0>>14)&3; size=(attr1>>14)&3
            dims={0:[(8,8),(16,16),(32,32),(64,64)],1:[(16,8),(32,8),(32,16),(64,32)],2:[(8,16),(8,32),(16,32),(32,64)]}
            if shape not in dims: continue
            w,h=dims[shape][size]
            x=attr1&0x1ff; y=attr0&0xff
            if x>=256: x-=512
            if y>=160: y-=256
            if attr0 & 0x0200: continue  # disabled non-affine OBJ
            xflip=bool(attr1&0x1000); yflip=bool(attr1&0x2000)
            ti=attr2&0x3ff; bank=(attr2>>12)&15
            palette_off=pa['offset']+pal_index*32+bank*32
            if palette_off+32>pa['end']: palette_off=pa['offset']+pal_index*32
            palette=_gba_palette(data,palette_off,16)
            obj=Image.new('RGBA',(w,h),(0,0,0,0))
            for py in range(h):
                for px in range(w):
                    sx=w-1-px if xflip else px; sy=h-1-py if yflip else py
                    tile_no=ti+(sy//8)*(w//8)+(sx//8)
                    byte_off=ta['offset']+tile_index*32+tile_no*32+(sy%8)*4+(sx%8)//2
                    if byte_off>=ta['end']: continue
                    bv=data[byte_off]; ci=(bv>>4)&15 if sx&1 else bv&15
                    obj.putpixel((px,py),palette[ci])
            decoded.append((x,y,obj)); minx=min(minx,x); miny=min(miny,y); maxx=max(maxx,x+w); maxy=max(maxy,y+h)
        if not decoded: continue
        # Crop to a bounded canvas; preserve negative GBA coordinates by shifting origin.
        cw=max(1,min(256,maxx-minx)); ch=max(1,min(256,maxy-miny))
        canvas=Image.new('RGBA',(cw,ch),(0,0,0,0))
        for x,y,obj in decoded: canvas.alpha_composite(obj,(x-minx,y-miny))
        name=f"definition_{definition['rom_offset']:06X}_frame_{fi:03d}.png"
        path=out/name; canvas.save(path)
        frames.append({"frame":fi,"png":str(path),"width":cw,"height":ch,"oam_count":oam_count,"tile_count":tile_count,"palette_count":pal_count})
    return frames

def export_all_reconstructed(rom_path: str | Path, report: dict, out_dir: str | Path):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); results=[]
    seen=set()
    for definition in report.get('definitions',[]):
        key=definition['rom_offset']
        if key in seen: continue
        seen.add(key)
        frames=render_definition_frames(rom_path,definition,out)
        results.append({"definition_offset":f"0x{definition['rom_offset']:06X}","callsite":definition['callsite'],"frame_count":len(frames),"frames":frames})
    # Contact sheet: first reconstructed frame for every unique definition.
    from PIL import Image, ImageDraw
    thumbs=[]
    for item in results:
        if not item['frames']: continue
        im=Image.open(item['frames'][0]['png']).convert('RGBA')
        im.thumbnail((64,64),Image.Resampling.NEAREST)
        thumbs.append((item['definition_offset'],im))
    cols=8; cellw=96; cellh=88; rows=max(1,(len(thumbs)+cols-1)//cols)
    sheet=Image.new('RGBA',(cols*cellw,rows*cellh),(38,38,42,255)); draw=ImageDraw.Draw(sheet)
    for i,(label,im) in enumerate(thumbs):
        x=(i%cols)*cellw; y=(i//cols)*cellh
        sheet.alpha_composite(im,(x+(64-im.width)//2,y+2+(64-im.height)//2))
        draw.text((x+4,y+68),label,fill=(240,240,240,255))
    contact=out/'mfomt_definition_contact_sheet.png'; sheet.save(contact)
    (out/'mfomt_reconstructed_frames.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return results

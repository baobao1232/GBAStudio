from pathlib import Path
from PIL import Image

def decode_palette(raw):
    if len(raw) % 2:
        raise ValueError("Palette data length must be even.")
    colors = []
    for i in range(0, len(raw), 2):
        v = raw[i] | (raw[i+1] << 8)
        r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
        colors.append((r*255//31, g*255//31, b*255//31))
    return colors

def decode_tiles(raw, bpp=4):
    if bpp not in (4, 8):
        raise ValueError("BPP must be 4 or 8.")
    unit = 32 if bpp == 4 else 64
    if len(raw) % unit:
        raise ValueError(f"Raw tile data must be a multiple of {unit} bytes.")
    result = []
    for start in range(0, len(raw), unit):
        chunk = raw[start:start+unit]
        if bpp == 4:
            pixels = []
            for value in chunk:
                pixels.extend((value & 15, value >> 4))
        else:
            pixels = list(chunk)
        result.append(pixels)
    return result

def save_tiles_png(tiles, columns, path, palette=None, scale=2, transparent_index=None):
    if not tiles:
        raise ValueError("No tile data to render.")
    if columns < 1:
        raise ValueError("Columns must be positive.")
    max_index = max(max(t) for t in tiles)
    needed = 256 if max_index > 15 else 16
    colors = list(palette) if palette else [(i*17, i*17, i*17) for i in range(16)]
    if len(colors) < needed:
        colors.extend([(i, i, i) for i in range(len(colors), needed)])
    rows = (len(tiles) + columns - 1) // columns
    image = Image.new("RGBA", (columns*8, rows*8), (48, 48, 48, 255))
    for idx, tile in enumerate(tiles):
        ox, oy = (idx % columns)*8, (idx // columns)*8
        for p, value in enumerate(tile):
            color = colors[value]
            alpha = 0 if transparent_index is not None and value == transparent_index else 255
            image.putpixel((ox+p%8, oy+p//8), (*color, alpha))
    if scale > 1:
        image = image.resize((image.width*scale, image.height*scale), Image.Resampling.NEAREST)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def decode_tiles_4bpp_gba(raw):
    """GBA 4BPP OBJ/BG tile order: low nibble is left pixel, high nibble right pixel."""
    return decode_tiles(raw, 4)


def decode_tiles_8bpp_gba(raw):
    """GBA 8BPP tile order: one byte per pixel."""
    return decode_tiles(raw, 8)

import struct, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from gba_studio.pokemon_gen3 import _lz77, _palette, _sprite_image, scan_pokemon_gen3, export_pokemon_gen3
from gba_studio.auto_extractor import run_full_auto_scan


def lz_literal(payload):
    out=bytearray([0x10, len(payload)&255, (len(payload)>>8)&255, (len(payload)>>16)&255])
    for i in range(0,len(payload),8):
        chunk=payload[i:i+8]; out.append(0)
        out.extend(chunk)
    return bytes(out)

class Gen3Tests(unittest.TestCase):
    def test_lz77_literal(self):
        raw=bytes(range(64))
        self.assertEqual(_lz77(lz_literal(raw),0),raw)

    def test_sprite_png_dimensions_and_alpha(self):
        pal=[(0,0,0,0)]+[(i*10,i*10,i*10,255) for i in range(1,16)]
        img=_sprite_image(bytes([0x11])*32*4,pal,width=16)
        self.assertEqual(img.size,(16,16))
        self.assertEqual(img.getpixel((0,0))[3],255)

    def test_detect_profile_code(self):
        data=bytearray(0x1000); data[0xAC:0xB0]=b'BPRE'
        rom=SimpleNamespace(data=bytes(data),path=Path('test.gba'))
        self.assertEqual(scan_pokemon_gen3(rom)['profile'],'pokemon_gen3')

    def test_bpre_scan_with_progress_callback(self):
        data=bytearray(0x1000); data[0xAC:0xB0]=b'BPRE'
        rom=SimpleNamespace(data=bytes(data),path=Path('test.gba'),header_info=lambda: {'game_code':'BPRE'})
        progress=[]
        result=run_full_auto_scan(rom, progress_callback=lambda *args: progress.append(args))
        self.assertEqual(result['profile'], 'pokemon_gen3')
        self.assertEqual(progress[0][0], 'Pokémon FireRed profile')
        self.assertEqual(progress[-1][1], 100)

if __name__=='__main__': unittest.main()

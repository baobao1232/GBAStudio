import tempfile
import unittest
from pathlib import Path
from gba_studio.auto_extractor import decompress_rle30, run_full_auto_scan, export_full_auto_scan, scan_rom_pointers
from gba_studio.graphics import decode_tiles
from gba_studio.rom import GbaRom

class V9Tests(unittest.TestCase):
    def test_rle_decoder(self):
        # 0x82 => repeat next byte five times
        result = decompress_rle30(bytes([0x30, 5, 0, 0, 0x82, 0x7A]))
        self.assertEqual(result['data'], b'\x7a' * 5)

    def test_4bpp_decode(self):
        self.assertEqual(decode_tiles(bytes([0x21]) + bytes(31), 4)[0][:2], [1, 2])

    def test_pointer_table_discovery(self):
        data = bytearray(0x400)
        for i, target in enumerate((0x08000100, 0x08000120, 0x08000140)):
            data[0x20 + i*4:0x24 + i*4] = target.to_bytes(4, 'little')
        found = scan_rom_pointers(bytes(data))
        self.assertEqual(found['reference_count'], 3)
        self.assertEqual(found['table_count'], 1)
        self.assertEqual(found['tables'][0]['start'], 0x20)

    def test_rom_header_load(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'test.gba'
            data = bytearray(0xC0 + 64)
            data[0xA0:0xAC] = b'TEST GAME   '
            data[0xAC:0xB0] = b'TEST'
            p.write_bytes(data)
            rom = GbaRom(p)
            self.assertEqual(rom.header_info()['game_code'], 'TEST')

if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from gba_studio.extended_assets import extract_text_candidates, extract_map_candidates, extract_audio_candidates

class ExtendedAssetTests(unittest.TestCase):
    def test_ascii_text_extraction(self):
        data = b'\x00Hello GBA world!\x00' + b'\xff' * 32
        with tempfile.TemporaryDirectory() as td:
            count = extract_text_candidates(data, Path(td))
            self.assertGreaterEqual(count, 1)
            text = (Path(td) / 'Text' / 'text_strings.txt').read_text(encoding='utf-8')
            self.assertIn('Hello GBA world!', text)

    def test_map_candidate_export(self):
        # A repeated tile-index block with plausible tilemap-like distribution.
        import struct
        vals = [(i % 32) + 1 for i in range(1024)]
        data = struct.pack('<1024H', *vals)
        with tempfile.TemporaryDirectory() as td:
            count = extract_map_candidates(data, Path(td))
            self.assertGreaterEqual(count, 1)
            self.assertTrue(list((Path(td) / 'Maps' / 'Tilemap_Candidates').glob('*.bin')))

    def test_embedded_wav_detection(self):
        import struct
        wav = b'RIFF' + struct.pack('<I', 4) + b'WAVE'
        data = b'\x00' * 20 + wav + b'\x00' * 20
        with tempfile.TemporaryDirectory() as td:
            extract_audio_candidates(data, Path(td))
            self.assertTrue(list((Path(td) / 'Audio').glob('*.wav')))

if __name__ == '__main__':
    unittest.main()

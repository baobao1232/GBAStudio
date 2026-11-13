import json
import tempfile
import unittest
from pathlib import Path

from gba_studio.candidate_workbench import analyze_candidate_file, mark_candidate_confirmed


class CandidateWorkbenchTests(unittest.TestCase):
    def test_candidate_can_be_rescanned_and_keeps_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'candidate_001.bin'
            source.write_bytes(bytes((i * 37) & 0xFF for i in range(4096)))
            result = analyze_candidate_file(source, root / 'deep')
            manifest = json.loads((root / 'deep' / 'candidate_analysis.json').read_text())
            self.assertEqual(manifest['source_candidate'], str(source))
            self.assertTrue((root / 'deep' / 'Source' / source.name).exists())
            self.assertIn('nested_compressed_streams', result['summary'])

    def test_user_can_mark_candidate_confirmed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'sprite.bin'
            source.write_bytes(b'asset-data')
            target = mark_candidate_confirmed(source, root / 'export')
            self.assertTrue(target.exists())
            self.assertIn('user_confirmed', (root / 'export' / 'Reviewed_Assets' / 'reviewed_assets.csv').read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()

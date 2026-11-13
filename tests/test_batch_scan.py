import tempfile
import unittest
from pathlib import Path

from gba_studio.candidate_workbench import run_iterative_scan


class BatchScanTests(unittest.TestCase):
    def test_seed_files_are_queued_and_scanned_without_manual_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'root.gba'
            candidate_a = root / 'MapCandidate_001.bin'
            candidate_b = root / 'GraphicsCandidate_002.bin'
            source.write_bytes(bytes(range(256)) * 2)
            candidate_a.write_bytes(bytes(reversed(range(256))))
            candidate_b.write_bytes(b'GBA-CANDIDATE-' * 20)
            result = run_iterative_scan(source, root / 'project', max_depth=0,
                                        max_nodes=10, max_file_bytes=4096,
                                        seed_files=[candidate_a, candidate_b])
            self.assertEqual(result['batch_seeded'], 2)
            kinds = {n['kind'] for n in result['nodes']}
            self.assertIn('BATCH_CANDIDATE', kinds)
            self.assertEqual(result['stats']['nodes_total'], 3)


if __name__ == '__main__':
    unittest.main()

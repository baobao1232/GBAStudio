import json, tempfile, unittest
from pathlib import Path
from gba_studio.candidate_workbench import run_iterative_scan

class IterativeScanTests(unittest.TestCase):
    def test_large_source_is_split_into_scannable_segments(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); rom=root/'larger.gba'; rom.write_bytes(bytes(range(256))*32)
            result=run_iterative_scan(rom, root/'seg_project', max_depth=0, max_nodes=4, max_file_bytes=2048)
            chunks=list((root/'seg_project'/'SourceChunks').glob('*.bin'))
            self.assertEqual(len(chunks),4)
            self.assertTrue(Path(result['project_file']).exists())

    def test_scan_project_is_persisted_and_resumable(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); rom=root/'tiny.gba'
            # A small synthetic GBA-like region with deterministic binary content.
            rom.write_bytes(bytes((i*73+19)&255 for i in range(2048)))
            result=run_iterative_scan(rom, root/'project', max_depth=1, max_nodes=8)
            project=Path(result['project_file'])
            self.assertTrue(project.exists())
            db=json.loads(project.read_text())
            self.assertEqual(db['source_rom'], str(rom.resolve()))
            self.assertTrue(db['nodes'])
            self.assertIn('sha256', db['nodes'][0])
            # Reopening the same project must retain node identity and source provenance.
            ids=[n['id'] for n in db['nodes']]
            again=run_iterative_scan(rom, root/'project', max_depth=1, max_nodes=8)
            db2=json.loads(project.read_text())
            self.assertEqual(ids, [n['id'] for n in db2['nodes'][:len(ids)]])
            self.assertEqual(again['project_file'], str(project))

if __name__=='__main__': unittest.main()

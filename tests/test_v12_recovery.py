import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gba_studio.candidate_workbench import run_iterative_scan


class V12RecoveryTests(unittest.TestCase):
    def test_failed_candidate_is_not_marked_processed_and_can_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / 'candidate.bin'
            candidate.write_bytes(bytes((i * 29 + 7) & 255 for i in range(1024)))
            project = root / 'project'
            with patch('gba_studio.candidate_workbench.analyze_candidate_file', side_effect=RuntimeError('simulated scan failure')):
                first = run_iterative_scan(candidate, project, max_depth=0, max_nodes=4)
            db = json.loads(Path(first['project_file']).read_text(encoding='utf-8'))
            digest = db['nodes'][0]['sha256']
            self.assertEqual(db['nodes'][0]['status'], 'error')
            self.assertNotIn(digest, db['processed_hashes'])

            def fake_analyze(source, out, max_depth=0):
                out.mkdir(parents=True, exist_ok=True)
                return {'directory': str(out), 'summary': {
                    'pointer_references': 0, 'pointer_tables': 0,
                    'nested_compressed_streams': 0, 'graphics_candidates': 0,
                }}

            with patch('gba_studio.candidate_workbench.analyze_candidate_file', side_effect=fake_analyze):
                second = run_iterative_scan(candidate, project, max_depth=0, max_nodes=4)
            db2 = json.loads(Path(second['project_file']).read_text(encoding='utf-8'))
            self.assertTrue(any(n['status'] == 'scanned' and n['sha256'] == digest for n in db2['nodes']))
            self.assertIn(digest, db2['processed_hashes'])


    def test_legacy_error_hash_is_retried_after_reselecting_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / 'reselected_candidate.bin'
            data = bytes((i * 17 + 3) & 255 for i in range(512))
            candidate.write_bytes(data)
            import hashlib
            digest = hashlib.sha256(data).hexdigest()
            project = root / 'old_project'
            project.mkdir()
            legacy = {
                'schema': 1,
                'source_rom': str(root / 'old_missing_path.bin'),
                'nodes': [{'id': 'N000001', 'parent_id': None, 'kind': 'ROM_ROOT',
                           'depth': 0, 'file': str(root / 'old_missing_path.bin'),
                           'size': len(data), 'sha256': digest, 'status': 'error',
                           'error': 'FileNotFoundError'}],
                'edges': [], 'processed_hashes': {digest: 'N000001'},
                'queue': [], 'limits': {'max_depth': 3, 'max_nodes': 80},
            }
            (project / 'scan_project.json').write_text(json.dumps(legacy), encoding='utf-8')

            def fake_analyze(source, out, max_depth=0):
                out.mkdir(parents=True, exist_ok=True)
                return {'directory': str(out), 'summary': {
                    'pointer_references': 0, 'pointer_tables': 0,
                    'nested_compressed_streams': 0, 'graphics_candidates': 0,
                }}

            with patch('gba_studio.candidate_workbench.analyze_candidate_file', side_effect=fake_analyze):
                result = run_iterative_scan(candidate, project, max_depth=0, max_nodes=4)
            db = json.loads(Path(result['project_file']).read_text(encoding='utf-8'))
            self.assertTrue(any(n.get('status') == 'scanned' and n.get('sha256') == digest for n in db['nodes']))
            self.assertEqual(db['source_rom'], str(candidate.resolve()))

    def test_missing_input_fails_with_actionable_message(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / 'gone.bin'
            with self.assertRaisesRegex(FileNotFoundError, 'Hãy chọn lại ROM hoặc Candidate'):
                run_iterative_scan(missing, Path(td) / 'project')


if __name__ == '__main__':
    unittest.main()

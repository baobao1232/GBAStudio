import tempfile, unittest, json
from pathlib import Path
from gba_studio.correlation import correlate_discoveries

class CorrelationTests(unittest.TestCase):
    def test_correlation_report_created(self):
        with tempfile.TemporaryDirectory() as td:
            report=correlate_discoveries({'references':[{'target':100}], 'reference_count':1},
                [{'offset':120,'format':'LZ77','decoded_size':64}], [{'offset':90}],
                {'4':[{'offset':105,'score':2}]}, td)
            self.assertEqual(len(report['graphics_relationships']),1)
            self.assertTrue((Path(td)/'candidate_correlations.csv').exists())

if __name__=='__main__': unittest.main()

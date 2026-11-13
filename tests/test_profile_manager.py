import tempfile, unittest, json
from pathlib import Path
from gba_studio.profile_manager import build_profile, save_profile, load_profile, scan_rom_with_profile, import_profile

class ProfileManagerTests(unittest.TestCase):
    def test_build_save_load_and_scan_exact_signature(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); sample=root/'sample.bin'; sample.write_bytes(b'\x00'*8+b'GBA_ASSET_SIGNATURE_123456'+b'\x00'*8)
            profile=build_profile(sample,'Example sprite','sprite','TEST','Example Game')
            saved=save_profile(profile,root/'profiles')
            loaded=load_profile(saved)
            matches=scan_rom_with_profile(b'abc'+sample.read_bytes()+b'xyz',loaded,'TEST')
            self.assertEqual(len(matches),1)
            self.assertEqual(matches[0]['offset'],3)
            self.assertEqual(scan_rom_with_profile(b'abc'+sample.read_bytes(), loaded, 'NOPE'), [])

    def test_bad_signature_checksum_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'sample.bin'; p.write_bytes(b'A'*64)
            profile=build_profile(p,'sample','other')
            profile['sample']['signature_hex']='42'*32
            with self.assertRaises(ValueError):
                from gba_studio.profile_manager import validate_profile
                validate_profile(profile)

if __name__=='__main__': unittest.main()

import unittest
import os
import shutil
import tempfile
from pathlib import Path
from utils import (
    format_size, validate_quality, FileResult, 
    parse_size_to_bytes, collect_files, SUPPORTED_FORMATS
)

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_format_size(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(2048), "2.0 KB")
        self.assertEqual(format_size(1048576), "1.0 MB")
        self.assertEqual(format_size(1024 * 1024 * 1024), "1.00 GB")

    def test_parse_size_to_bytes(self):
        self.assertEqual(parse_size_to_bytes("500"), 500 * 1024)
        self.assertEqual(parse_size_to_bytes("1MB"), 1024 * 1024)
        self.assertEqual(parse_size_to_bytes("1.5 GB"), int(1.5 * 1024 * 1024 * 1024))
        self.assertEqual(parse_size_to_bytes("100B"), 100)
        self.assertIsNone(parse_size_to_bytes(None))

    def test_validate_quality(self):
        self.assertTrue(validate_quality(50))
        self.assertTrue(validate_quality(100))
        self.assertTrue(validate_quality(1))
        self.assertFalse(validate_quality(0))
        self.assertFalse(validate_quality(101))

    def test_file_result(self):
        result = FileResult('success', 'test', 100, 50)
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.original_size, 100)
        self.assertEqual(result.new_size, 50)

    def test_collect_files(self):
        # 建立測試目錄結構
        (self.test_dir / "img1.jpg").touch()
        (self.test_dir / "img2.png").touch()
        (self.test_dir / "text.txt").touch()
        (self.test_dir / ".hidden").mkdir()
        (self.test_dir / ".hidden" / "img3.jpg").touch()
        (self.test_dir / "subdir").mkdir()
        (self.test_dir / "subdir" / "img4.webp").touch()

        files = collect_files(self.test_dir, SUPPORTED_FORMATS)
        file_names = {f.name for f in files}
        
        self.assertIn("img1.jpg", file_names)
        self.assertIn("img2.png", file_names)
        self.assertIn("img4.webp", file_names)
        self.assertNotIn("text.txt", file_names)
        self.assertNotIn("img3.jpg", file_names) # 隱藏目錄應被跳過

    def test_collect_files_max_depth(self):
        (self.test_dir / "img1.jpg").touch()
        subdir = self.test_dir / "level1"
        subdir.mkdir()
        (subdir / "img2.jpg").touch()
        subsubdir = subdir / "level2"
        subsubdir.mkdir()
        (subsubdir / "img3.jpg").touch()

        files_d0 = collect_files(self.test_dir, SUPPORTED_FORMATS, max_depth=0)
        self.assertEqual(len(files_d0), 1)

        files_d1 = collect_files(self.test_dir, SUPPORTED_FORMATS, max_depth=1)
        self.assertEqual(len(files_d1), 2)

if __name__ == '__main__':
    unittest.main()

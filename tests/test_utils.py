import unittest
from pathlib import Path
from utils import format_size, validate_quality, FileResult

class TestUtils(unittest.TestCase):
    def test_format_size(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(2048), "2.0 KB")
        self.assertEqual(format_size(1048576 * 1.5), "1.5 MB")

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

if __name__ == '__main__':
    unittest.main()

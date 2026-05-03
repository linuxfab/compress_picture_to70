import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from compress_images import compress_image
from images_to_webp import convert_to_webp
from utils import FileResult

class TestImageLogic(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path("/mock/root")
        self.filepath = self.root_dir / "test.jpg"
        self.out_dir = Path("/mock/out")

    @patch("compress_images.Image.open")
    @patch("compress_images.Path.mkdir")
    @patch("compress_images.Path.stat")
    @patch("compress_images.os.utime")
    @patch("compress_images.Path.unlink")
    @patch("compress_images.Path.rename")
    @patch("compress_images.Path.exists")
    def test_compress_image_success(self, mock_exists, mock_rename, mock_unlink, mock_utime, mock_stat, mock_mkdir, mock_image_open):
        # 設定 Mock
        mock_img = MagicMock()
        mock_img.info = {}
        mock_img.mode = 'RGB'
        mock_image_open.return_value = mock_img
        
        mock_exists.return_value = False
        
        # 模擬 stat
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 1000
        mock_stat_val.st_atime = 123456
        mock_stat_val.st_mtime = 123456
        mock_stat.return_value = mock_stat_val

        # 模擬儲存後變小 (temp_path.stat().st_size)
        # 注意: compress_image 會呼叫多次 stat, 所以要用 side_effect 或分開 patch
        with patch("compress_images.Path.with_suffix") as mock_with_suffix:
            mock_temp = MagicMock()
            mock_temp.stat.return_value.st_size = 500
            mock_temp.exists.return_value = False
            mock_with_suffix.return_value = mock_temp
            
            result = compress_image(
                self.filepath, self.root_dir, self.out_dir,
                quality=70, overwrite=True, keep_exif=False, dry_run=False
            )

        if result.status == 'failed':
            print(f"DEBUG: Error message: {result.message}")

        self.assertEqual(result.status, 'success')
        self.assertEqual(result.original_size, 1000)
        self.assertEqual(result.new_size, 500)
        mock_img.save.assert_called()
        mock_utime.assert_called()

    @patch("images_to_webp.Image.open")
    @patch("images_to_webp.Path.mkdir")
    @patch("images_to_webp.Path.stat")
    @patch("images_to_webp.os.utime")
    def test_convert_to_webp_success(self, mock_utime, mock_stat, mock_mkdir, mock_image_open):
        mock_img = MagicMock()
        mock_img.info = {}
        mock_img.mode = 'RGB'
        mock_image_open.return_value = mock_img
        
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 1000
        mock_stat_val.st_atime = 123456
        mock_stat_val.st_mtime = 123456
        mock_stat.return_value = mock_stat_val
        
        # 模擬 target_path
        with patch("images_to_webp.Path.exists", return_value=False):
            result = convert_to_webp(
                self.filepath, self.root_dir, self.out_dir,
                quality=80, overwrite=True, dry_run=False, lossless=False, keep_exif=False
            )

        self.assertEqual(result.status, 'success')
        mock_img.save.assert_called()
        mock_utime.assert_called()

if __name__ == '__main__':
    unittest.main()

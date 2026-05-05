import unittest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from utils import process_image_core, FileResult
import io

class TestImageLogic(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path("/mock/root")
        self.filepath = self.root_dir / "test.jpg"
        self.target_path = Path("/mock/out/test.jpg")

    @patch("utils.Image.open")
    @patch("utils.Path.stat")
    @patch("utils.os.utime")
    @patch("utils.open", new_callable=mock_open)
    @patch("utils.Path.mkdir")
    def test_process_image_core_success(self, mock_mkdir, mock_file_open, mock_utime, mock_stat, mock_image_open):
        # 模擬圖片
        mock_img = MagicMock()
        mock_img.info = {}
        mock_img.mode = 'RGB'
        mock_img.width = 100
        mock_img.height = 100
        mock_image_open.return_value = mock_img
        
        # 模擬檔案大小
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 1000
        mock_stat_val.st_atime = 123456
        mock_stat_val.st_mtime = 123456
        mock_stat.return_value = mock_stat_val

        # 模擬儲存到 BytesIO
        def mock_save(buf, format=None, **kwargs):
            buf.write(b"fake image data")
        mock_img.save.side_effect = mock_save

        result = process_image_core(
            filepath=self.filepath,
            target_path=self.target_path,
            quality=70,
            keep_exif=True,
            scale=1.0,
            output_format='JPEG'
        )

        self.assertEqual(result.status, 'success')
        self.assertEqual(result.original_size, 1000)
        self.assertGreater(result.new_size, 0)
        mock_img.save.assert_called()
        mock_file_open.assert_called_with(self.target_path, 'wb')
        mock_utime.assert_called()

    @patch("utils.Image.open")
    @patch("utils.Path.stat")
    def test_process_image_core_size_skip(self, mock_stat, mock_image_open):
        mock_img = MagicMock()
        mock_img.info = {}
        mock_img.mode = 'RGB'
        mock_image_open.return_value = mock_img
        
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 10 # 很小的原始大小
        mock_stat.return_value = mock_stat_val

        # 模擬儲存後變大
        def mock_save(buf, format=None, **kwargs):
            buf.write(b"this is definitely larger than 10 bytes")
        mock_img.save.side_effect = mock_save

        result = process_image_core(
            filepath=self.filepath,
            target_path=self.target_path,
            quality=70,
            skip_if_larger=True
        )

        self.assertEqual(result.status, 'size_skip')

if __name__ == '__main__':
    unittest.main()

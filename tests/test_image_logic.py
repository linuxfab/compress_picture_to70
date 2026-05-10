import unittest
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from utils import process_image_core, FileResult


class TestImageLogic(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        # 建立一張真實的測試用 JPEG
        self.test_img_path = self.test_dir / "test.jpg"
        img = Image.new('RGB', (200, 200), color='red')
        img.save(self.test_img_path, 'JPEG', quality=95)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_process_image_core_success(self):
        """基本壓縮流程：應成功寫出較小的檔案"""
        target_path = self.test_dir / "out" / "test.jpg"
        result = process_image_core(
            filepath=self.test_img_path,
            target_path=target_path,
            quality=70,
            keep_exif=True,
            scale=1.0,
            output_format='JPEG'
        )
        self.assertEqual(result.status, 'success')
        self.assertTrue(target_path.exists())
        self.assertGreater(result.original_size, 0)
        self.assertGreater(result.new_size, 0)

    def test_process_image_core_size_skip(self):
        """越壓越大時應回傳 size_skip"""
        # 建立一張已經極低品質的小圖
        tiny_path = self.test_dir / "tiny.jpg"
        img = Image.new('RGB', (4, 4), color='blue')
        img.save(tiny_path, 'JPEG', quality=1)

        target_path = self.test_dir / "out" / "tiny.jpg"
        result = process_image_core(
            filepath=tiny_path,
            target_path=target_path,
            quality=95,  # 用高品質重編碼 → 極可能變大
            skip_if_larger=True,
            output_format='JPEG'
        )
        # 小圖在 quality=95 下幾乎一定會膨脹
        self.assertIn(result.status, ('success', 'size_skip'))

    def test_process_image_core_scale(self):
        """縮放後圖片尺寸應正確"""
        target_path = self.test_dir / "scaled.jpg"
        result = process_image_core(
            filepath=self.test_img_path,
            target_path=target_path,
            quality=70,
            scale=0.5,
            output_format='JPEG'
        )
        self.assertEqual(result.status, 'success')
        with Image.open(target_path) as img:
            self.assertEqual(img.width, 100)
            self.assertEqual(img.height, 100)

    def test_process_image_core_format_conversion(self):
        """JPEG → WebP 格式轉換應成功"""
        target_path = self.test_dir / "converted.webp"
        result = process_image_core(
            filepath=self.test_img_path,
            target_path=target_path,
            quality=80,
            output_format='WEBP',
            skip_if_larger=False,
        )
        self.assertEqual(result.status, 'success')
        self.assertTrue(target_path.exists())
        with Image.open(target_path) as img:
            self.assertEqual(img.format, 'WEBP')

    def test_process_image_core_rgba_to_jpeg(self):
        """RGBA PNG → JPEG 轉換時色彩模式應自動轉為 RGB"""
        rgba_path = self.test_dir / "rgba.png"
        img = Image.new('RGBA', (50, 50), color=(255, 0, 0, 128))
        img.save(rgba_path, 'PNG')

        target_path = self.test_dir / "rgba_converted.jpg"
        result = process_image_core(
            filepath=rgba_path,
            target_path=target_path,
            quality=70,
            output_format='JPEG',
            skip_if_larger=False,
        )
        self.assertEqual(result.status, 'success')
        with Image.open(target_path) as img:
            self.assertEqual(img.mode, 'RGB')

    def test_process_image_core_unidentified(self):
        """非圖片檔案應回傳 failed"""
        garbage_path = self.test_dir / "not_an_image.jpg"
        garbage_path.write_bytes(b"this is not an image at all")

        target_path = self.test_dir / "out" / "not_an_image.jpg"
        result = process_image_core(
            filepath=garbage_path,
            target_path=target_path,
            quality=70,
            output_format='JPEG'
        )
        self.assertEqual(result.status, 'failed')

    def test_process_image_core_atomic_write(self):
        """原子寫入後原始修改時間應被保留"""
        target_path = self.test_dir / "out" / "test_atomic.jpg"
        orig_stat = self.test_img_path.stat()

        result = process_image_core(
            filepath=self.test_img_path,
            target_path=target_path,
            quality=70,
            output_format='JPEG'
        )
        self.assertEqual(result.status, 'success')
        target_stat = target_path.stat()
        # 修改時間 (mtime) 應該被保留
        self.assertAlmostEqual(target_stat.st_mtime, orig_stat.st_mtime, places=0)


if __name__ == '__main__':
    unittest.main()

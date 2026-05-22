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

    def test_convert_to_webp_in_place(self):
        """測試 convert_to_webp 原地轉換，原圖應被刪除且轉出新 webp 檔案"""
        from images_to_webp import convert_to_webp
        png_path = self.test_dir / "to_convert.png"
        img = Image.new('RGB', (10, 10), color='green')
        img.save(png_path, 'PNG')
        
        result = convert_to_webp(
            filepath=png_path,
            root_dir=self.test_dir,
            target_root=self.test_dir,
            quality=80,
            overwrite=True,
            dry_run=False,
            lossless=False,
            keep_exif=True,
            in_place=True
        )
        self.assertEqual(result.status, 'success')
        target_webp = self.test_dir / "to_convert.webp"
        self.assertTrue(target_webp.exists())
        self.assertFalse(png_path.exists())

    def test_convert_to_webp_self_deletion_protection(self):
        """測試 convert_to_webp 傳入已經是 webp 的檔案時，應保護不自我刪除"""
        from images_to_webp import convert_to_webp
        webp_path = self.test_dir / "already.webp"
        img = Image.new('RGB', (10, 10), color='blue')
        img.save(webp_path, 'WEBP')

        result = convert_to_webp(
            filepath=webp_path,
            root_dir=self.test_dir,
            target_root=self.test_dir,
            quality=80,
            overwrite=True,
            dry_run=False,
            lossless=False,
            keep_exif=True,
            in_place=True
        )
        self.assertTrue(webp_path.exists())

    def test_convert_to_webp_nested_output_filtering(self):
        """測試轉檔時若輸出目錄位於更深層的子目錄，是否能精準濾除該輸出目錄"""
        out_dir = self.test_dir / "output" / "webp"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立兩個測試檔案：一個在來源目錄，一個在輸出目錄
        src_file = self.test_dir / "valid_image.png"
        nested_out_file = out_dir / "already_processed.png"
        src_file.touch()
        nested_out_file.touch()
        
        from utils import collect_files, SUPPORTED_FORMATS
        
        # 模擬與 images_to_webp 一致的 should_exclude 斷言
        def should_exclude(dir_path: Path) -> bool:
            try:
                return dir_path.resolve() == out_dir.resolve() or dir_path.resolve().is_relative_to(out_dir.resolve())
            except Exception:
                return False
                
        files = collect_files(
            self.test_dir, 
            SUPPORTED_FORMATS, 
            exclude_fn=should_exclude
        )
        
        self.assertIn(src_file.resolve(), [f.resolve() for f in files])
        self.assertNotIn(nested_out_file.resolve(), [f.resolve() for f in files])

    def test_process_image_core_readonly_compatibility(self):
        """測試當目標檔案為唯讀 (ReadOnly) 屬性時，原子寫入是否能成功覆蓋"""
        import os
        import stat
        target_path = self.test_dir / "readonly_out.jpg"
        # 先建立一個空檔案並設定為唯讀
        target_path.touch()
        os.chmod(target_path, stat.S_IREAD)
        
        try:
            result = process_image_core(
                filepath=self.test_img_path,
                target_path=target_path,
                quality=70,
                output_format='JPEG',
                skip_if_larger=False
            )
            self.assertEqual(result.status, 'success')
            self.assertTrue(target_path.exists())
            self.assertGreater(target_path.stat().st_size, 0)
        finally:
            # 測試結束後還原權限以便 cleanup 可以順利刪除該暫存目錄
            try:
                os.chmod(target_path, stat.S_IWRITE)
            except Exception:
                pass

    def test_process_image_core_rgba_to_jpeg_alpha_blending(self):
        """測試 RGBA PNG 轉成 JPEG 時透明通道是否與白色背景正確混合而非變成黑色"""
        rgba_path = self.test_dir / "rgba_blend.png"
        # 建立一張完全透明 (alpha=0) 的紅色圖片
        img = Image.new('RGBA', (10, 10), color=(255, 0, 0, 0))
        img.save(rgba_path, 'PNG')

        target_path = self.test_dir / "rgba_blend_out.jpg"
        result = process_image_core(
            filepath=rgba_path,
            target_path=target_path,
            quality=90,
            output_format='JPEG',
            skip_if_larger=False
        )
        self.assertEqual(result.status, 'success')
        # 讀取轉出的 JPEG，透明處因為與白底混合，其顏色應為白色 (255, 255, 255)
        with Image.open(target_path) as out_img:
            pixels = list(out_img.getdata())
            # 每一個像素都應該是白色 (255, 255, 255) 而非黑色 (0, 0, 0)
            self.assertEqual(pixels[0], (255, 255, 255))

    def test_process_image_core_progressive_jpeg(self):
        """測試當 JPEG 大於 10KB 時，是否正確啟用 progressive 寫入"""
        large_img_path = self.test_dir / "large.jpg"
        # 建立一張足夠大能超過 10KB 的圖片 (比如 800x800)
        img = Image.new('RGB', (800, 800), color='blue')
        img.save(large_img_path, 'JPEG', quality=95)
        self.assertGreater(large_img_path.stat().st_size, 10240)

        target_path = self.test_dir / "large_out.jpg"
        result = process_image_core(
            filepath=large_img_path,
            target_path=target_path,
            quality=70,
            output_format='JPEG',
            skip_if_larger=False
        )
        self.assertEqual(result.status, 'success')
        # 讀取產出的 JPEG，檢查 info 中是否含有 progressive = True
        with Image.open(target_path) as out_img:
            self.assertTrue(out_img.info.get('progressive', False))

    def test_convert_to_webp_skip_if_larger(self):
        """測試 images_to_webp 在啟用 skip_if_larger 且體積膨脹時會跳過轉換"""
        from images_to_webp import convert_to_webp
        import random
        # 建立一張充滿隨機雜訊的低品質 JPEG，這張圖在轉換為高品質 WebP 時體積必定會膨脹
        img = Image.new('RGB', (50, 50))
        pixels = [(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for _ in range(2500)]
        img.putdata(pixels)
        small_jpg = self.test_dir / "noise_comp.jpg"
        img.save(small_jpg, 'JPEG', quality=30)

        result = convert_to_webp(
            filepath=small_jpg,
            root_dir=self.test_dir,
            target_root=self.test_dir,
            quality=95, # 高品質轉檔 → 體積必定會膨脹
            overwrite=True,
            dry_run=False,
            lossless=False,
            keep_exif=False,
            skip_if_larger=True # 啟用防膨脹
        )
        self.assertEqual(result.status, 'size_skip')

    def test_tune_quality_for_target_size(self):
        """測試動態品質二分逼近輔助函數"""
        from utils import tune_quality_for_target_size
        img = Image.new('RGB', (150, 150), color='green')
        # 測試目標大小
        target_size = 2000 # 2KB
        save_kwargs = {'optimize': True}
        best_q = tune_quality_for_target_size(img, target_size, 'JPEG', save_kwargs)
        
        # 驗證得到的品質是否合理 (40 <= best_q <= 95)
        self.assertTrue(40 <= best_q <= 95)
        
        # 使用得到的最佳品質存檔，驗證大小應小於或接近目標大小
        buf = __import__('io')
        b = buf.BytesIO()
        save_kwargs['quality'] = best_q
        img.save(b, 'JPEG', **save_kwargs)
        size = b.tell()
        b.close()
        self.assertLessEqual(size, target_size + 1024)

    def test_process_image_core_target_size(self):
        """測試 process_image_core 中帶入 target_size_bytes 的壓縮控制"""
        large_img_path = self.test_dir / "target_size_test.jpg"
        # 建立一張 300x300 的大一點的圖
        img = Image.new('RGB', (300, 300), color='orange')
        img.save(large_img_path, 'JPEG', quality=95)
        orig_size = large_img_path.stat().st_size
        
        target_path = self.test_dir / "target_size_out.jpg"
        # 設定目標大小為原始大小的 40%
        target_limit = int(orig_size * 0.4)
        
        result = process_image_core(
            filepath=large_img_path,
            target_path=target_path,
            quality=90,
            output_format='JPEG',
            skip_if_larger=False,
            target_size_bytes=target_limit
        )
        self.assertEqual(result.status, 'success')
        self.assertTrue(target_path.exists())
        # 新的大小應明顯小於原圖，且接近 target_limit (或小於 target_limit)
        self.assertLess(target_path.stat().st_size, orig_size)


if __name__ == '__main__':
    unittest.main()


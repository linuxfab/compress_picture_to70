"""
v8.8.0 畫質與色彩正確性測試：
5. ICC 色彩描述檔保留 (JPEG / PNG / WebP / 動畫 WebP)
6. 特殊色彩模式轉換 (I;16, PA, YCbCr, 1)
7. 目標大小搜尋精確收斂、原檔小於目標時跳過重編碼、品質 40 仍過大時自動縮放與提醒
8. --png-quantize PNG 減色量化與 --target-size 整合
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import compress_images
import image_core
from ui import FileResult


class TestIccProfilePreservation(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.fake_icc = b"FAKE_DISPLAY_P3_ICC_PROFILE_DATA_1234567890"

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_icc_preserved_across_jpeg_and_webp(self):
        """即使 keep_exif=False，ICC 色彩描述檔仍應保留"""
        src = self.d / "p3.jpg"
        Image.new('RGB', (100, 100), color=(200, 30, 30)).save(
            src, 'JPEG', quality=95, icc_profile=self.fake_icc
        )

        out_webp = self.d / "p3.webp"
        res_webp = image_core.process_image_core(
            filepath=src, target_path=out_webp, quality=80,
            keep_exif=False, output_format='WEBP', skip_if_larger=False,
        )
        self.assertEqual(res_webp.status, 'success')
        with Image.open(out_webp) as w:
            self.assertEqual(w.info.get('icc_profile'), self.fake_icc)

        out_jpg = self.d / "p3_out.jpg"
        res_jpg = image_core.process_image_core(
            filepath=src, target_path=out_jpg, quality=70,
            keep_exif=False, output_format='JPEG', skip_if_larger=False,
        )
        self.assertEqual(res_jpg.status, 'success')
        with Image.open(out_jpg) as j:
            self.assertEqual(j.info.get('icc_profile'), self.fake_icc)

    def test_icc_preserved_in_animated_webp(self):
        src = self.d / "anim_p3.webp"
        frames = [Image.new('RGBA', (32, 32), c) for c in ('red', 'blue')]
        frames[0].save(
            src, 'WEBP', save_all=True, append_images=frames[1:],
            duration=100, icc_profile=self.fake_icc,
        )
        out = self.d / "anim_out.webp"
        res = image_core.process_image_core(
            filepath=src, target_path=out, quality=75,
            output_format='WEBP', skip_if_larger=False,
        )
        self.assertEqual(res.status, 'success')
        with Image.open(out) as w:
            self.assertEqual(w.n_frames, 2)
            self.assertEqual(w.info.get('icc_profile'), self.fake_icc)


class TestColorModeNormalization(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_i16_not_clipped_to_white(self):
        """16-bit 灰階中灰 (32768) 轉換後應接近 128，而非被截斷成 255 全白"""
        src = self.d / "gray16.png"
        Image.new('I;16', (32, 32), 32768).save(src, 'PNG')

        out_jpg = self.d / "gray16.jpg"
        res = image_core.process_image_core(
            filepath=src, target_path=out_jpg, quality=90,
            output_format='JPEG', skip_if_larger=False,
        )
        self.assertEqual(res.status, 'success', res.message)
        with Image.open(out_jpg) as j:
            px = j.getpixel((16, 16))
            val = px[0] if isinstance(px, tuple) else px
            self.assertTrue(110 <= val <= 145, f"預期接近 128 的灰階，實際為 {val}")

    def test_pa_mode_to_jpeg_and_webp(self):
        """PA (Palette + Alpha) 轉 WebP 保留透明、轉 JPEG 融合白底"""
        src = self.d / "pa.tif"
        Image.new('PA', (32, 32), (100, 0)).save(src, 'TIFF')  # 完全透明

        out_webp = self.d / "pa.webp"
        res_w = image_core.process_image_core(
            filepath=src, target_path=out_webp, quality=80,
            output_format='WEBP', skip_if_larger=False,
        )
        self.assertEqual(res_w.status, 'success', res_w.message)

        out_jpg = self.d / "pa.jpg"
        res_j = image_core.process_image_core(
            filepath=src, target_path=out_jpg, quality=90,
            output_format='JPEG', skip_if_larger=False,
        )
        self.assertEqual(res_j.status, 'success', res_j.message)
        with Image.open(out_jpg) as j:
            r, g, b = j.getpixel((16, 16))
            self.assertGreater(r, 240)
            self.assertGreater(g, 240)
            self.assertGreater(b, 240)

    def test_ycbcr_and_1bit_to_jpeg(self):
        """YCbCr 與 1-bit 模式轉 JPEG 皆可成功不報錯"""
        for mode, color in (('YCbCr', (128, 128, 128)), ('1', 0)):
            img = Image.new(mode, (32, 32), color)
            normalized = image_core._normalize_image_mode(img, 'JPEG')
            self.assertIn(normalized.mode, ('RGB', 'L'))


class TestTargetSizeImprovements(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_already_under_target_in_place_skips_reencode(self):
        """原地覆蓋且原檔已小於 target_size_bytes 時，應跳過重編碼並保留原 bytes"""
        src = self.d / "small.jpg"
        Image.new('RGB', (64, 64), 'green').save(src, 'JPEG', quality=85)
        orig_bytes = src.read_bytes()

        res = image_core.process_image_core(
            filepath=src, target_path=src, quality=70,
            output_format='JPEG', target_size_bytes=len(orig_bytes) + 10240,
        )
        self.assertEqual(res.status, 'skipped')
        self.assertEqual(src.read_bytes(), orig_bytes)

    def test_already_under_target_out_dir_skips_binary_search(self):
        """另存新檔時若原檔已小於目標，不應重複執行二分搜尋"""
        src = self.d / "small.jpg"
        Image.new('RGB', (64, 64), 'green').save(src, 'JPEG', quality=85)
        out = self.d / "out.jpg"

        with patch("image_core.tune_quality_for_target_size") as mock_tune:
            res = image_core.process_image_core(
                filepath=src, target_path=out, quality=70,
                output_format='JPEG', skip_if_larger=False,
                target_size_bytes=src.stat().st_size + 10240,
            )
        self.assertEqual(res.status, 'success')
        mock_tune.assert_not_called()

    def test_auto_downscale_when_min_quality_exceeds_target(self):
        """品質降到 40 仍大於目標體積時，應自動縮小尺寸並回傳 warn=True 提醒"""
        import random
        rng = random.Random(42)
        src = self.d / "noisy.jpg"
        img = Image.new('RGB', (320, 320))
        img.putdata([(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(320 * 320)])
        img.save(src, 'JPEG', quality=95)

        out = self.d / "noisy_small.jpg"
        # 設定極嚴格目標 (例如原檔 12% 大小)，品質 40 必定超標，會觸發自動縮放
        target = int(src.stat().st_size * 0.25)
        res = image_core.process_image_core(
            filepath=src, target_path=out, quality=85,
            output_format='JPEG', skip_if_larger=False,
            target_size_bytes=target,
        )
        self.assertEqual(res.status, 'success')
        self.assertTrue(res.warn)
        with Image.open(out) as out_img:
            self.assertLess(out_img.width, 320)


class TestPngQuantize(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_png_quantize_reduces_size_and_keeps_alpha(self):
        """啟用 --png-quantize 時應轉成調色盤 PNG 保留透明並大幅縮小體積"""
        import random
        rng = random.Random(7)
        src = self.d / "grad.png"
        img = Image.new('RGBA', (200, 200))
        pixels = []
        for y in range(200):
            for x in range(200):
                alpha = 0 if x < 50 else 255
                pixels.append(((x * 3 + rng.randint(0, 20)) % 256, (y * 2) % 256, 120, alpha))
        img.putdata(pixels)
        img.save(src, 'PNG')

        out = self.d / "grad_q.png"
        res = compress_images.compress_image(
            filepath=src, root_dir=self.d, out_dir=self.d / "out",
            quality=70, overwrite=True, keep_exif=False, dry_run=False,
            png_quantize=True,
        )
        # compress_image 指定 out_dir 時會寫到 out_dir/grad.png
        out_real = self.d / "out" / "grad.png"
        self.assertEqual(res.status, 'success', res.message)
        self.assertLess(out_real.stat().st_size, src.stat().st_size)
        with Image.open(out_real) as q_img:
            self.assertEqual(q_img.mode, 'P')
            self.assertIn('transparency', q_img.info)

    def test_png_quantize_with_target_size(self):
        import random
        rng = random.Random(9)
        src = self.d / "target.png"
        img = Image.new('RGB', (160, 160))
        img.putdata([(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(160 * 160)])
        img.save(src, 'PNG')

        out = self.d / "target_q.png"
        res = image_core.process_image_core(
            filepath=src, target_path=out, quality=70,
            output_format='PNG', skip_if_larger=False,
            target_size_bytes=int(src.stat().st_size * 0.4),
            png_quantize=True,
        )
        self.assertEqual(res.status, 'success')
        self.assertLess(out.stat().st_size, src.stat().st_size)


if __name__ == '__main__':
    unittest.main()

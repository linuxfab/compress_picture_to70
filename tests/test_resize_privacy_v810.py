"""
v8.10.0 新功能測試：
1. --max-dim：限制最長邊像素 (只縮小不放大)，可與 --scale 併用，靜態與動畫皆適用
2. --strip-gps：移除 GPS IFD、保留其餘 EXIF，並自動啟用 --keep-exif
3. 保留 EXIF 時 Orientation 重設為 1，避免像素轉正後被看圖軟體再轉一次
"""

import shutil
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import cli
import compress_images
import images_to_webp
from image_core import (
    EXIF_GPS_IFD_TAG,
    EXIF_ORIENTATION_TAG,
    compute_resize,
    prepare_exif_bytes,
    process_image_core,
)
from ui import build_filter_info

MAKE_TAG = 0x010F
DATETIME_TAG = 0x0132


def _exif_bytes(orientation: int = 1, with_gps: bool = True) -> bytes:
    exif = Image.Exif()
    exif[MAKE_TAG] = 'TestCam'
    exif[DATETIME_TAG] = '2026:11:17 12:00:00'
    if orientation != 1:
        exif[EXIF_ORIENTATION_TAG] = orientation
    if with_gps:
        gps = exif.get_ifd(EXIF_GPS_IFD_TAG)
        gps[1] = 'N'
        gps[2] = (25.0, 2.0, 3.0)
    return exif.tobytes()


class TestComputeResize(unittest.TestCase):
    def test_no_resize_when_within_limit(self):
        self.assertIsNone(compute_resize(800, 600, 1.0, 1920))
        self.assertIsNone(compute_resize(1920, 1080, 1.0, 1920))

    def test_landscape_and_portrait_long_side(self):
        self.assertEqual(compute_resize(4000, 3000, 1.0, 1920), (1920, 1440))
        self.assertEqual(compute_resize(3000, 4000, 1.0, 1920), (1440, 1920))

    def test_combined_with_scale(self):
        # 先 scale 0.5 → 2000x1500，再限制最長邊 1000
        self.assertEqual(compute_resize(4000, 3000, 0.5, 1000), (1000, 750))
        # scale 後已在限制內則只套用 scale
        self.assertEqual(compute_resize(4000, 3000, 0.25, 1920), (1000, 750))

    def test_never_upscale(self):
        self.assertIsNone(compute_resize(100, 50, 1.0, 5000))


class TestPrepareExif(unittest.TestCase):
    def test_strip_gps_keeps_other_tags(self):
        out = prepare_exif_bytes(_exif_bytes(), strip_gps=True)
        exif = Image.Exif()
        exif.load(out)
        self.assertNotIn(EXIF_GPS_IFD_TAG, exif)
        self.assertEqual(exif[MAKE_TAG], 'TestCam')
        self.assertEqual(exif[DATETIME_TAG], '2026:11:17 12:00:00')

    def test_noop_returns_same_bytes(self):
        raw = _exif_bytes()
        self.assertIs(prepare_exif_bytes(raw), raw)
        self.assertIsNone(prepare_exif_bytes(None, strip_gps=True))

    def test_reset_orientation(self):
        out = prepare_exif_bytes(_exif_bytes(orientation=6), reset_orientation=True)
        exif = Image.Exif()
        exif.load(out)
        self.assertEqual(exif[EXIF_ORIENTATION_TAG], 1)

    def test_unparseable_exif_dropped_when_stripping_gps(self):
        self.assertIsNone(prepare_exif_bytes(b'garbage-not-exif', strip_gps=True))


class TestProcessCore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _jpeg(self, name='a.jpg', size=(800, 400), orientation=1):
        p = self.tmp / name
        Image.new('RGB', size, (200, 30, 30)).save(p, exif=_exif_bytes(orientation))
        return p

    def test_max_dim_still_image(self):
        src = self._jpeg(size=(800, 400))
        out = self.tmp / 'out.jpg'
        r = process_image_core(src, out, 70, keep_exif=False, max_dim=200, skip_if_larger=False)
        self.assertEqual(r.status, 'success')
        with Image.open(out) as im:
            self.assertEqual(im.size, (200, 100))

    def test_max_dim_animated_webp(self):
        src = self.tmp / 'anim.webp'
        frames = [Image.new('RGBA', (400, 300), c) for c in ((255, 0, 0, 255), (0, 255, 0, 255))]
        frames[0].save(src, save_all=True, append_images=frames[1:], duration=100, loop=0)
        out = self.tmp / 'anim_out.webp'
        r = process_image_core(src, out, 70, keep_exif=False, output_format='WEBP',
                               max_dim=100, skip_if_larger=False)
        self.assertEqual(r.status, 'success')
        with Image.open(out) as im:
            self.assertEqual(im.size, (100, 75))
            self.assertEqual(im.n_frames, 2)

    def test_max_dim_bypasses_target_size_inplace_skip(self):
        # 原檔已小於目標大小，但尺寸超過 max-dim 時仍須縮圖，不可直接跳過
        src = self._jpeg(size=(800, 400))
        r = process_image_core(src, src, 70, keep_exif=False, max_dim=200,
                               target_size_bytes=10 * 1024 * 1024, skip_if_larger=False)
        self.assertEqual(r.status, 'success')
        with Image.open(src) as im:
            self.assertEqual(im.size, (200, 100))

    def test_strip_gps_end_to_end(self):
        src = self._jpeg()
        out = self.tmp / 'out.jpg'
        r = process_image_core(src, out, 70, keep_exif=True, strip_gps=True, skip_if_larger=False)
        self.assertEqual(r.status, 'success')
        with Image.open(out) as im:
            exif = im.getexif()
            self.assertNotIn(EXIF_GPS_IFD_TAG, exif)
            self.assertEqual(exif[MAKE_TAG], 'TestCam')

    def test_keep_exif_without_strip_keeps_gps(self):
        src = self._jpeg()
        out = self.tmp / 'out.jpg'
        process_image_core(src, out, 70, keep_exif=True, skip_if_larger=False)
        with Image.open(out) as im:
            self.assertIn(EXIF_GPS_IFD_TAG, im.getexif())

    def test_orientation_reset_after_transpose(self):
        # Orientation=6 (順時針轉 90°)：像素轉正後 EXIF 須為 1，否則會被旋轉兩次
        src = self._jpeg(size=(400, 200), orientation=6)
        out = self.tmp / 'out.jpg'
        process_image_core(src, out, 70, keep_exif=True, skip_if_larger=False)
        with Image.open(out) as im:
            self.assertEqual(im.size, (200, 400))
            self.assertEqual(im.getexif().get(EXIF_ORIENTATION_TAG, 1), 1)


class _SyncExecutor:
    """以同步方式執行任務，避免測試中 fork 子程序"""
    def __init__(self, max_workers=1):
        pass

    def submit(self, fn, arg):
        fut: Future = Future()
        try:
            fut.set_result(fn(arg))
        except Exception as e:
            fut.set_exception(e)
        return fut

    def shutdown(self, wait=True, cancel_futures=False):
        pass


@patch("ui.ProcessPoolExecutor", _SyncExecutor)
class TestCliWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        Image.new('RGB', (800, 400), (10, 120, 200)).save(
            self.tmp / 'p.jpg', exif=_exif_bytes(), quality=100,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compress_main_max_dim_and_strip_gps(self):
        compress_images.main([str(self.tmp), '--max-dim', '300', '--strip-gps', '-w', '1'])
        out = self.tmp / 'p_70%.jpg'
        self.assertTrue(out.exists())
        with Image.open(out) as im:
            self.assertEqual(im.size, (300, 150))
            exif = im.getexif()
            # --strip-gps 自動啟用 --keep-exif：相機資訊保留、GPS 移除
            self.assertEqual(exif[MAKE_TAG], 'TestCam')
            self.assertNotIn(EXIF_GPS_IFD_TAG, exif)

    def test_webp_main_max_dim_and_strip_gps(self):
        images_to_webp.main([str(self.tmp), '--max-dim', '300', '--strip-gps', '-w', '1'])
        out = self.tmp / 'webp_output' / 'p.webp'
        self.assertTrue(out.exists())
        with Image.open(out) as im:
            self.assertEqual(im.size, (300, 150))
            exif = im.getexif()
            self.assertEqual(exif[MAKE_TAG], 'TestCam')
            self.assertNotIn(EXIF_GPS_IFD_TAG, exif)

    def test_invalid_max_dim_rejected(self):
        self.assertFalse(cli.validate_max_dim(0))
        self.assertTrue(cli.validate_max_dim(None))
        compress_images.main([str(self.tmp), '--max-dim', '0', '-w', '1'])
        self.assertFalse((self.tmp / 'p_70%.jpg').exists())

    def test_filter_info_shows_new_options(self):
        info = build_filter_info(None, None, 1.0, None, max_dim=1920, strip_gps=True)
        self.assertIn('最長邊 1920px', info)
        self.assertIn('移除 GPS', info)


if __name__ == '__main__':
    unittest.main()

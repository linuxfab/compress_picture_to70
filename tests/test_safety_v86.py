"""
v8.6.0 資料安全修復測試：
1. 同名不同副檔名的輸出衝突 (a.jpg + a.png → a.webp)
2. HEIC 原地轉換不可覆蓋既有 JPG
3. 動畫圖片不可被壓成單格
4. 壓縮工具需排除位於來源內的輸出目錄
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from utils import (
    collect_files, assign_conflict_tags, make_output_dir_excluder,
    process_image_core, SUPPORTED_FORMATS,
)
from compress_images import compress_image, build_target_path, build_suffix
from images_to_webp import convert_to_webp, build_webp_target


def _make_img(path: Path, color: str, fmt: str, size=(64, 64)) -> Path:
    Image.new('RGB', size, color=color).save(path, fmt)
    return path


def _make_animated_webp(path: Path, colors=('red', 'green', 'blue'), size=(32, 32)) -> Path:
    frames = [Image.new('RGBA', size, color=c) for c in colors]
    frames[0].save(
        path, 'WEBP', save_all=True, append_images=frames[1:],
        duration=[100, 200, 300], loop=0, lossless=True,
    )
    return path


class TestConflictTags(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_no_conflict_returns_empty(self):
        a = _make_img(self.d / "a.jpg", 'red', 'JPEG')
        b = _make_img(self.d / "b.png", 'red', 'PNG')
        tags = assign_conflict_tags([a, b], lambda f, t: build_webp_target(f, self.d, self.d, t))
        self.assertEqual(tags, {})

    def test_webp_conflict_all_members_tagged(self):
        """a.jpg + a.png → 沒有天生的 .webp 來源，兩者都要加標籤"""
        a = _make_img(self.d / "a.jpg", 'red', 'JPEG')
        b = _make_img(self.d / "a.png", 'blue', 'PNG')
        fn = lambda f, t: build_webp_target(f, self.d, self.d, t)
        tags = assign_conflict_tags([a, b], fn)
        self.assertEqual(tags, {str(a): 'jpg', str(b): 'png'})
        self.assertEqual(fn(a, tags[str(a)]).name, "a_jpg.webp")
        self.assertEqual(fn(b, tags[str(b)]).name, "a_png.webp")

    def test_case_insensitive_conflict(self):
        """不同大小寫的輸出路徑在 Windows 上是同一個檔案，必須視為衝突"""
        a = self.d / "Photo.jpg"
        b = self.d / "photo.png"
        fn = lambda f, t: build_webp_target(f, self.d, self.d, t)
        tags = assign_conflict_tags([a, b], fn)
        self.assertEqual(len(tags), 2)

    def test_natural_member_keeps_name(self):
        """原地壓縮：IMG.jpg 本來就輸出 IMG.jpg，應保留；IMG.heic 改為 IMG_heic.jpg"""
        jpg = self.d / "IMG.jpg"
        heic = self.d / "IMG.heic"
        fn = lambda f, t: build_target_path(f, self.d, None, True, "", t)
        tags = assign_conflict_tags([heic, jpg], fn)
        self.assertEqual(tags, {str(heic): 'heic'})
        self.assertEqual(fn(heic, 'heic').name, "IMG_heic.jpg")

    def test_tag_collision_gets_counter(self):
        """標籤後的檔名若又撞到其他來源 (a_png.jpg → a_png.webp)，需再加數字"""
        a = self.d / "a.jpg"
        b = self.d / "a.png"
        c = self.d / "a_png.jpg"  # 天生就輸出 a_png.webp
        fn = lambda f, t: build_webp_target(f, self.d, self.d, t)
        tags = assign_conflict_tags([a, b, c], fn)
        finals = {str(fn(f, tags.get(str(f), ''))).lower() for f in (a, b, c)}
        self.assertEqual(len(finals), 3, f"輸出必須唯一: {finals}")
        self.assertEqual(tags[str(b)], 'png2')


class TestWebpInPlaceSafety(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def _convert(self, f, tags=None, overwrite=False):
        return convert_to_webp(
            filepath=f, root_dir=self.d, target_root=self.d, quality=80,
            overwrite=overwrite, dry_run=False, lossless=False, keep_exif=False,
            in_place=True, conflict_tags=tags,
        )

    def test_same_stem_both_preserved(self):
        """a.jpg 與 a.png 原地轉換後，兩張圖片內容都必須保留 (不同檔案)"""
        a = _make_img(self.d / "a.jpg", 'red', 'JPEG')
        b = _make_img(self.d / "a.png", 'blue', 'PNG')
        fn = lambda f, t: build_webp_target(f, self.d, self.d, t)
        tags = assign_conflict_tags([a, b], fn)

        self.assertEqual(self._convert(a, tags).status, 'success')
        self.assertEqual(self._convert(b, tags).status, 'success')

        out_a, out_b = self.d / "a_jpg.webp", self.d / "a_png.webp"
        self.assertTrue(out_a.exists() and out_b.exists())
        self.assertFalse(a.exists() or b.exists())
        with Image.open(out_a) as ia, Image.open(out_b) as ib:
            self.assertGreater(ia.convert('RGB').getpixel((10, 10))[0], 200)  # 紅
            self.assertGreater(ib.convert('RGB').getpixel((10, 10))[2], 200)  # 藍

    def test_existing_webp_not_overwritten_without_flag(self):
        """原地模式下 a.webp 已存在時，不加 -o 應跳過且保留 a.jpg 與 a.webp"""
        existing = _make_img(self.d / "a.webp", 'green', 'WEBP')
        before = existing.read_bytes()
        src = _make_img(self.d / "a.jpg", 'red', 'JPEG')

        result = self._convert(src)
        self.assertEqual(result.status, 'skipped')
        self.assertTrue(result.warn)
        self.assertTrue(src.exists())
        self.assertEqual(existing.read_bytes(), before)

    def test_existing_webp_overwritten_with_flag(self):
        _make_img(self.d / "a.webp", 'green', 'WEBP')
        src = _make_img(self.d / "a.jpg", 'red', 'JPEG')
        self.assertEqual(self._convert(src, overwrite=True).status, 'success')
        self.assertFalse(src.exists())


class TestCompressInPlaceHeicSafety(unittest.TestCase):
    """以 .avif 代替 .heic 測試 (同屬 FORCE_JPEG_EXTS，且 Pillow 可直接寫出測試檔)"""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def _compress(self, f, tags=None, overwrite=False):
        return compress_image(
            filepath=f, root_dir=self.d, out_dir=None, quality=70,
            overwrite=overwrite, keep_exif=False, dry_run=False,
            in_place=True, conflict_tags=tags,
        )

    def test_existing_jpg_not_overwritten(self):
        """IMG.avif 原地轉 IMG.jpg 時，既有 IMG.jpg 不可被覆蓋，IMG.avif 也要保留"""
        jpg = _make_img(self.d / "IMG.jpg", 'blue', 'JPEG')
        before = jpg.read_bytes()
        try:
            src = _make_img(self.d / "IMG.avif", 'red', 'AVIF')
        except Exception as e:  # pragma: no cover - 環境無 AVIF 編碼器
            self.skipTest(f"AVIF 編碼不可用: {e}")

        result = self._compress(src)
        self.assertEqual(result.status, 'skipped')
        self.assertTrue(result.warn)
        self.assertTrue(src.exists())
        self.assertEqual(jpg.read_bytes(), before)

    def test_conflict_tag_produces_separate_file(self):
        jpg = _make_img(self.d / "IMG.jpg", 'blue', 'JPEG', size=(256, 256))
        try:
            src = _make_img(self.d / "IMG.avif", 'red', 'AVIF', size=(256, 256))
        except Exception as e:  # pragma: no cover
            self.skipTest(f"AVIF 編碼不可用: {e}")

        fn = lambda f, t: build_target_path(f, self.d, None, True, "", t)
        tags = assign_conflict_tags([jpg, src], fn)
        self.assertEqual(tags, {str(src): 'avif'})

        result = self._compress(src, tags)
        self.assertEqual(result.status, 'success')
        out = self.d / "IMG_avif.jpg"
        self.assertTrue(out.exists())
        self.assertTrue(jpg.exists())
        self.assertFalse(src.exists())
        with Image.open(jpg) as ij:
            self.assertGreater(ij.getpixel((10, 10))[2], 200)  # 原本的藍色 JPG 未被動到


class TestAnimatedImages(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.anim = _make_animated_webp(self.d / "anim.webp")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_animated_webp_keeps_all_frames(self):
        out = self.d / "out" / "anim.webp"
        result = process_image_core(
            filepath=self.anim, target_path=out, quality=80,
            output_format='WEBP', skip_if_larger=False,
        )
        self.assertEqual(result.status, 'success')
        with Image.open(out) as img:
            self.assertTrue(getattr(img, 'is_animated', False))
            self.assertEqual(img.n_frames, 3)
            colors = []
            for i in range(3):
                img.seek(i)
                colors.append(img.convert('RGB').getpixel((5, 5)))
            self.assertGreater(colors[0][0], 200)  # 紅
            self.assertGreater(colors[1][1], 100)  # 綠
            self.assertGreater(colors[2][2], 200)  # 藍

    def test_animated_webp_scale(self):
        out = self.d / "scaled.webp"
        result = process_image_core(
            filepath=self.anim, target_path=out, quality=80, scale=0.5,
            output_format='WEBP', skip_if_larger=False,
        )
        self.assertEqual(result.status, 'success')
        with Image.open(out) as img:
            self.assertEqual(img.size, (16, 16))
            self.assertEqual(img.n_frames, 3)

    def test_animated_to_jpeg_is_skipped(self):
        out = self.d / "anim.jpg"
        result = process_image_core(
            filepath=self.anim, target_path=out, quality=80, output_format='JPEG',
        )
        self.assertEqual(result.status, 'skipped')
        self.assertTrue(result.warn)
        self.assertFalse(out.exists())

    def test_animated_compress_in_place_keeps_frames(self):
        """原地壓縮動畫 WebP (target == filepath)：在 Windows 上也不能因檔案占用而失敗"""
        result = compress_image(
            filepath=self.anim, root_dir=self.d, out_dir=None, quality=50,
            overwrite=False, keep_exif=False, dry_run=False, in_place=True,
        )
        self.assertIn(result.status, ('success', 'size_skip'), result.message)
        with Image.open(self.anim) as img:
            self.assertEqual(img.n_frames, 3)


class TestCompressOutputDirExclusion(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_nested_out_dir_excluded(self):
        out = self.d / "compressed"
        (out / "sub").mkdir(parents=True)
        src = _make_img(self.d / "a.jpg", 'red', 'JPEG')
        _make_img(out / "a.jpg", 'red', 'JPEG')
        _make_img(out / "sub" / "b.jpg", 'red', 'JPEG')

        files = collect_files(
            self.d, SUPPORTED_FORMATS, exclude_fn=make_output_dir_excluder(self.d, out),
        )
        self.assertEqual([f.resolve() for f in files], [src.resolve()])

    def test_deep_nested_out_dir_excluded(self):
        out = self.d / "x" / "y" / "out"
        out.mkdir(parents=True)
        keep = _make_img(self.d / "x" / "keep.jpg", 'red', 'JPEG')
        _make_img(out / "skip.jpg", 'red', 'JPEG')
        files = collect_files(
            self.d, SUPPORTED_FORMATS, exclude_fn=make_output_dir_excluder(self.d, out),
        )
        self.assertEqual([f.resolve() for f in files], [keep.resolve()])

    def test_excluder_none_cases(self):
        self.assertIsNone(make_output_dir_excluder(self.d, None))
        self.assertIsNone(make_output_dir_excluder(self.d, self.d))  # 原地模式
        outside = Path(tempfile.mkdtemp())
        try:
            self.assertIsNone(make_output_dir_excluder(self.d, outside))
        finally:
            shutil.rmtree(outside)

    def test_similar_prefix_dir_not_excluded(self):
        """輸出目錄 'out' 不可誤排除名稱前綴相同的 'out2'"""
        out = self.d / "out"
        out.mkdir()
        (self.d / "out2").mkdir()
        keep = _make_img(self.d / "out2" / "k.jpg", 'red', 'JPEG')
        files = collect_files(
            self.d, SUPPORTED_FORMATS, exclude_fn=make_output_dir_excluder(self.d, out),
        )
        self.assertIn(keep.resolve(), [f.resolve() for f in files])

    def test_rerun_does_not_create_out_out(self):
        """實際模擬兩次執行：第二次不應產生 compressed/compressed/..."""
        out = self.d / "compressed"
        _make_img(self.d / "a.jpg", 'red', 'JPEG', size=(300, 300))
        for _ in range(2):
            files = collect_files(
                self.d, SUPPORTED_FORMATS, exclude_fn=make_output_dir_excluder(self.d, out),
            )
            for f in files:
                compress_image(
                    filepath=f, root_dir=self.d, out_dir=out, quality=50,
                    overwrite=True, keep_exif=False, dry_run=False,
                )
        self.assertTrue((out / "a.jpg").exists())
        self.assertFalse((out / "compressed").exists())


class TestSuffixHelpers(unittest.TestCase):
    def test_build_suffix(self):
        self.assertEqual(build_suffix(70, None), "_70%")
        self.assertEqual(build_suffix(70, 512000), "_500.0KB")

    def test_build_target_path_modes(self):
        root = Path("/r")
        f = root / "sub" / "x.heic"
        self.assertEqual(build_target_path(f, root, None, True, "_70%").name, "x.jpg")
        self.assertEqual(build_target_path(f, root, None, False, "_70%").name, "x_70%.jpg")
        self.assertEqual(
            build_target_path(f, root, Path("/o"), False, "_70%"),
            Path("/o") / "sub" / "x.jpg",
        )


if __name__ == '__main__':
    unittest.main()

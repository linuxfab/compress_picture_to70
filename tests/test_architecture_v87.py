"""
v8.7.0 架構重構與測試覆蓋率補充：
1. 模組拆分 (ui.py / cli.py / image_core.py) 與 utils.py 向後相容匯出
2. _atomic_write 嚴格原子寫入保護 (失敗時保留原檔並清理暫存檔)
3. run_pipeline() 各種結果狀態與統計驗證
4. compress_images.main() 與 images_to_webp.main() CLI 參數解析與執行
5. --format avif 支援與輸出路徑驗證
6. pyproject.toml 打包白名單與 scripts 去重驗證
"""

import shutil
import tempfile
import tomllib
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import cli
import compress_images
import image_core
import images_to_webp
import ui
import utils
from ui import FileResult, run_pipeline


def _make_img(path: Path, color: str = 'red', fmt: str = 'JPEG', size=(64, 64)) -> Path:
    Image.new('RGB', size, color=color).save(path, fmt)
    return path


class _DummyExecutor:
    """單元測試用同步執行器，模擬 ProcessPoolExecutor 介面以確定性覆蓋 run_pipeline 分支"""

    def __init__(self, max_workers=1):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def submit(self, fn, arg):
        fut: Future = Future()
        try:
            fut.set_result(fn(arg))
        except Exception as e:
            fut.set_exception(e)
        return fut


class TestModuleSplitAndCompatibility(unittest.TestCase):
    def test_split_modules_and_utils_facade(self):
        """驗證拆分後的模組符號皆可在 utils.py 相容匯入且指向同一物件"""
        self.assertIs(utils.console, ui.console)
        self.assertIs(utils.run_pipeline, ui.run_pipeline)
        self.assertIs(utils.FileResult, ui.FileResult)
        self.assertIs(utils.create_base_parser, cli.create_base_parser)
        self.assertIs(utils.assign_conflict_tags, cli.assign_conflict_tags)
        self.assertIs(utils.process_image_core, image_core.process_image_core)
        self.assertIs(utils.FORMAT_MAP, image_core.FORMAT_MAP)
        self.assertIs(utils.EXT_BY_FORMAT, image_core.EXT_BY_FORMAT)
        self.assertEqual(utils.__version__, "8.7.0")


class TestAtomicWriteProtection(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_atomic_write_failure_preserves_original_and_cleans_tmp(self):
        """os.replace 失敗時不可 fallback 成直接覆寫，必須保留原檔並刪除暫存檔"""
        target = self.d / "important.jpg"
        original_bytes = b"ORIGINAL_SAFE_BYTES"
        target.write_bytes(original_bytes)

        with patch("image_core.os.replace", side_effect=OSError("模擬磁碟置換失敗")):
            with self.assertRaises(OSError):
                image_core._atomic_write(target, b"NEW_CORRUPT_BYTES")

        self.assertEqual(target.read_bytes(), original_bytes)
        remaining = [p.name for p in self.d.iterdir()]
        self.assertEqual(remaining, ["important.jpg"])

    def test_process_image_core_returns_failed_on_atomic_write_error(self):
        """process_image_core 遇到原子寫入失敗應回傳 failed 且原檔完整"""
        src = _make_img(self.d / "src.jpg", size=(200, 200))
        target = self.d / "target.jpg"
        target.write_bytes(b"KEEP_ME")

        with patch("image_core.os.replace", side_effect=PermissionError("模擬權限不足")):
            res = image_core.process_image_core(
                filepath=src, target_path=target, quality=50,
                skip_if_larger=False, output_format='JPEG',
            )

        self.assertEqual(res.status, 'failed')
        self.assertEqual(target.read_bytes(), b"KEEP_ME")


class TestRunPipeline(unittest.TestCase):
    def test_empty_files(self):
        summary = run_pipeline([], lambda f: FileResult('success', 'ok'), workers=2)
        self.assertEqual(summary.success, 0)
        self.assertEqual(summary.failed, 0)

    def test_pipeline_aggregates_all_statuses(self):
        files = [
            Path("ok.jpg"),
            Path("skip.jpg"),
            Path("warn_skip.jpg"),
            Path("larger.jpg"),
            Path("fail.jpg"),
            Path("crash.jpg"),
        ]

        def fake_worker(p: Path) -> FileResult:
            if p.name == "ok.jpg":
                return FileResult('success', 'OK', original_size=1000, new_size=400)
            if p.name == "skip.jpg":
                return FileResult('skipped', 'skip')
            if p.name == "warn_skip.jpg":
                return FileResult('skipped', 'warn', warn=True)
            if p.name == "larger.jpg":
                return FileResult('size_skip', 'too large')
            if p.name == "fail.jpg":
                return FileResult('failed', 'bad file')
            raise RuntimeError("boom")

        with patch("ui.ProcessPoolExecutor", _DummyExecutor):
            summary = run_pipeline(files, fake_worker, workers=2, dry_run=False, label="測試")

        self.assertEqual(summary.success, 1)
        self.assertEqual(summary.skipped, 2)
        self.assertEqual(summary.size_skip, 1)
        self.assertEqual(summary.failed, 2)
        self.assertEqual(summary.total_original, 1000)
        self.assertEqual(summary.total_new, 400)

    def test_pipeline_dry_run_counts_as_skipped(self):
        files = [Path("a.jpg"), Path("b.jpg")]
        with patch("ui.ProcessPoolExecutor", _DummyExecutor):
            summary = run_pipeline(
                files, lambda p: FileResult('dry_run', f"[預覽] {p.name}"),
                workers=1, dry_run=True,
            )
        self.assertEqual(summary.skipped, 2)
        self.assertEqual(summary.success, 0)


class TestCliMainAndAvifFormat(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.img = _make_img(self.d / "photo.png", color='blue', fmt='PNG', size=(120, 120))

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_compress_main_dry_run_and_format_avif(self):
        out_dir = self.d / "out_avif"
        with patch("ui.ProcessPoolExecutor", _DummyExecutor):
            compress_images.main([
                str(self.d), "-O", str(out_dir), "-f", "avif", "-n", "-w", "1"
            ])
        # dry-run 不應實際產生檔案
        self.assertFalse(out_dir.exists())

    def test_compress_main_invalid_quality_and_scale_exit_gracefully(self):
        with patch("compress_images.run_pipeline") as mock_pipe:
            compress_images.main([str(self.d), "-q", "150"])
            compress_images.main([str(self.d), "--scale", "2.5"])
            compress_images.main([str(self.d / "not_exists")])
            mock_pipe.assert_not_called()

    def test_images_to_webp_main_dry_run_avif(self):
        out_dir = self.d / "avif_out"
        with patch("ui.ProcessPoolExecutor", _DummyExecutor):
            images_to_webp.main([
                str(self.d), "-O", str(out_dir), "-f", "avif", "-n", "-w", "1"
            ])
        self.assertFalse(out_dir.exists())

    def test_images_to_webp_main_executes_conversion(self):
        out_dir = self.d / "webp_out"
        with patch("ui.ProcessPoolExecutor", _DummyExecutor):
            images_to_webp.main([
                str(self.d), "-O", str(out_dir), "-q", "80", "-w", "1"
            ])
        self.assertTrue((out_dir / "photo.webp").exists())

    def test_build_target_path_with_explicit_format(self):
        out_dir = self.d / "out"
        p_avif = compress_images.build_target_path(
            self.img, self.d, out_dir, in_place=False, suffix="_70%", target_format="avif"
        )
        self.assertEqual(p_avif, out_dir / "photo.avif")

        p_webp_suffix = compress_images.build_target_path(
            self.img, self.d, None, in_place=False, suffix="_70%", target_format="webp"
        )
        self.assertEqual(p_webp_suffix, self.d / "photo_70%.webp")

        p_avif_convert = images_to_webp.build_webp_target(
            self.img, self.d, out_dir, target_format="avif"
        )
        self.assertEqual(p_avif_convert, out_dir / "photo.avif")

    def test_compress_image_format_avif_real_conversion(self):
        """驗證 compress_image 指定 target_format='avif' 的實際轉檔"""
        out_dir = self.d / "avif_real"
        res = compress_images.compress_image(
            filepath=self.img, root_dir=self.d, out_dir=out_dir,
            quality=70, overwrite=True, keep_exif=False, dry_run=False,
            target_format='avif',
        )
        if res.status == 'failed' and "AVIF" in res.message.upper():
            self.skipTest(f"環境不支援 AVIF 編碼: {res.message}")
        self.assertEqual(res.status, 'success', res.message)
        self.assertTrue((out_dir / "photo.avif").exists())


class TestPyprojectConfiguration(unittest.TestCase):
    def test_pyproject_scripts_and_wheel_include(self):
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        scripts = data["project"]["scripts"]
        self.assertNotIn("compress_images", scripts)
        self.assertIn("compress-img", scripts)
        self.assertIn("images-to-webp", scripts)

        wheel_cfg = data["tool"]["hatch"]["build"]["targets"]["wheel"]
        self.assertNotIn("packages", wheel_cfg)
        only_include = set(wheel_cfg["only-include"])
        self.assertTrue({"compress_images.py", "images_to_webp.py", "utils.py", "ui.py", "cli.py", "image_core.py"}.issubset(only_include))
        self.assertNotIn("tests", only_include)
        self.assertNotIn("scratch", only_include)


if __name__ == '__main__':
    unittest.main()

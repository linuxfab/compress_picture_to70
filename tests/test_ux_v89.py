"""
v8.9.0 使用體驗 (UX) 改良測試：
9. Ctrl+C (KeyboardInterrupt) 呼叫 executor.shutdown(wait=False, cancel_futures=True)
10. -v / verbose 輸出被跳過與處理明細
11. --dry-run 獨立統計於 summary.dry_run 並於報表顯示「預覽 (將處理)」
12. 拖曳路徑帶單/雙引號自動清理
13. --report out.csv 逐檔結果報表匯出 (含 quality_used)
"""

import argparse
import csv
import shutil
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

import cli
import compress_images
import images_to_webp
import ui
from ui import FileResult, ProcessingSummary, print_summary, run_pipeline


class _SyncExecutor:
    def __init__(self, max_workers=1):
        self.max_workers = max_workers

    def submit(self, fn, arg):
        fut: Future = Future()
        try:
            fut.set_result(fn(arg))
        except Exception as e:
            fut.set_exception(e)
        return fut

    def shutdown(self, wait=True, cancel_futures=False):
        pass


class TestCtrlCCancellation(unittest.TestCase):
    def test_keyboard_interrupt_cancels_futures(self):
        """捕捉到 KeyboardInterrupt 時應呼叫 executor.shutdown(wait=False, cancel_futures=True)"""
        mock_executor = MagicMock()
        mock_executor.submit.return_value = Future()

        with patch("ui.ProcessPoolExecutor", return_value=mock_executor), \
             patch("ui.as_completed", side_effect=KeyboardInterrupt):
            run_pipeline([Path("a.jpg"), Path("b.jpg")], lambda p: FileResult('success', 'ok'), workers=2)

        mock_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


class TestVerboseAndDryRunSummary(unittest.TestCase):
    def test_verbose_prints_skipped_details(self):
        files = [Path("a.bmp")]
        with patch("ui.ProcessPoolExecutor", _SyncExecutor), \
             patch.object(ui.console, "print") as mock_print:
            run_pipeline(
                files,
                lambda p: FileResult('skipped', f"跳過 BMP: {p.name}"),
                workers=1,
                verbose=True,
            )
        printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("跳過 BMP: a.bmp", printed)

    def test_print_summary_displays_dry_run_row(self):
        summary = ProcessingSummary(dry_run=5)
        with patch.object(ui.console, "print") as mock_print:
            print_summary(summary)
        self.assertTrue(mock_print.called)
        table = mock_print.call_args_list[0].args[0]
        # 確認第一列欄位有 "預覽 (將處理)"
        first_cell = table.columns[0]._cells[0]
        self.assertIn("預覽 (將處理)", first_cell)


class TestDragDropQuoteResolution(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_resolve_directory_strips_quotes_from_arg(self):
        args = argparse.Namespace(directory=f'  "{self.d}"  ')
        resolved = cli.resolve_directory(args)
        self.assertEqual(resolved, str(self.d))

    def test_resolve_directory_strips_quotes_from_interactive_input(self):
        args = argparse.Namespace(directory=None)
        with patch("builtins.input", return_value=f"'{self.d}'"):
            resolved = cli.resolve_directory(args)
        self.assertEqual(resolved, str(self.d))


class TestCsvReportExport(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.img = self.d / "sample.jpg"
        Image.new('RGB', (200, 200), 'red').save(self.img, 'JPEG', quality=95)

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_compress_main_writes_csv_report(self):
        out_dir = self.d / "out"
        report_file = self.d / "reports" / "compress_report.csv"

        with patch("ui.ProcessPoolExecutor", _SyncExecutor):
            compress_images.main([
                str(self.d), "-O", str(out_dir), "-q", "65", "-w", "1", "--report", str(report_file)
            ])

        self.assertTrue(report_file.exists())
        with open(report_file, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["quality_used"], "65")
        self.assertEqual(Path(row["filepath"]).name, "sample.jpg")
        self.assertEqual(Path(row["target_path"]).name, "sample.jpg")
        self.assertGreater(int(row["original_size"]), 0)
        self.assertGreater(int(row["new_size"]), 0)
        self.assertEqual(int(row["saved_bytes"]), int(row["original_size"]) - int(row["new_size"]))

    def test_images_to_webp_dry_run_csv_report(self):
        report_file = self.d / "webp_preview.csv"
        with patch("ui.ProcessPoolExecutor", _SyncExecutor):
            images_to_webp.main([
                str(self.d), "-n", "-w", "1", "--report", str(report_file)
            ])

        self.assertTrue(report_file.exists())
        with open(report_file, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "dry_run")
        self.assertTrue(rows[0]["target_path"].endswith("sample.webp"))


if __name__ == '__main__':
    unittest.main()

"""
圖片處理工具 - 共用模組

提供並行處理管線、統計彙整、CLI 共用元件等功能。
消除全域 mutable state，每個 worker 回傳 FileResult，由管線在主執行緒彙整。
"""

from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
import argparse


@dataclass
class FileResult:
    """單一檔案處理結果 (immutable per-file, 無需 lock)"""
    status: str  # 'success', 'skipped', 'failed', 'size_skip', 'dry_run'
    message: str
    original_size: int = 0
    new_size: int = 0


@dataclass
class ProcessingSummary:
    """批次處理統計摘要"""
    success: int = 0
    skipped: int = 0
    failed: int = 0
    size_skip: int = 0
    total_original: int = 0
    total_new: int = 0


def format_size(size_bytes: int) -> str:
    """將 bytes 轉為人類可讀格式"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def collect_files(
    directory: Path,
    supported_formats: set[str],
    exclude_dirs: set[str] | None = None,
) -> list[Path]:
    """
    收集目錄及子目錄中所有符合格式的檔案

    Args:
        directory: 目標目錄
        supported_formats: 支援的副檔名集合 (含點號, e.g. {'.jpg', '.png'})
        exclude_dirs: 要排除的目錄名稱集合 (e.g. {'webpimage'})
    """
    files = []
    for f in directory.rglob('*'):
        if not f.is_file():
            continue
        if f.suffix.lower() not in supported_formats:
            continue
        # 排除指定目錄
        if exclude_dirs:
            try:
                rel = f.relative_to(directory)
                if any(part in exclude_dirs for part in rel.parts):
                    continue
            except ValueError:
                pass
        files.append(f)
    return files


def run_pipeline(
    files: list[Path],
    worker_fn: Callable[[Path], FileResult],
    workers: int,
    dry_run: bool = False,
    label: str = "處理",
) -> ProcessingSummary:
    """
    並行處理檔案管線

    每個 worker_fn 回傳 FileResult，由此函式在主執行緒彙整統計。
    不使用任何全域 state 或 lock。

    Args:
        files: 待處理檔案清單
        worker_fn: 處理單一檔案的函式 (接受 Path, 回傳 FileResult)
                   呼叫端應使用 functools.partial 綁定額外參數
        workers: 並行執行緒數
        dry_run: 是否為預覽模式 (僅影響 banner 文字)
        label: 動作標籤 (e.g. "壓縮", "轉換")
    """
    summary = ProcessingSummary()
    total = len(files)

    if dry_run:
        print(f"[DRY-RUN] 找到 {total} 張圖片，預覽模式（不會實際{label}）...")
    else:
        print(f"找到 {total} 張圖片，開始{label}...")
    print("=" * 60)

    if total == 0:
        return summary

    # 並行處理，結果在主執行緒彙整 (no lock needed)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker_fn, f): f for f in files}

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            print(f"[{i}/{total}] {result.message}")

            if result.status == 'success':
                summary.success += 1
                summary.total_original += result.original_size
                summary.total_new += result.new_size
            elif result.status in ('skipped', 'dry_run'):
                summary.skipped += 1
            elif result.status == 'size_skip':
                summary.size_skip += 1
            else:
                summary.failed += 1

    return summary


def print_summary(
    summary: ProcessingSummary,
    success_label: str = "成功壓縮",
    skip_label: str = "跳過(已存在/已壓縮)",
    after_label: str = "處理後",
) -> None:
    """印出處理結果摘要"""
    print("=" * 60)
    print("處理完成!")
    print(f"  {success_label}: {summary.success}")
    print(f"  {skip_label}: {summary.skipped}")
    if summary.size_skip > 0:
        print(f"  跳過(壓縮後變大): {summary.size_skip}")
    print(f"  失敗: {summary.failed}")

    if summary.total_original > 0:
        saved = summary.total_original - summary.total_new
        pct = (saved / summary.total_original) * 100
        print(f"\n  📊 空間統計:")
        print(f"     原始總大小: {format_size(summary.total_original)}")
        print(f"     {after_label}總大小: {format_size(summary.total_new)}")
        print(f"     總共節省: {format_size(saved)} ({pct:.1f}%)")


def create_base_parser(description: str, epilog: str) -> argparse.ArgumentParser:
    """建立含共用參數的 ArgumentParser"""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    parser.add_argument('directory', nargs='?', help='目標目錄路徑')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='並行處理執行緒數 (預設: 4)')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='預覽模式：僅列出待處理檔案，不實際處理')
    return parser


def resolve_directory(args) -> str | None:
    """解析目錄路徑 (支援互動模式)，回傳 None 表示使用者未輸入"""
    if not args.directory:
        args.directory = input("請輸入目標目錄路徑: ").strip()
        if not args.directory:
            print("未輸入目錄，程式結束")
            return None
    return args.directory


def validate_quality(quality: int) -> bool:
    """驗證 quality 參數範圍"""
    if not 1 <= quality <= 100:
        print("錯誤: quality 必須在 1-100 之間")
        return False
    return True

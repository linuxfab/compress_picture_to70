"""
圖片處理工具 - 共用模組

整合了 Rich UI 視覺化（進度條、匯總表格）、隱藏目錄過濾、以及自訂輸出路徑等功能。
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable
import argparse

# 引入 Rich 函式庫做終端機視覺化美化
from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TimeElapsedColumn, 
    TextColumn, BarColumn, TaskProgressColumn
)
from rich.table import Table
from rich import box

console = Console()
logger = logging.getLogger("img_tools")

def setup_logger(verbose: bool = False):
    """初始化底層 Logger 給背景報錯使用，一般輸出改由 Rich 接管"""
    level = logging.DEBUG if verbose else logging.WARNING
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    logger.setLevel(level)
    
    if not logger.handlers:
        logger.addHandler(handler)


@dataclass
class FileResult:
    """單一檔案處理結果 (immutable per-file)"""
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
    max_depth: int | None = None,
) -> list[Path]:
    """收集目錄及子目錄中所有符合格式的檔案，並自動濾除系統隱藏及專案相關目錄"""
    files = []
    
    # 使用者如果未傳入要避開的目錄，我們給空 set
    if exclude_dirs is None:
        exclude_dirs = set()
    
    # 內建忽略規則：以 `.` 或 `__` 開頭的目錄
    def is_ignored(part: str) -> bool:
        return part.startswith('.') or part.startswith('__') or part in exclude_dirs

    for f in directory.rglob('*'):
        if not f.is_file():
            continue
            
        try:
            rel = f.relative_to(directory)
            depth = len(rel.parts) - 1
            
            # 深度檢查
            if max_depth is not None and depth > max_depth:
                continue
                
            # 過濾隱藏與專案內部目錄 (例 .venv, .git, __pycache__, 或外部傳入的 webpimage 等)
            if any(is_ignored(part) for part in rel.parts):
                continue
                
        except ValueError:
            continue
            
        if f.suffix.lower() not in supported_formats:
            continue
            
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
    並行處理檔案管線，整合 Rich 視覺化進度條
    """
    summary = ProcessingSummary()
    total = len(files)

    if total == 0:
        return summary

    if dry_run:
        console.print(f"[bold yellow][DRY-RUN] 找到 {total} 張圖片，預覽模式（不實際寫入）...[/bold yellow]")
    else:
        console.print(f"[bold green]找到 {total} 張圖片，開始進行 {label}...[/bold green]\n")

    # 使用 Rich 來渲染動態進度條
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        task_id = progress.add_task(f" [cyan]{label}中...", total=total)

        # 啟動並行處理 (ProcessPoolExecutor 加速 CPU bound)
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(worker_fn, f): f for f in files}

            for future in as_completed(futures):
                result = future.result()
                
                # 如果失敗，將紅色的 Alert 印在進度條上方而不破壞版面
                if result.status == 'failed':
                    progress.console.print(f"[bold red]{result.message}[/bold red]")
                # 為了避免洗版，成功的訊息不再像以往一樣印出 (除 dry_run 會跳出)
                elif result.status == 'dry_run':
                    progress.console.print(f"[dim]{result.message}[/dim]")

                # 統計
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
                
                # 更新進度表
                progress.advance(task_id)

    return summary


def print_summary(
    summary: ProcessingSummary,
    success_label: str = "成功處理",
    skip_label: str = "跳過(已存在/隱藏)",
    after_label: str = "處理後",
) -> None:
    """使用 Rich Table 印出華麗且易讀的分析報告"""
    
    # =================
    # 執行結果狀態表格
    # =================
    status_table = Table(title="\n📊 執行結果分析", box=box.ROUNDED, show_header=True, header_style="bold magenta")
    status_table.add_column("狀態", style="dim", width=25)
    status_table.add_column("數量", justify="right", style="bold cyan")

    status_table.add_row(success_label, str(summary.success))
    status_table.add_row(skip_label, str(summary.skipped))
    if summary.size_skip > 0:
        status_table.add_row("跳過 (無效壓縮/體積變大)", str(summary.size_skip))
    
    fail_color = "red" if summary.failed > 0 else "white"
    status_table.add_row(f"[{fail_color}]失敗[/{fail_color}]", f"[{fail_color}]{str(summary.failed)}[/{fail_color}]")
    
    console.print(status_table)

    # =================
    # 儲存空間統計表格
    # =================
    if summary.total_original > 0:
        saved = summary.total_original - summary.total_new
        pct = (saved / summary.total_original) * 100
        
        space_table = Table(title="💾 磁碟空間變化", box=box.MINIMAL_DOUBLE_HEAD)
        space_table.add_column("對象", style="cyan")
        space_table.add_column("容量大小", justify="right", style="green")
        
        space_table.add_row("原始總大小", format_size(summary.total_original))
        space_table.add_row(f"{after_label}總大小", format_size(summary.total_new))
        
        # 決定顏色 (省越多越綠，反而變大則拉警報)
        saved_color = "bold green" if saved > 0 else "bold red"
        space_table.add_row(f"[{saved_color}]實際節省空間[/{saved_color}]", f"[{saved_color}]{format_size(saved)} ({pct:.1f}%)[/{saved_color}]")
        
        console.print(space_table)


def create_base_parser(description: str, epilog: str) -> argparse.ArgumentParser:
    """建立含共用參數的 ArgumentParser，已內建 out-dir 支援"""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    parser.add_argument('directory', nargs='?', help='目標目錄路徑 (來源資料夾)')
    parser.add_argument('-O', '--out-dir', type=str, default=None,
                        help='輸出目錄 (留空則覆寫於原始資料夾旁，若指定則建立不落地的鏡像目錄)')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='並行處理程序的數量 (預設: 4)')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='預覽模式：僅列出待處理檔案，不實際處理')
    parser.add_argument('-d', '--max-depth', type=int, default=None,
                        help='最大遞迴深度 (0=不進入子目錄, 未指定=無限)')
    return parser


def resolve_directory(args) -> str | None:
    """解析目錄路徑 (支援互動模式)，回傳 None 表示使用者未輸入"""
    if not args.directory:
        args.directory = input("請輸入目標來源目錄路徑：").strip()
        if not args.directory:
            console.print("[bold red]未輸入目錄，程式結束。[/bold red]")
            return None
    return args.directory


def validate_quality(quality: int) -> bool:
    """驗證 quality 參數範圍"""
    if not 1 <= quality <= 100:
        console.print("[bold red]錯誤：壓縮品質 quality 必須在 1-100 之間。[/bold red]")
        return False
    return True

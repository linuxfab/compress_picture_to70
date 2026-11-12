"""
圖片處理工具 - 終端機 UI 與並行管線模組
負責 Rich 視覺化輸出、進度條、統計報表與 ProcessPoolExecutor 並行管線。
"""

import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rich import box
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

console = Console()
logger = logging.getLogger("img_tools")


def setup_logger(verbose: bool = False) -> None:
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
    warn: bool = False  # True 時進度條上方會以黃字顯示 message (例如動畫圖片被跳過)


@dataclass
class ProcessingSummary:
    """批次處理統計摘要"""
    success: int = 0
    skipped: int = 0
    failed: int = 0
    size_skip: int = 0
    total_original: int = 0
    total_new: int = 0
    elapsed_seconds: float = 0.0


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


def _format_elapsed(seconds: float) -> str:
    """將秒數格式化為人類可讀的時間字串"""
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)} 分 {s:.0f} 秒"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{int(h)} 時 {int(m)} 分 {s:.0f} 秒"


def build_filter_info(
    min_size: int | None,
    max_size: int | None,
    scale: float,
    target_size: int | None = None,
) -> str:
    """組裝過濾與目標條件的顯示字串，供 Welcome Panel 使用"""
    parts: list[str] = []
    if min_size:
        parts.append(f">= {format_size(min_size)}")
    if max_size:
        parts.append(f"<= {format_size(max_size)}")
    if scale < 1.0:
        parts.append(f"縮放 {scale:.0%}")
    if target_size:
        parts.append(f"目標大小 {format_size(target_size)}")
    return f" | [bold red]過濾/目標[/bold red]: {', '.join(parts)}" if parts else ""


def print_conflict_notice(
    tags: dict[str, str],
    target_fn: Callable[[Path, str], Path],
    limit: int = 10,
) -> None:
    """在 Welcome Panel 後提示使用者有哪些檔案因同名衝突而改名"""
    if not tags:
        return
    console.print(
        f"[bold yellow]注意：偵測到 {len(tags)} 個檔案的輸出檔名互相衝突，"
        f"已自動加上原副檔名標籤避免互相覆蓋：[/bold yellow]"
    )
    for i, (src, tag) in enumerate(sorted(tags.items())):
        if i >= limit:
            console.print(f"[yellow]  ... 以及其他 {len(tags) - limit} 個檔案[/yellow]")
            break
        src_path = Path(src)
        console.print(f"[yellow]  {src_path.name} → {target_fn(src_path, tag).name}[/yellow]")


def run_pipeline(
    files: list[Path],
    worker_fn: Callable[[Path], FileResult],
    workers: int,
    dry_run: bool = False,
    label: str = "處理",
) -> ProcessingSummary:
    """並行處理檔案管線，整合 Rich 視覺化進度條"""
    summary = ProcessingSummary()
    total = len(files)

    if total == 0:
        return summary

    if dry_run:
        console.print(f"[bold yellow][DRY-RUN] 找到 {total} 張圖片，預覽模式（不實際寫入）...[/bold yellow]")
    else:
        console.print(f"[bold green]找到 {total} 張圖片，開始進行 {label}...[/bold green]\n")

    t_start = time.perf_counter()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task_id = progress.add_task(f" [cyan]{label}中...", total=total)

        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(worker_fn, f): f for f in files}

                for future in as_completed(futures):
                    filepath = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        result = FileResult('failed', f"子程序異常 {filepath.name}: {e}")

                    if result.status == 'failed':
                        progress.console.print(f"[bold red]{result.message}[/bold red]")
                    elif result.status == 'dry_run':
                        progress.console.print(f"[dim]{result.message}[/dim]")
                    elif result.warn:
                        progress.console.print(f"[yellow]{result.message}[/yellow]")

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

                    progress.update(task_id, description=f" [cyan]{label}中: {filepath.name}")
                    progress.advance(task_id)
        except KeyboardInterrupt:
            progress.console.print("\n[bold yellow]警告：使用者中斷 (Ctrl+C)，正在停止...[/bold yellow]")

    summary.elapsed_seconds = time.perf_counter() - t_start
    return summary


def print_summary(
    summary: ProcessingSummary,
    success_label: str = "成功處理",
    skip_label: str = "跳過(已存在/隱藏/大小不符)",
    after_label: str = "處理後",
) -> None:
    """使用 Rich Table 印出華麗且易讀的分析報告"""
    status_table = Table(title="\n[分析] 執行結果分析", box=box.ROUNDED, show_header=True, header_style="bold magenta")
    status_table.add_column("狀態", style="dim", width=25)
    status_table.add_column("數量", justify="right", style="bold cyan")

    status_table.add_row(success_label, str(summary.success))
    status_table.add_row(skip_label, str(summary.skipped))
    if summary.size_skip > 0:
        status_table.add_row("跳過 (無效壓縮/體積變大)", str(summary.size_skip))

    fail_color = "red" if summary.failed > 0 else "white"
    status_table.add_row(f"[{fail_color}]失敗[/{fail_color}]", f"[{fail_color}]{str(summary.failed)}[/{fail_color}]")

    if summary.elapsed_seconds > 0:
        status_table.add_row("總執行時間", _format_elapsed(summary.elapsed_seconds))

    console.print(status_table)

    if summary.total_original > 0:
        saved = summary.total_original - summary.total_new
        pct = (saved / summary.total_original) * 100

        space_table = Table(title="[容量] 磁碟空間變化", box=box.MINIMAL_DOUBLE_HEAD)
        space_table.add_column("對象", style="cyan")
        space_table.add_column("容量大小", justify="right", style="green")

        space_table.add_row("原始總大小", format_size(summary.total_original))
        space_table.add_row(f"{after_label}總大小", format_size(summary.total_new))

        saved_color = "bold green" if saved > 0 else "bold red"
        space_table.add_row(f"[{saved_color}]實際節省空間[/{saved_color}]", f"[{saved_color}]{format_size(saved)} ({pct:.1f}%)[/{saved_color}]")

        if summary.success > 0:
            avg_saved = saved / summary.success
            space_table.add_row("平均每張節省", format_size(int(avg_saved)))

        console.print(space_table)

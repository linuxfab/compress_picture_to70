"""
圖片處理工具 - 共用模組

整合了 Rich UI 視覺化、進度條、匯總表格、隱藏目錄過濾、檔案大小過濾及自訂輸出功能。
"""

import logging
import re
import os
import io
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, Iterable
import argparse

__version__ = "8.1.1"

# 引入 Rich 函式庫做終端機視覺化美化
from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TimeElapsedColumn, 
    TextColumn, BarColumn, TaskProgressColumn
)
from rich.table import Table
from rich import box
from PIL import Image, ImageOps, UnidentifiedImageError

import pillow_heif
pillow_heif.register_heif_opener()

console = Console()
logger = logging.getLogger("img_tools")

# --- 集中管理常數 ---
# 支援的圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic', '.avif'}

# 用於偵測已壓縮檔案的 regex pattern (e.g. _70%, _50%)
COMPRESSED_SUFFIX_PATTERN = re.compile(r'_\d+%$')

# -----------------

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

def parse_size_to_bytes(size_str: str | None) -> int | None:
    """
    將人類可讀大小（如 '500KB', '2MB', '1.5GB'）轉為 bytes 數字
    若無單位預設視為 KB，如果沒傳入則回傳 None
    """
    if not size_str:
        return None
        
    match = re.match(r'^([\d\.]+)\s*([a-zA-Z]*)$', size_str.strip())
    if not match:
        raise ValueError(f"解析檔案大小參數錯誤: {size_str}，請使用如 500KB, 2MB 等格式")
        
    number = float(match.group(1))
    unit = match.group(2).upper()
    
    if unit in ('', 'K', 'KB'):
        return int(number * 1024)
    elif unit in ('M', 'MB'):
        return int(number * 1024 * 1024)
    elif unit in ('G', 'GB'):
        return int(number * 1024 * 1024 * 1024)
    elif unit in ('B', 'BYTE', 'BYTES'):
        return int(number)
    else:
        raise ValueError(f"未知的單位: {unit}")


def collect_files(
    directory: Path,
    supported_formats: Iterable[str],
    exclude_dirs: set[str] | None = None,
    max_depth: int | None = None,
) -> list[Path]:
    """收集目錄及子目錄中所有符合格式的檔案，並自動濾除系統隱藏及專案目錄"""
    files: list[Path] = []
    
    if exclude_dirs is None:
        exclude_dirs = set()
    
    # 內建忽略規則：以 `.` 或 `__` 開頭的目錄
    def is_ignored(part: str) -> bool:
        return part.startswith('.') or part.startswith('__') or part in exclude_dirs

    # 使用 os.walk 通常比 rglob('*') 在大型目錄下更快，且更容易控制深度
    for root, dirs, filenames in os.walk(directory):
        root_path = Path(root)
        try:
            rel = root_path.relative_to(directory)
            depth = len(rel.parts)
            
            # 深度檢查 (max_depth=0 代表只看根目錄)
            if max_depth is not None and depth > max_depth:
                dirs[:] = [] # 停止繼續往下走
                continue
                
            # 過濾隱藏與專案內部目錄 (修改 dirs 陣列會影響 os.walk 的後續遍歷)
            dirs[:] = [d for d in dirs if not is_ignored(d)]
            
        except ValueError:
            continue

        for filename in filenames:
            f = root_path / filename
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
                try:
                    result = future.result()
                except Exception as e:
                    filepath = futures[future]
                    result = FileResult('failed', f"子程序異常 {filepath.name}: {e}")
                
                # 如果失敗，將紅色的 Alert 印在進度條上方而不破壞版面
                if result.status == 'failed':
                    progress.console.print(f"[bold red]{result.message}[/bold red]")
                # DRY RUN 模式要把每條紀錄印出來
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
    skip_label: str = "跳過(已存在/隱藏/大小不符)",
    after_label: str = "處理後",
) -> None:
    """使用 Rich Table 印出華麗且易讀的分析報告"""
    
    # 執行結果狀態表格
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

    # 儲存空間統計表格
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
        
        if summary.success > 0:
            avg_saved = saved / summary.success
            space_table.add_row("平均每張節省", format_size(int(avg_saved)))

        console.print(space_table)


def create_base_parser(description: str, epilog: str) -> argparse.ArgumentParser:
    """建立含共用參數的 ArgumentParser，已內建 out-dir 及大小過濾支援"""
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
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='顯示詳細除錯資訊')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='預覽模式：僅列出待處理檔案，不實際處理')
    parser.add_argument('-d', '--max-depth', type=int, default=None,
                        help='最大遞迴深度 (0=不進入子目錄, 未指定=無限)')
    parser.add_argument('-m', '--min-size', '--min', type=str, default=None,
                        help='最小檔案限制 (低於此大小將被跳過)，範例: 500KB, 2MB')
    parser.add_argument('-M', '--max-size', '--max', type=str, default=None,
                        help='最大檔案限制 (高於此大小將被跳過)，範例: 10MB')
    parser.add_argument('--skip-if-newer', action='store_true',
                        help='如果目標檔案存在且比來源檔案新則跳過 (適用於增量備份)')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='縮放比例 (0.1 - 1.0)，例如 0.5 表示長寬減半 (預設: 1.0)')
    parser.add_argument('--in-place', action='store_true',
                        help='原地覆蓋：直接取代原始檔案 (不加後綴，且會自動刪除/覆蓋原檔，請小心使用)')
    return parser


def resolve_directory(args: argparse.Namespace) -> str | None:
    """解析目錄路徑 (支援互動模式)，回傳 None 表示使用者未輸入"""
    if not args.directory:
        args.directory = input("請輸入目標來源目錄路徑：").strip()
        if not args.directory:
            console.print("[bold red]未輸入目錄，程式結束。[/bold red]")
            return None
    return str(args.directory)


def validate_quality(quality: int) -> bool:
    """驗證 quality 參數範圍"""
    if not 1 <= quality <= 100:
        console.print("[bold red]錯誤：壓縮品質 quality 必須在 1-100 之間。[/bold red]")
        return False
    return True


# --- 新增：圖片處理核心邏輯 ---

def get_exif_data(img: Image.Image) -> bytes | None:
    """取得圖片的 EXIF 資料"""
    try:
        return img.info.get('exif')
    except Exception:
        return None

def process_image_core(
    filepath: Path,
    target_path: Path,
    quality: int,
    keep_exif: bool = True,
    scale: float = 1.0,
    output_format: str | None = None, # None = 自動偵測
    lossless: bool = False,
    skip_if_larger: bool = True,
    force_convert_from: set[str] | None = None,
    file_stat: os.stat_result | None = None
) -> FileResult:
    """
    圖片處理核心邏輯：
    1. 開啟與縮放
    2. 色彩空間轉換 (CMYK/P -> RGB)
    3. 提取 EXIF
    4. 儲存至緩衝區檢查大小
    5. 決定是否寫入硬碟
    """
    try:
        orig_stat = file_stat if file_stat is not None else filepath.stat()
        original_size = orig_stat.st_size
        with Image.open(filepath) as img:
            img.load()  # 強制讀入記憶體，釋放 file handle
            
            # 修正 EXIF 旋轉問題 (手機照片必備) - 必須在 resize 前
            img = ImageOps.exif_transpose(img)

            # 縮放處理
            if 0.1 <= scale < 1.0:
                new_width = max(1, int(img.width * scale))
                new_height = max(1, int(img.height * scale))
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            exif_data = get_exif_data(img) if keep_exif else None
        
        # 色彩模式標準化
        if img.mode in ('CMYK', 'P', 'RGBA') and output_format in ('JPEG', 'JPG'):
             img = img.convert('RGB')
        elif img.mode in ('CMYK', 'P') and output_format in ('WEBP', 'AVIF'):
             img = img.convert('RGB')

        # 準備儲存參數
        save_kwargs = {'optimize': True}
        if output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
            if not lossless:
                save_kwargs['quality'] = quality
        
        if lossless and output_format in ('WEBP', 'AVIF'):
            save_kwargs['lossless'] = True
            
        if exif_data:
            save_kwargs['exif'] = exif_data

        # 決定最終格式
        if not output_format:
            fmt_map = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP', '.avif': 'AVIF'}
            output_format = fmt_map.get(target_path.suffix.lower(), 'JPEG')

        # 先存到記憶體緩衝區檢查大小
        buf = io.BytesIO()
        img.save(buf, format=output_format, **save_kwargs)
        new_size = buf.tell()
        
        # 檢查是否越壓越大 (排除特定轉檔需求)
        orig_ext = filepath.suffix.lower()
        should_force = force_convert_from and orig_ext in force_convert_from
        
        if skip_if_larger and new_size >= original_size and not should_force:
            return FileResult('size_skip', f"檔案 {filepath.name} 越壓越大，捨棄變更")

        # 確保目錄存在並寫入
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, 'wb') as f:
            f.write(buf.getvalue())

        # 保留修改時間
        os.utime(target_path, (orig_stat.st_atime, orig_stat.st_mtime))

        return FileResult('success', "OK", original_size, new_size)

    except UnidentifiedImageError:
        return FileResult('failed', f"無法辨識圖片: {filepath.name}")
    except Exception as e:
        return FileResult('failed', f"處理失敗 {filepath.name}: {e}")


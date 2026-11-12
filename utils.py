"""
圖片處理工具 - 共用模組

整合了 Rich UI 視覺化、進度條、匯總表格、隱藏目錄過濾、檔案大小過濾及自訂輸出功能。
"""

import logging
import re
import os
import io
import time
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, Iterable
import argparse

__version__ = "8.6.0"

# 引入 Rich 函式庫做終端機視覺化美化
from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TimeElapsedColumn, 
    TextColumn, BarColumn, TaskProgressColumn
)
from rich.table import Table
from rich import box
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

import pillow_heif
pillow_heif.register_heif_opener()

console = Console()
logger = logging.getLogger("img_tools")

# --- 集中管理常數 ---
# 支援的圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic', '.avif'}

# 用於偵測已壓縮檔案的 regex pattern (e.g. _70%, _50%, _500.0KB, _1.0MB)
COMPRESSED_SUFFIX_PATTERN = re.compile(r'_(\d+%|[\d.]+(B|KB|MB|GB))$', re.IGNORECASE)

# 格式映射表 (副檔名 → PIL format string)
FORMAT_MAP = {
    '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG',
    '.webp': 'WEBP', '.avif': 'AVIF',
}

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


def tune_quality_for_target_size(
    img: Image.Image,
    target_bytes: int,
    output_format: str,
    save_kwargs: dict,
    return_data: bool = False,
) -> int | tuple[int, bytes | None]:
    """使用記憶體二分搜尋法動態逼近符合大小上限的最佳品質 (不超過目標體積，且畫質最高)"""
    low, high = 40, 95
    best_q = low
    best_data: bytes | None = None
    fallback_data: bytes | None = None
    # 複製 save_kwargs 避免副作用
    kwargs = save_kwargs.copy()
    
    # 5 次迭代即可在 40-95 之間精確收斂
    for _ in range(5):
        mid = (low + high) // 2
        kwargs['quality'] = mid
        buf = io.BytesIO()
        try:
            img.save(buf, format=output_format, **kwargs)
            size = buf.tell()
            cur_data = buf.getvalue() if return_data else None
        except Exception:
            size = float('inf')
            cur_data = None
        finally:
            buf.close()
        
        if size <= target_bytes:
            best_q = mid
            best_data = cur_data
            low = mid + 1  # 嘗試看能不能品質更好
        else:
            if mid == 40:
                fallback_data = cur_data
            high = mid - 1 # 太大了，降低品質
            
    if return_data:
        return best_q, (best_data if best_data is not None else fallback_data)
    return best_q


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
    exclude_fn: Callable[[Path], bool] | None = None,
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
            dirs[:] = [
                d for d in dirs 
                if not is_ignored(d) and not (exclude_fn and exclude_fn(root_path / d))
            ]
            
        except ValueError:
            continue

        for filename in filenames:
            f = root_path / filename
            if f.suffix.lower() not in supported_formats:
                continue
            
            files.append(f)
        
    return sorted(files)


def _norm_key(path: Path | str) -> str:
    """產生路徑比較用的正規化鍵值 (一律不分大小寫，以 Windows/macOS 最嚴格的檔案系統為準)"""
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path)))).lower()


def make_output_dir_excluder(
    root: Path, out_dir: Path | None
) -> Callable[[Path], bool] | None:
    """
    若輸出目錄位於來源目錄內部，回傳一個給 collect_files(exclude_fn=...) 用的判斷函式，
    在遍歷階段直接剪除輸出目錄，避免重複處理自己產生的檔案 (out/out/...)。
    輸出目錄不在來源內、或等於來源目錄 (原地模式) 時回傳 None。
    """
    if out_dir is None:
        return None
    try:
        out_key = _norm_key(out_dir.resolve())
        root_key = _norm_key(root.resolve())
    except OSError:
        return None

    if out_key == root_key:
        return None  # 原地模式：不能把整個來源目錄排除
    if not out_key.startswith(root_key.rstrip(os.sep) + os.sep):
        return None  # 輸出目錄在來源之外，不需要排除

    def _exclude(dir_path: Path) -> bool:
        try:
            key = _norm_key(dir_path.resolve())
        except OSError:
            return False
        return key == out_key or key.startswith(out_key + os.sep)

    return _exclude


def assign_conflict_tags(
    files: list[Path],
    target_fn: Callable[[Path, str], Path],
) -> dict[str, str]:
    """
    在送進多程序管線「之前」，於主程序一次性偵測輸出檔名衝突並分配唯一標籤。

    - target_fn(filepath, tag) 必須回傳該檔案在指定 tag 下的輸出路徑 (tag='' 代表原始命名)。
    - 衝突的定義：兩個以上來源檔案對應到同一個輸出路徑 (不分大小寫)，
      例如 a.jpg + a.png → a.webp，或 IMG.heic + IMG.jpg → IMG.jpg。
    - 分配規則：
        1. 群組中若有「副檔名本來就與輸出相同」的檔案 (例如原地壓縮的 IMG.jpg)，它保留原始命名；
           若有多個，取路徑排序第一個。
        2. 其餘成員改用原副檔名當標籤，例如 IMG.heic → IMG_heic.jpg、a.png → a_png.webp。
        3. 若標籤後仍與其他輸出撞名，則依序加上數字 (png2, png3 ...) 直到唯一。
    - 回傳 {str(filepath): tag}，只包含需要改名的檔案；無衝突時為空 dict。
      由於只含衝突檔案，傳給 worker 時的 pickle 成本極低，且可完全消除多程序同時寫入同一檔案的競態。
    """
    groups: dict[str, list[Path]] = {}
    for f in files:
        groups.setdefault(_norm_key(target_fn(f, '')), []).append(f)

    used: set[str] = set()
    pending: list[Path] = []

    for key in sorted(groups):
        members = groups[key]
        if len(members) == 1:
            used.add(key)
            continue
        natural = sorted(
            (m for m in members if m.suffix.lower() == target_fn(m, '').suffix.lower()),
            key=str,
        )
        keeper = natural[0] if natural else None
        if keeper is not None:
            used.add(key)
        pending.extend(m for m in members if m is not keeper)

    tags: dict[str, str] = {}
    for m in sorted(pending, key=str):
        base = m.suffix.lstrip('.') or 'dup'
        tag, n = base, 2
        while _norm_key(target_fn(m, tag)) in used:
            tag = f"{base}{n}"
            n += 1
        used.add(_norm_key(target_fn(m, tag)))
        tags[str(m)] = tag
    return tags


def print_conflict_notice(tags: dict[str, str], target_fn: Callable[[Path, str], Path], limit: int = 10) -> None:
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

    t_start = time.perf_counter()

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
        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(worker_fn, f): f for f in files}

                for future in as_completed(futures):
                    filepath = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        result = FileResult('failed', f"子程序異常 {filepath.name}: {e}")
                    
                    # 如果失敗，將紅色的 Alert 印在進度條上方而不破壞版面
                    if result.status == 'failed':
                        progress.console.print(f"[bold red]{result.message}[/bold red]")
                    # DRY RUN 模式要把每條紀錄印出來
                    elif result.status == 'dry_run':
                        progress.console.print(f"[dim]{result.message}[/dim]")
                    # 需要使用者注意的跳過 (例如動畫圖片、目標已存在的衝突)
                    elif result.warn:
                        progress.console.print(f"[yellow]{result.message}[/yellow]")

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
                    
                    # 動態更新進度條的描述，顯示當前剛處理完的檔案名稱
                    progress.update(task_id, description=f" [cyan]{label}中: {filepath.name}")
                    # 更新進度表
                    progress.advance(task_id)
        except KeyboardInterrupt:
            progress.console.print("\n[bold yellow]警告：使用者中斷 (Ctrl+C)，正在停止...[/bold yellow]")

    summary.elapsed_seconds = time.perf_counter() - t_start
    return summary


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


def print_summary(
    summary: ProcessingSummary,
    success_label: str = "成功處理",
    skip_label: str = "跳過(已存在/隱藏/大小不符)",
    after_label: str = "處理後",
) -> None:
    """使用 Rich Table 印出華麗且易讀的分析報告"""
    
    # 執行結果狀態表格
    status_table = Table(title="\n[分析] 執行結果分析", box=box.ROUNDED, show_header=True, header_style="bold magenta")
    status_table.add_column("狀態", style="dim", width=25)
    status_table.add_column("數量", justify="right", style="bold cyan")

    status_table.add_row(success_label, str(summary.success))
    status_table.add_row(skip_label, str(summary.skipped))
    if summary.size_skip > 0:
        status_table.add_row("跳過 (無效壓縮/體積變大)", str(summary.size_skip))
    
    fail_color = "red" if summary.failed > 0 else "white"
    status_table.add_row(f"[{fail_color}]失敗[/{fail_color}]", f"[{fail_color}]{str(summary.failed)}[/{fail_color}]")
    
    # 總執行時間
    if summary.elapsed_seconds > 0:
        status_table.add_row("總執行時間", _format_elapsed(summary.elapsed_seconds))

    console.print(status_table)

    # 儲存空間統計表格
    if summary.total_original > 0:
        saved = summary.total_original - summary.total_new
        pct = (saved / summary.total_original) * 100
        
        space_table = Table(title="[容量] 磁碟空間變化", box=box.MINIMAL_DOUBLE_HEAD)
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
    default_workers = min(os.cpu_count() or 4, 8)
    parser.add_argument('-w', '--workers', type=int, default=default_workers,
                        help=f'並行處理程序的數量 (預設: {default_workers}，自動偵測 CPU 核心數)')
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
    parser.add_argument('-T', '--target-size', '--target', type=str, default=None,
                        help='目標檔案大小 (自動調校有損壓縮 quality 以逼近此大小)，範例: 1MB, 500KB')
    parser.add_argument('--skip-if-newer', action='store_true',
                        help='如果目標檔案存在且比來源檔案新則跳過 (適用於增量備份)')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='縮放比例 (0.1 - 1.0)，例如 0.5 表示長寬減半 (預設: 1.0)')
    parser.add_argument('--in-place', action='store_true',
                        help='原地覆蓋：直接取代原始檔案 (不加後綴，且會自動刪除/覆蓋原檔，請小心使用)')
    parser.add_argument('--version', action='version', version=f'%(prog)s v{__version__}')
    return parser


def resolve_directory(args: argparse.Namespace) -> str | None:
    """解析目錄路徑 (支援互動模式)，回傳 None 表示使用者未輸入或路徑無效"""
    if not args.directory:
        args.directory = input("請輸入目標來源目錄路徑：").strip()
        if not args.directory:
            console.print("[bold red]未輸入目錄，程式結束。[/bold red]")
            return None
    
    target = Path(args.directory)
    if not target.exists():
        console.print(f"[bold red]錯誤：路徑不存在 → {target}[/bold red]")
        return None
    if not target.is_dir():
        console.print(f"[bold red]錯誤：指定的路徑不是一個目錄 → {target}[/bold red]")
        return None
    return str(args.directory)


def validate_quality(quality: int) -> bool:
    """驗證 quality 參數範圍"""
    if not 1 <= quality <= 100:
        console.print("[bold red]錯誤：壓縮品質 quality 必須在 1-100 之間。[/bold red]")
        return False
    return True


def validate_scale(scale: float) -> bool:
    """驗證 scale 參數範圍，回傳 False 表示無效"""
    if not 0.1 <= scale <= 1.0:
        console.print("[bold red]錯誤：--scale 必須在 0.1-1.0 之間[/bold red]")
        return False
    return True


def build_filter_info(min_size: int | None, max_size: int | None, scale: float, target_size: int | None = None) -> str:
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


# --- 新增：圖片處理核心邏輯 ---

def get_exif_data(img: Image.Image) -> bytes | None:
    """取得圖片的 EXIF 資料"""
    try:
        return img.info.get('exif')
    except Exception:
        return None


# 支援動畫輸出的格式 (其餘格式遇到多影格來源會被跳過，避免只剩第一格)
ANIMATED_OUTPUT_FORMATS = {'WEBP'}


def is_animated_image(img: Image.Image) -> bool:
    """判斷圖片是否為多影格動畫 (動畫 WebP / APNG / 動畫 AVIF 等)"""
    return bool(getattr(img, 'is_animated', False)) and getattr(img, 'n_frames', 1) > 1


def _encode_animated_webp(
    src: Image.Image,
    quality: int,
    scale: float,
    lossless: bool,
    exif_data: bytes | None,
) -> bytes:
    """
    逐格讀取動畫並重新編碼為動畫 WebP，保留每一格的顯示時間 (duration) 與循環次數 (loop)。
    - 每格統一轉為 RGBA，避免調色盤/透明度在影格間不一致。
    - 動畫不套用 --target-size 二分搜尋 (多影格反覆編碼成本過高)，直接使用指定 quality。
    - 使用 method=4：多影格下 method=6 會慢數倍，壓縮率差異極小。
    """
    frames: list[Image.Image] = []
    durations: list[int] = []
    default_duration = int(src.info.get('duration') or 100)

    for frame in ImageSequence.Iterator(src):
        f = frame.convert('RGBA')
        if 0.1 <= scale < 1.0:
            f = f.resize(
                (max(1, int(f.width * scale)), max(1, int(f.height * scale))),
                Image.Resampling.LANCZOS,
            )
        frames.append(f)
        durations.append(int(frame.info.get('duration') or default_duration))

    save_kwargs: dict = {
        'format': 'WEBP',
        'save_all': True,
        'append_images': frames[1:],
        'duration': durations,
        'loop': int(src.info.get('loop', 0)),
    }
    if lossless:
        save_kwargs['lossless'] = True
    else:
        save_kwargs['quality'] = quality
        save_kwargs['method'] = 4
    if exif_data:
        save_kwargs['exif'] = exif_data

    buf = io.BytesIO()
    try:
        frames[0].save(buf, **save_kwargs)
        return buf.getvalue()
    finally:
        buf.close()


def _encode_still_image(
    img: Image.Image,
    output_format: str,
    quality: int,
    keep_exif: bool,
    scale: float,
    lossless: bool,
    original_size: int,
    target_size_bytes: int | None,
) -> bytes:
    """單張靜態圖片的完整編碼流程：EXIF 轉正 → 縮放 → 色彩模式標準化 → (目標大小逼近) → 編碼"""
    # 修正 EXIF 旋轉問題 (手機照片必備) - 必須在 resize 前
    img = ImageOps.exif_transpose(img)

    # 縮放處理
    if 0.1 <= scale < 1.0:
        new_width = max(1, int(img.width * scale))
        new_height = max(1, int(img.height * scale))
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    exif_data = get_exif_data(img) if keep_exif else None

    # 若為 P (調色盤) 模式且含透明資訊，先轉為 RGBA 以保留透明通道供後續白底融合或透明輸出
    if img.mode == 'P' and 'transparency' in img.info:
        img = img.convert('RGBA')

    # 色彩模式標準化與透明背景融合
    if img.mode in ('RGBA', 'LA') and output_format in ('JPEG', 'JPG'):
        bg_color = (255, 255, 255) if img.mode == 'RGBA' else 255
        background = Image.new(img.mode[:-1] if img.mode == 'RGBA' else 'L', img.size, bg_color)
        if img.mode == 'RGBA':
            background.paste(img, mask=img.split()[3])
            img = background.convert('RGB')
        else:
            background.paste(img, mask=img.split()[1])
            img = background.convert('RGB')
    elif img.mode in ('CMYK', 'P') and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        img = img.convert('RGB')

    # 準備儲存參數
    save_kwargs: dict = {'optimize': True}

    if lossless and output_format in ('WEBP', 'AVIF'):
        save_kwargs['lossless'] = True

    if output_format in ('JPEG', 'JPG'):
        # 漸進式 JPEG 參數 (通常檔案大於 10KB 才有額外壓縮效益)
        if original_size > 10240:
            save_kwargs['progressive'] = True
    elif output_format == 'WEBP' and not lossless:
        save_kwargs['method'] = 6  # 啟用最慢但品質最好的 WebP 壓縮方式

    if exif_data:
        save_kwargs['exif'] = exif_data

    data: bytes | None = None

    # 如果設定了目標大小且非無損，進行動態品質自動逼近並快取結果，避免重複編碼
    if target_size_bytes is not None and not lossless and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        quality, data = tune_quality_for_target_size(
            img, target_size_bytes, output_format, save_kwargs, return_data=True
        )

    if not lossless and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        save_kwargs['quality'] = quality

    # 先存到記憶體緩衝區檢查大小 (若二分搜尋已快取則不重複編碼)
    if data is None:
        buf = io.BytesIO()
        try:
            img.save(buf, format=output_format, **save_kwargs)
            data = buf.getvalue()
        finally:
            buf.close()
    return data

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
    file_stat: os.stat_result | None = None,
    target_size_bytes: int | None = None
) -> FileResult:
    """
    圖片處理核心邏輯：
    1. 開啟圖片並判斷是否為動畫
    2. 動畫：輸出格式支援 (WebP) 則逐格重新編碼；否則跳過並保留原檔，避免只剩第一格
    3. 靜態：EXIF 轉正 → 縮放 → 色彩空間轉換 → (目標大小逼近) → 編碼
    4. 儲存至緩衝區檢查大小
    5. 決定是否寫入硬碟 (原子寫入)
    """
    try:
        orig_stat = file_stat if file_stat is not None else filepath.stat()
        original_size = orig_stat.st_size

        # 決定最終格式 (必須在色彩模式轉換與動畫判斷前完成)
        if not output_format:
            output_format = FORMAT_MAP.get(target_path.suffix.lower(), 'JPEG')
        else:
            output_format = output_format.upper()

        # src 保留原始開檔物件，確保 finally 一定關閉 file handle。
        # 動畫逐格讀取時檔案會保持開啟；若不先關閉，原地覆蓋 (target == filepath)
        # 在 Windows 上 os.replace 會因檔案被占用而失敗。
        src = Image.open(filepath)
        try:
            if is_animated_image(src):
                if output_format not in ANIMATED_OUTPUT_FORMATS:
                    return FileResult(
                        'skipped',
                        f"跳過動畫圖片 ({getattr(src, 'n_frames', '?')} 格)：輸出格式 {output_format} "
                        f"不支援動畫，已保留原檔 → {filepath.name}",
                        warn=True,
                    )
                exif_data = get_exif_data(src) if keep_exif else None
                data = _encode_animated_webp(src, quality, scale, lossless, exif_data)
            else:
                src.load()  # 強制讀入記憶體
                data = _encode_still_image(
                    src, output_format, quality, keep_exif, scale,
                    lossless, original_size, target_size_bytes,
                )
        finally:
            src.close()

        new_size = len(data)

        # 檢查是否越壓越大 (排除特定轉檔需求)
        orig_ext = filepath.suffix.lower()
        should_force = force_convert_from and orig_ext in force_convert_from

        if skip_if_larger and new_size >= original_size and not should_force:
            return FileResult('size_skip', f"檔案 {filepath.name} 越壓越大，捨棄變更")

        # 確保目錄存在
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 原子寫入：先寫暫存檔，再 rename，防止寫入中途斷電毀損原檔
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                suffix=target_path.suffix,
                dir=str(target_path.parent)
            )
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            
            # Windows 唯讀屬性相容性修復
            if target_path.exists():
                try:
                    import stat
                    os.chmod(target_path, stat.S_IWRITE)
                except Exception:
                    pass
                    
            os.replace(tmp_path, str(target_path))
        except Exception:
            # 若原子寫入失敗，清理暫存檔後 fallback 直寫
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            
            if target_path.exists():
                try:
                    import stat
                    os.chmod(target_path, stat.S_IWRITE)
                except Exception:
                    pass
                    
            with open(target_path, 'wb') as f:
                f.write(data)

        # 保留修改時間
        os.utime(target_path, (orig_stat.st_atime, orig_stat.st_mtime))

        return FileResult('success', "OK", original_size, new_size)

    except UnidentifiedImageError:
        return FileResult('failed', f"無法辨識圖片: {filepath.name}")
    except Exception as e:
        return FileResult('failed', f"處理失敗 {filepath.name}: {e}")

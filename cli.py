"""
圖片處理工具 - CLI 參數解析、檔案收集與衝突偵測模組
"""

import argparse
import os
import re
from pathlib import Path
from typing import Callable, Iterable

from ui import console

__version__ = "8.10.0"


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

    def is_ignored(part: str) -> bool:
        return part.startswith('.') or part.startswith('__') or part in exclude_dirs

    for root, dirs, filenames in os.walk(directory):
        root_path = Path(root)
        try:
            rel = root_path.relative_to(directory)
            depth = len(rel.parts)

            if max_depth is not None and depth > max_depth:
                dirs[:] = []
                continue

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
        return None
    if not out_key.startswith(root_key.rstrip(os.sep) + os.sep):
        return None

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
    parser.add_argument('--max-dim', type=int, default=None, metavar='PX',
                        help='限制最長邊像素 (只縮小不放大)，例如 1920；可與 --scale 併用')
    parser.add_argument('--strip-gps', action='store_true',
                        help='移除 GPS 位置資訊，保留其餘 EXIF (會自動啟用 --keep-exif)')
    parser.add_argument('--in-place', action='store_true',
                        help='原地覆蓋：直接取代原始檔案 (不加後綴，且會自動刪除/覆蓋原檔，請小心使用)')
    parser.add_argument('--report', type=str, default=None,
                        help='匯出逐檔處理結果的 CSV 報表路徑，範例: --report out.csv')
    parser.add_argument('--version', action='version', version=f'%(prog)s v{__version__}')
    return parser


def resolve_directory(args: argparse.Namespace) -> str | None:
    """解析目錄路徑 (支援互動模式，並自動移除拖曳路徑帶入的引號)，回傳 None 表示路徑無效"""
    if not args.directory:
        raw_input = input("請輸入目標來源目錄路徑：")
    else:
        raw_input = args.directory

    cleaned = raw_input.strip().strip('"').strip("'").strip()
    args.directory = cleaned
    if not cleaned:
        console.print("[bold red]未輸入目錄，程式結束。[/bold red]")
        return None

    target = Path(cleaned)
    if not target.exists():
        console.print(f"[bold red]錯誤：路徑不存在 → {target}[/bold red]")
        return None
    if not target.is_dir():
        console.print(f"[bold red]錯誤：指定的路徑不是一個目錄 → {target}[/bold red]")
        return None
    return str(target)


def validate_quality(quality: int) -> bool:
    """驗證 quality 參數範圍"""
    if not 1 <= quality <= 100:
        console.print("[bold red]錯誤：壓縮品質 quality 必須在 1-100 之間。[/bold red]")
        return False
    return True


def validate_max_dim(max_dim: int | None) -> bool:
    """驗證 --max-dim 參數 (須為正整數)，回傳 False 表示無效"""
    if max_dim is not None and max_dim < 1:
        console.print("[bold red]錯誤：--max-dim 必須是大於 0 的整數 (像素)[/bold red]")
        return False
    return True


def validate_scale(scale: float) -> bool:
    """驗證 scale 參數範圍，回傳 False 表示無效"""
    if not 0.1 <= scale <= 1.0:
        console.print("[bold red]錯誤：--scale 必須在 0.1-1.0 之間[/bold red]")
        return False
    return True

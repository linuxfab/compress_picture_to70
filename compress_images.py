"""
圖片壓縮工具 v2.1
遍歷指定目錄及子目錄，將圖片壓縮後另存新檔

功能:
- 自訂壓縮比例 (--quality)
- 並行處理加速
- 覆蓋/跳過已存在檔案 (--overwrite)
- 保留 EXIF 資訊 (--keep-exif)
- 自動跳過壓縮後變大的檔案
- Dry-run 模式預覽
- 總空間節省統計
"""

import re
import argparse
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 支援的圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

# 用於偵測已壓縮檔案的 regex pattern (e.g. _70%, _50%)
COMPRESSED_SUFFIX_PATTERN = re.compile(r'_\d+%$')

# 統計計數器 (thread-safe)
stats_lock = threading.Lock()
stats = {
    'success': 0, 'skipped': 0, 'failed': 0, 'size_skip': 0,
    'total_original': 0, 'total_new': 0,
}


def get_exif(image: Image.Image) -> bytes | None:
    """取得圖片的 EXIF 資料"""
    try:
        return image.info.get('exif')
    except Exception:
        return None


def compress_image(
    filepath: Path, quality: int, overwrite: bool, keep_exif: bool, dry_run: bool
) -> tuple[str, str, int, int]:
    """
    壓縮單張圖片並另存新檔

    Returns:
        tuple: (狀態, 訊息, 原始大小, 新大小)
    """
    try:
        suffix = f"_{quality}%"

        # 檢查是否已經是壓縮過的檔案 (匹配任何 _數字% pattern)
        if COMPRESSED_SUFFIX_PATTERN.search(filepath.stem):
            return ('skipped', f"跳過已壓縮: {filepath.name}", 0, 0)

        # 建立新檔名
        new_name = f"{filepath.stem}{suffix}{filepath.suffix}"
        new_path = filepath.parent / new_name

        # 檢查檔案是否已存在
        if new_path.exists() and not overwrite:
            return ('skipped', f"檔案已存在(跳過): {new_name}", 0, 0)

        original_size = filepath.stat().st_size

        # Dry-run 模式：僅報告，不實際壓縮
        if dry_run:
            return (
                'dry_run',
                f"[預覽] {filepath.name} -> {new_name} ({original_size / 1024:.1f}KB)",
                0, 0,
            )

        # 開啟圖片
        img = Image.open(filepath)

        # 取得 EXIF
        exif_data = get_exif(img) if keep_exif else None

        # 準備儲存參數
        save_kwargs = {'optimize': True}

        if filepath.suffix.lower() in {'.jpg', '.jpeg', '.webp'}:
            save_kwargs['quality'] = quality
            if exif_data:
                save_kwargs['exif'] = exif_data
            # 確保是 RGB 模式
            if img.mode == 'RGBA':
                img = img.convert('RGB')
        elif filepath.suffix.lower() == '.png':
            # PNG 不支援 quality，使用 optimize
            pass

        # 判斷輸出格式
        ext = filepath.suffix.lower()
        format_map = {
            '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG',
            '.webp': 'WEBP', '.bmp': 'BMP',
        }
        output_format = format_map.get(ext, 'JPEG')

        # 先存到暫存路徑檢查大小
        temp_path = new_path.with_suffix('.tmp')
        img.save(temp_path, format=output_format, **save_kwargs)
        new_size = temp_path.stat().st_size

        # 檢查是否壓縮後反而變大
        if new_size >= original_size:
            temp_path.unlink()  # 刪除暫存檔
            return (
                'size_skip',
                f"壓縮後變大，跳過: {filepath.name} "
                f"({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB)",
                0, 0,
            )

        # 重新命名為正式檔名
        if new_path.exists():
            new_path.unlink()
        temp_path.rename(new_path)

        reduction = (1 - new_size / original_size) * 100
        return (
            'success',
            f"✓ {filepath.name} -> {new_name} "
            f"({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB, -{reduction:.1f}%)",
            original_size, new_size,
        )

    except Exception as e:
        return ('failed', f"✗ 處理失敗 {filepath}: {e}", 0, 0)


def process_directory(
    directory: str, quality: int, overwrite: bool,
    keep_exif: bool, workers: int, dry_run: bool,
) -> dict:
    """
    處理目錄及所有子目錄中的圖片 (並行處理)
    """
    global stats
    stats = {
        'success': 0, 'skipped': 0, 'failed': 0, 'size_skip': 0,
        'total_original': 0, 'total_new': 0,
    }

    root_path = Path(directory)

    if not root_path.exists():
        print(f"目錄不存在: {directory}")
        return stats

    # 收集所有圖片檔案
    files = [
        f for f in root_path.rglob('*')
        if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
    ]

    total = len(files)
    if dry_run:
        print(f"[DRY-RUN] 找到 {total} 張圖片，預覽模式（不會實際壓縮）...")
    else:
        print(f"找到 {total} 張圖片，開始處理...")
    print("=" * 60)

    # 並行處理
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                compress_image, f, quality, overwrite, keep_exif, dry_run
            ): f
            for f in files
        }

        for i, future in enumerate(as_completed(futures), 1):
            status, message, orig_size, new_size = future.result()
            print(f"[{i}/{total}] {message}")

            with stats_lock:
                if status == 'success':
                    stats['success'] += 1
                    stats['total_original'] += orig_size
                    stats['total_new'] += new_size
                elif status in ('skipped', 'dry_run'):
                    stats['skipped'] += 1
                elif status == 'size_skip':
                    stats['size_skip'] += 1
                else:
                    stats['failed'] += 1

    return stats


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


def main():
    parser = argparse.ArgumentParser(
        description='圖片批量壓縮工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
範例:
  python compress_images.py "D:\\Photos" --quality 50
  python compress_images.py "D:\\Photos" --quality 80 --overwrite --keep-exif
  python compress_images.py "D:\\Photos" -q 70 -w 8
  python compress_images.py "D:\\Photos" --dry-run
        '''
    )

    parser.add_argument('directory', nargs='?', help='目標目錄路徑')
    parser.add_argument('-q', '--quality', type=int, default=70,
                        help='壓縮品質 1-100 (預設: 70)')
    parser.add_argument('-o', '--overwrite', action='store_true',
                        help='覆蓋已存在的壓縮檔')
    parser.add_argument('-e', '--keep-exif', action='store_true',
                        help='保留 EXIF 資訊 (GPS、拍攝時間等)')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='並行處理執行緒數 (預設: 4)')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='預覽模式：僅列出待處理檔案，不實際壓縮')

    args = parser.parse_args()

    # 互動模式
    if not args.directory:
        args.directory = input("請輸入目標目錄路徑: ").strip()
        if not args.directory:
            print("未輸入目錄，程式結束")
            return

    # 驗證 quality 範圍
    if not 1 <= args.quality <= 100:
        print("錯誤: quality 必須在 1-100 之間")
        return

    print(f"\n圖片壓縮工具 v2.1")
    print(f"目標目錄: {args.directory}")
    print(f"壓縮品質: {args.quality}%")
    print(f"覆蓋模式: {'是' if args.overwrite else '否'}")
    print(f"保留EXIF: {'是' if args.keep_exif else '否'}")
    print(f"執行緒數: {args.workers}")
    if args.dry_run:
        print("模式: 🔍 DRY-RUN (預覽)")
    print("=" * 60)

    result = process_directory(
        args.directory,
        args.quality,
        args.overwrite,
        args.keep_exif,
        args.workers,
        args.dry_run,
    )

    print("=" * 60)
    print("處理完成!")
    print(f"  成功壓縮: {result['success']}")
    print(f"  跳過(已存在/已壓縮): {result['skipped']}")
    print(f"  跳過(壓縮後變大): {result['size_skip']}")
    print(f"  失敗: {result['failed']}")

    # 顯示總空間節省統計
    if result['total_original'] > 0:
        saved = result['total_original'] - result['total_new']
        pct = (saved / result['total_original']) * 100
        print(f"\n  📊 空間統計:")
        print(f"     原始總大小: {format_size(result['total_original'])}")
        print(f"     壓縮後總大小: {format_size(result['total_new'])}")
        print(f"     總共節省: {format_size(saved)} ({pct:.1f}%)")


if __name__ == "__main__":
    main()

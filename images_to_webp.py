"""
圖片轉 WebP 工具 v1.1
遍歷指定目錄及子目錄，將圖片轉換為 WebP 格式並保留目錄結構存於 webpimage 資料夾

功能:
- 自動轉換 JPG/PNG/BMP 為 WebP
- 保持原始目錄結構，輸出至 webpimage 目錄
- 自訂壓縮品質 (--quality)
- 並行處理加速
- 覆蓋/跳過已存在檔案 (--overwrite)
- Dry-run 模式預覽
- 總空間節省統計
"""

import argparse
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 支援的輸入圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp'}

# 統計計數器 (thread-safe)
stats_lock = threading.Lock()
stats = {
    'success': 0, 'skipped': 0, 'failed': 0,
    'total_original': 0, 'total_new': 0,
}


def convert_to_webp(
    filepath: Path, root_dir: Path, quality: int, overwrite: bool, dry_run: bool
) -> tuple[str, str, int, int]:
    """
    將單張圖片轉換為 WebP 並另存新檔

    Args:
        filepath: 來源檔案路徑
        root_dir: 根目錄路徑(用於計算相對路徑)
        quality: WebP 壓縮品質
        overwrite: 是否覆蓋已存在檔案
        dry_run: 是否為預覽模式

    Returns:
        tuple: (狀態, 訊息, 原始大小, 新大小)
    """
    try:
        # 計算相對路徑
        try:
            rel_path = filepath.relative_to(root_dir)
        except ValueError:
            # 如果檔案不在 root_dir 下 (理論上不應發生)，就直接用檔名
            rel_path = Path(filepath.name)

        # 設定目標目錄與檔案路徑
        # 目標為: root_dir / webpimage / 相對路徑結構
        target_root = root_dir / 'webpimage'

        # 構建目標檔案的完整路徑 (更換副檔名為 .webp)
        target_path = target_root / rel_path.with_suffix('.webp')

        # 檢查檔案是否已存在
        if target_path.exists() and not overwrite:
            return ('skipped', f"檔案已存在(跳過): {target_path.name}", 0, 0)

        original_size = filepath.stat().st_size

        # Dry-run 模式：僅報告，不實際轉換
        if dry_run:
            return (
                'dry_run',
                f"[預覽] {filepath.name} -> {rel_path.with_suffix('.webp')} "
                f"({original_size / 1024:.1f}KB)",
                0, 0,
            )

        # 確保目標目錄存在
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 開啟圖片
        img = Image.open(filepath)

        # 轉換為 RGB (WebP 不支援 CMYK, P 等模式需要轉一下比較保險)
        # PNG 若有透明度 (RGBA) 轉 WebP 是支援的，所以只處理不支援的模式
        if img.mode == 'CMYK':
            img = img.convert('RGB')

        # 儲存為 WebP
        # lossless=False (預設), quality 參數生效
        img.save(target_path, 'WEBP', quality=quality)

        new_size = target_path.stat().st_size

        reduction = 0
        if original_size > 0:
            reduction = (1 - new_size / original_size) * 100

        return (
            'success',
            f"✓ {filepath.name} -> {target_path.name} "
            f"({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB, -{reduction:.1f}%)",
            original_size, new_size,
        )

    except Exception as e:
        return ('failed', f"✗ 處理失敗 {filepath}: {e}", 0, 0)


def process_directory(
    directory: str, quality: int, overwrite: bool, workers: int, dry_run: bool
) -> dict:
    """
    處理目錄及所有子目錄中的圖片 (並行處理)
    """
    global stats
    stats = {
        'success': 0, 'skipped': 0, 'failed': 0,
        'total_original': 0, 'total_new': 0,
    }

    root_path = Path(directory)

    if not root_path.exists():
        print(f"目錄不存在: {directory}")
        return stats

    # 輸出目錄名稱
    target_dir_name = 'webpimage'

    # 收集所有圖片檔案
    files = []
    # 使用 rglob 遍歷
    for f in root_path.rglob('*'):
        if not f.is_file():
            continue

        # 檢查副檔名
        if f.suffix.lower() not in SUPPORTED_FORMATS:
            continue

        # 排除目標目錄 (避免遞迴處理生成的檔案)
        # 檢查路徑中是否包含 webpimage
        try:
            rel = f.relative_to(root_path)
            parts = rel.parts
            if target_dir_name in parts:
                continue
        except ValueError:
            pass

        files.append(f)

    total = len(files)
    if dry_run:
        print(f"[DRY-RUN] 找到 {total} 張可處理圖片，預覽模式（不會實際轉換）...")
    else:
        print(f"找到 {total} 張可處理圖片，開始轉換...")
    print(f"輸出目錄將位於: {root_path / target_dir_name}")
    print("=" * 60)

    if total == 0:
        return stats

    # 並行處理
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                convert_to_webp, f, root_path, quality, overwrite, dry_run
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
        description='圖片轉 WebP 工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
範例:
  python images_to_webp.py "D:\\Photos" --quality 75
  python images_to_webp.py "D:\\Photos" -q 80 --overwrite
  python images_to_webp.py "D:\\Photos" -w 8
  python images_to_webp.py "D:\\Photos" --dry-run
        '''
    )

    parser.add_argument('directory', nargs='?', help='目標目錄路徑')
    parser.add_argument('-q', '--quality', type=int, default=80,
                        help='WebP 壓縮品質 1-100 (預設: 80)')
    parser.add_argument('-o', '--overwrite', action='store_true',
                        help='覆蓋已存在的 WebP 檔案')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='並行處理執行緒數 (預設: 4)')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='預覽模式：僅列出待處理檔案，不實際轉換')

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

    print(f"\n圖片轉 WebP 工具 v1.1")
    print(f"目標目錄: {args.directory}")
    print(f"WebP 品質: {args.quality}%")
    print(f"覆蓋模式: {'是' if args.overwrite else '否'}")
    print(f"執行緒數: {args.workers}")
    if args.dry_run:
        print("模式: 🔍 DRY-RUN (預覽)")
    print("=" * 60)

    result = process_directory(
        args.directory,
        args.quality,
        args.overwrite,
        args.workers,
        args.dry_run,
    )

    print("=" * 60)
    print("處理完成!")
    print(f"  成功轉換: {result['success']}")
    print(f"  跳過(已存在): {result['skipped']}")
    print(f"  失敗: {result['failed']}")

    # 顯示總空間節省統計
    if result['total_original'] > 0:
        saved = result['total_original'] - result['total_new']
        pct = (saved / result['total_original']) * 100
        print(f"\n  📊 空間統計:")
        print(f"     原始總大小: {format_size(result['total_original'])}")
        print(f"     轉換後總大小: {format_size(result['total_new'])}")
        print(f"     總共節省: {format_size(saved)} ({pct:.1f}%)")


if __name__ == "__main__":
    main()

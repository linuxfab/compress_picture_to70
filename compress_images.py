"""
圖片壓縮工具 v4.0
遍歷指定目錄及子目錄，將圖片壓縮後另存新檔

功能:
- 自訂壓縮比例 (--quality)
- 並行處理加速 (多執行緒)
- 覆蓋/跳過已存在檔案 (--overwrite)
- 保留 EXIF 資訊 (--keep-exif)
- 自動跳過壓縮後變大的檔案
- Dry-run 模式預覽
- 總空間節省統計
- 支援深度控制 (--max-depth)
- 跳過無效壓縮格式 (BMP)
"""

import re
from pathlib import Path
from functools import partial
from PIL import Image

from utils import (
    FileResult, collect_files, run_pipeline, print_summary,
    create_base_parser, resolve_directory, validate_quality,
    setup_logger, logger
)

# 支援的圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

# 用於偵測已壓縮檔案的 regex pattern (e.g. _70%, _50%)
COMPRESSED_SUFFIX_PATTERN = re.compile(r'_\d+%$')


def get_exif(image: Image.Image) -> bytes | None:
    """取得圖片的 EXIF 資料"""
    try:
        return image.info.get('exif')
    except Exception:
        return None


def compress_image(
    filepath: Path, quality: int, overwrite: bool, keep_exif: bool, dry_run: bool
) -> FileResult:
    """壓縮單張圖片並另存新檔"""
    try:
        suffix = f"_{quality}%"
        
        # BMP 直接跳過
        if filepath.suffix.lower() == '.bmp':
            return FileResult('skipped', f"跳過 BMP (不支援無損或有損壓縮): {filepath.name}")

        # 檢查是否已經是壓縮過的檔案 (匹配任何 _數字% pattern)
        if COMPRESSED_SUFFIX_PATTERN.search(filepath.stem):
            return FileResult('skipped', f"跳過已壓縮: {filepath.name}")

        # 建立新檔名
        new_name = f"{filepath.stem}{suffix}{filepath.suffix}"
        new_path = filepath.parent / new_name

        # 檢查檔案是否已存在
        if new_path.exists() and not overwrite:
            return FileResult('skipped', f"檔案已存在(跳過): {new_name}")

        original_size = filepath.stat().st_size

        # Dry-run 模式
        if dry_run:
            return FileResult(
                'dry_run',
                f"[預覽] {filepath.name} -> {new_name} ({original_size / 1024:.1f}KB)",
            )

        # 開啟圖片
        img = Image.open(filepath)
        exif_data = get_exif(img) if keep_exif else None

        # 準備儲存參數
        save_kwargs = {'optimize': True}

        if filepath.suffix.lower() in {'.jpg', '.jpeg', '.webp'}:
            save_kwargs['quality'] = quality
            if exif_data:
                save_kwargs['exif'] = exif_data
            if img.mode == 'RGBA':
                img = img.convert('RGB')
        elif filepath.suffix.lower() == '.png':
            pass  # PNG 不支援 quality，使用 optimize

        # 判斷輸出格式
        ext = filepath.suffix.lower()
        format_map = {
            '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'
        }
        output_format = format_map.get(ext, 'JPEG')

        # 先存到暫存路徑檢查大小
        temp_path = new_path.with_suffix('.tmp')
        img.save(temp_path, format=output_format, **save_kwargs)
        new_size = temp_path.stat().st_size

        # 壓縮後反而變大
        if new_size >= original_size:
            temp_path.unlink()
            return FileResult(
                'size_skip',
                f"壓縮後變大，跳過: {filepath.name} "
                f"({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB)",
            )

        # 重新命名為正式檔名
        if new_path.exists():
            new_path.unlink()
        temp_path.rename(new_path)

        reduction = (1 - new_size / original_size) * 100
        return FileResult(
            'success',
            f"✓ {filepath.name} -> {new_name} "
            f"({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB, -{reduction:.1f}%)",
            original_size, new_size,
        )

    except Exception as e:
        return FileResult('failed', f"✗ 處理失敗 {filepath}: {e}")


def main():
    setup_logger()
    
    parser = create_base_parser(
        description='圖片批量壓縮工具',
        epilog='''
範例:
  python compress_images.py "D:\\Photos" --quality 50
  python compress_images.py "D:\\Photos" --quality 80 --overwrite --keep-exif
  python compress_images.py "D:\\Photos" -q 70 -w 8 -d 1
  python compress_images.py "D:\\Photos" --dry-run
        '''
    )
    parser.add_argument('-q', '--quality', type=int, default=70,
                        help='壓縮品質 1-100 (預設: 70)')
    parser.add_argument('-o', '--overwrite', action='store_true',
                        help='覆蓋已存在的壓縮檔')
    parser.add_argument('-e', '--keep-exif', action='store_true',
                        help='保留 EXIF 資訊 (GPS、拍攝時間等)')

    args = parser.parse_args()

    directory = resolve_directory(args)
    if not directory:
        return
    if not validate_quality(args.quality):
        return

    root_path = Path(directory)
    if not root_path.exists():
        logger.error(f"目錄不存在: {directory}")
        return

    logger.info(f"\n圖片壓縮工具 v4.0")
    logger.info(f"目標目錄: {directory}")
    logger.info(f"壓縮品質: {args.quality}%")
    logger.info(f"覆蓋模式: {'是' if args.overwrite else '否'}")
    logger.info(f"保留EXIF: {'是' if args.keep_exif else '否'}")
    logger.info(f"最大深度: {'無限' if args.max_depth is None else args.max_depth}")
    logger.info(f"Process 數: {args.workers}")
    if args.dry_run:
        logger.info("模式: 🔍 DRY-RUN (預覽)")
    logger.info("=" * 60)

    files = collect_files(root_path, SUPPORTED_FORMATS, max_depth=args.max_depth)

    worker = partial(
        compress_image,
        quality=args.quality,
        overwrite=args.overwrite,
        keep_exif=args.keep_exif,
        dry_run=args.dry_run,
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="壓縮")
    print_summary(summary, success_label="成功壓縮", skip_label="跳過(已存在/BMP)")


if __name__ == "__main__":
    main()

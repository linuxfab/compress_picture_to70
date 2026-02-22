"""
圖片轉 WebP 工具 v2.0
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

from pathlib import Path
from functools import partial
from PIL import Image

from utils import (
    FileResult, collect_files, run_pipeline, print_summary,
    create_base_parser, resolve_directory, validate_quality,
)

# 支援的輸入圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp'}

# 輸出目錄名稱
TARGET_DIR_NAME = 'webpimage'


def convert_to_webp(
    filepath: Path, root_dir: Path, quality: int, overwrite: bool, dry_run: bool
) -> FileResult:
    """將單張圖片轉換為 WebP 並另存新檔"""
    try:
        # 計算相對路徑
        try:
            rel_path = filepath.relative_to(root_dir)
        except ValueError:
            rel_path = Path(filepath.name)

        target_root = root_dir / TARGET_DIR_NAME
        target_path = target_root / rel_path.with_suffix('.webp')

        # 檢查檔案是否已存在
        if target_path.exists() and not overwrite:
            return FileResult('skipped', f"檔案已存在(跳過): {target_path.name}")

        original_size = filepath.stat().st_size

        # Dry-run 模式
        if dry_run:
            return FileResult(
                'dry_run',
                f"[預覽] {filepath.name} -> {rel_path.with_suffix('.webp')} "
                f"({original_size / 1024:.1f}KB)",
            )

        # 確保目標目錄存在
        target_path.parent.mkdir(parents=True, exist_ok=True)

        img = Image.open(filepath)

        # 轉換不支援的色彩模式
        if img.mode == 'CMYK':
            img = img.convert('RGB')

        # 儲存為 WebP
        img.save(target_path, 'WEBP', quality=quality)
        new_size = target_path.stat().st_size

        reduction = 0
        if original_size > 0:
            reduction = (1 - new_size / original_size) * 100

        return FileResult(
            'success',
            f"✓ {filepath.name} -> {target_path.name} "
            f"({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB, -{reduction:.1f}%)",
            original_size, new_size,
        )

    except Exception as e:
        return FileResult('failed', f"✗ 處理失敗 {filepath}: {e}")


def main():
    parser = create_base_parser(
        description='圖片轉 WebP 工具',
        epilog='''
範例:
  python images_to_webp.py "D:\\Photos" --quality 75
  python images_to_webp.py "D:\\Photos" -q 80 --overwrite
  python images_to_webp.py "D:\\Photos" -w 8
  python images_to_webp.py "D:\\Photos" --dry-run
        '''
    )
    parser.add_argument('-q', '--quality', type=int, default=80,
                        help='WebP 壓縮品質 1-100 (預設: 80)')
    parser.add_argument('-o', '--overwrite', action='store_true',
                        help='覆蓋已存在的 WebP 檔案')

    args = parser.parse_args()

    directory = resolve_directory(args)
    if not directory:
        return
    if not validate_quality(args.quality):
        return

    root_path = Path(directory)
    if not root_path.exists():
        print(f"目錄不存在: {directory}")
        return

    print(f"\n圖片轉 WebP 工具 v2.0")
    print(f"目標目錄: {directory}")
    print(f"WebP 品質: {args.quality}%")
    print(f"覆蓋模式: {'是' if args.overwrite else '否'}")
    print(f"執行緒數: {args.workers}")
    if args.dry_run:
        print("模式: 🔍 DRY-RUN (預覽)")
    print(f"輸出目錄: {root_path / TARGET_DIR_NAME}")
    print("=" * 60)

    files = collect_files(root_path, SUPPORTED_FORMATS, exclude_dirs={TARGET_DIR_NAME})

    worker = partial(
        convert_to_webp,
        root_dir=root_path,
        quality=args.quality,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="轉換")
    print_summary(summary, success_label="成功轉換", skip_label="跳過(已存在)", after_label="轉換後")


if __name__ == "__main__":
    main()

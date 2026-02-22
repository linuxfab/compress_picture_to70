"""
圖片轉 WebP 工具 v5.0
遍歷指定目錄及子目錄，將所有格式圖片 (含 HEIC / AVIF 等特規檔)
轉換為 WebP 格式並保留目錄結構。
可自由指定 `--out-dir` 與 尺寸過濾 (--min-size, --max-size)。
"""

from pathlib import Path
from functools import partial
from PIL import Image

import pillow_heif
pillow_heif.register_heif_opener()


from utils import (
    FileResult, collect_files, run_pipeline, print_summary,
    create_base_parser, resolve_directory, validate_quality,
    parse_size_to_bytes, format_size, setup_logger, console
)
from rich.panel import Panel

# 支援的輸入圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.heic', '.avif'}


def get_exif(image: Image.Image) -> bytes | None:
    """取得圖片的 EXIF 資料"""
    try:
        return image.info.get('exif')
    except Exception:
        return None


def convert_to_webp(
    filepath: Path, root_dir: Path, target_root: Path, quality: int, 
    overwrite: bool, dry_run: bool, lossless: bool, keep_exif: bool
) -> FileResult:
    """將單張圖片轉換為 WebP 並另存新檔"""
    try:
        # 計算相對路徑複製樹狀結構
        try:
            rel_path = filepath.relative_to(root_dir)
        except ValueError:
            rel_path = Path(filepath.name)

        target_path = target_root / rel_path.with_suffix('.webp')

        # 檢查檔案是否已存在
        if target_path.exists() and not overwrite:
            return FileResult('skipped', f"檔案已存在(跳過): {target_path.name}")

        original_size = filepath.stat().st_size

        # Dry-run 模式
        if dry_run:
            return FileResult(
                'dry_run',
                f"此檔案即將轉換: {target_path.name} ({original_size / 1024:.1f}KB)",
            )

        # 確保目標目錄存在
        if dry_run is False:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        img = Image.open(filepath)
        exif_data = get_exif(img) if keep_exif else None
        
        # 轉換不支援的色彩模式
        if img.mode in ('CMYK', 'P'):
            img = img.convert('RGB')

        # 儲存參數
        save_kwargs = {'format': 'WEBP', 'lossless': lossless}
        if not lossless:
            save_kwargs['quality'] = quality
        if exif_data:
            save_kwargs['exif'] = exif_data

        # 儲存為 WebP
        img.save(target_path, **save_kwargs)
        new_size = target_path.stat().st_size

        return FileResult(
            'success',
            "已隱藏", # rich進度條自行處理即可
            original_size, new_size,
        )

    except Exception as e:
        return FileResult('failed', f"檔案 {filepath.name} 解析失敗: {e}")


def main():
    setup_logger()
    
    parser = create_base_parser(
        description='圖片轉 WebP 工具 (支援 iPhone 照片與自訂尺寸過濾)',
        epilog='''
範例:
  python images_to_webp.py "D:\\Photos" --min-size 1MB
  # 挑選 E 碟裡 200KB~5MB 的圖檔跨碟鏡像匯出，並轉換成 WebP 無損格式
  python images_to_webp.py "D:\\Photos" -O "F:\\Backup_Webp" --min-size 200KB --max-size 5MB --lossless --keep-exif
        '''
    )
    # 增加 WebP 專屬選項
    parser.add_argument('-q', '--quality', type=int, default=80,
                        help='WebP 壓縮品質 1-100 (預設: 80)')
    parser.add_argument('-o', '--overwrite', action='store_true',
                        help='覆蓋已存在的 WebP 檔案')
    parser.add_argument('-l', '--lossless', action='store_true',
                        help='使用無損壓縮 (預設: 有損)')
    parser.add_argument('-e', '--keep-exif', action='store_true',
                        help='保留 EXIF 資訊')

    args = parser.parse_args()

    min_size = parse_size_to_bytes(args.min_size)
    max_size = parse_size_to_bytes(args.max_size)

    directory = resolve_directory(args)
    if not directory or not (args.lossless or validate_quality(args.quality)):
        return

    root_path = Path(directory)
    if not root_path.exists():
        console.print(f"[bold red]❌ 目錄不存在: {directory}[/bold red]")
        return
        
    out_dir_path = Path(args.out_dir) if args.out_dir else root_path / "webpimage"

    welcome_str = (
        f"📂 [bold cyan]來源掃描目錄[/bold cyan]: {directory}\n"
        f"📁 [bold magenta]鏡像輸出位置[/bold magenta]: {out_dir_path}\n"
        f"⚙️  [bold yellow]WebP 模式[/bold yellow]: {'Lossless (無損)' if args.lossless else f'Lossy (品質 {args.quality}%)'}\n"
        f"⚖️  [bold yellow]過濾範圍[/bold yellow]: {'不限' if not min_size else format_size(min_size)} ~ {'不限' if not max_size else format_size(max_size)}\n"
        f"🚀 [bold green]並發數量[/bold green]: {args.workers} 行程"
    )
    console.print(Panel.fit(welcome_str, title="[bold]圖片轉 WebP 批次工具 v5.0[/bold]"))

    exclude_targets = {out_dir_path.name} if out_dir_path.parent == root_path else set()
    files = collect_files(
        root_path, SUPPORTED_FORMATS, exclude_dirs=exclude_targets, 
        max_depth=args.max_depth, min_size_bytes=min_size, max_size_bytes=max_size
    )

    worker = partial(
        convert_to_webp,
        root_dir=root_path,
        target_root=out_dir_path,
        quality=args.quality,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        lossless=args.lossless,
        keep_exif=args.keep_exif
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="跨格式轉換")
    
    after_label_word = "無損 Webp後" if args.lossless else f"Webp ({args.quality}%)後"
    print_summary(summary, success_label="WebP 轉換匯出成功", skip_label="跳過(尺寸不符/已存在)", after_label=after_label_word)

if __name__ == "__main__":
    main()

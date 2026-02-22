"""
圖片壓縮工具 v6.0
遍歷指定目錄及子目錄，將圖片壓縮後另存新檔

功能:
- 自訂壓縮比例 (--quality)
- 並行處理加速 (多執行緒)
- 支援 `--out-dir` 將檔案以同樣的樹狀結構鏡像匯出 (不污染原資料夾)
- 覆蓋/跳過已存在檔案 (--overwrite)
- 保留 EXIF 資訊 (--keep-exif)
- 自動跳過壓縮後變大的檔案
- 支援深度控制 (--max-depth) 以及 尺寸過濾 (--min-size, --max-size)
- 跳過無效壓縮格式 (BMP)
- 支援讀取 Apple 高效無損圖檔 (.HEIC / .AVIF)
"""

import re
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

# 支援的圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic', '.avif'}

# 用於偵測已壓縮檔案的 regex pattern (e.g. _70%, _50%)
COMPRESSED_SUFFIX_PATTERN = re.compile(r'_\d+%$')


def get_exif(image: Image.Image) -> bytes | None:
    """取得圖片的 EXIF 資料"""
    try:
        return image.info.get('exif')
    except Exception:
        return None


def compress_image(
    filepath: Path, root_dir: Path, out_dir: Path | None, 
    quality: int, overwrite: bool, keep_exif: bool, dry_run: bool
) -> FileResult:
    """壓縮單張圖片並另存新檔"""
    try:
        suffix = f"_{quality}%"
        
        # BMP 直接跳過
        if filepath.suffix.lower() == '.bmp':
            return FileResult('skipped', f"跳過 BMP (不支援壓縮): {filepath.name}")

        # 1. 決定輸出目標的「相對存儲目錄」與「檔名」
        if out_dir:
            try:
                rel_path = filepath.relative_to(root_dir)
            except ValueError:
                rel_path = Path(filepath.name)
            
            # 因為已經在別的資料夾，不需要後綴 _70%
            target_path = out_dir / rel_path
        else:
            # 原地壓縮模式
            if COMPRESSED_SUFFIX_PATTERN.search(filepath.stem):
                return FileResult('skipped', f"跳過已壓縮: {filepath.name}")
            target_path = filepath.parent / f"{filepath.stem}{suffix}{filepath.suffix}"

        # 2. 如果來源是 HEIC 或 AVIF，強制把輸出副檔名改為常規能讀取的格式 (.jpg)
        if filepath.suffix.lower() in {'.heic', '.avif'}:
            target_path = target_path.with_suffix('.jpg')

        # 確保資料夾存在
        if dry_run is False:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists() and not overwrite:
            return FileResult('skipped', f"檔案已存在(跳過): {target_path.name}")

        original_size = filepath.stat().st_size

        if dry_run:
            return FileResult(
                'dry_run',
                f"[預覽] 將建立: {target_path} ({original_size / 1024:.1f}KB)",
            )

        # 3. 開啟圖片並抽取 EXIF
        img = Image.open(filepath)
        exif_data = get_exif(img) if keep_exif else None
        save_kwargs = {'optimize': True}

        # 判定將被儲存為哪一種格式 (支援 HEIC 轉換成 JPEG)
        ext = target_path.suffix.lower()
        if ext in {'.jpg', '.jpeg', '.webp'}:
            save_kwargs['quality'] = quality
            if exif_data:
                save_kwargs['exif'] = exif_data
            if img.mode in ('RGBA', 'P', 'CMYK'):
                img = img.convert('RGB')
        elif ext == '.png':
            pass

        format_map = {
            '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'
        }
        output_format = format_map.get(ext, 'JPEG')

        # 4. 存成暫存檔檢查大小
        temp_path = target_path.with_suffix('.tmp')
        img.save(temp_path, format=output_format, **save_kwargs)
        new_size = temp_path.stat().st_size

        # 5. 放棄沒有變小的檔案 (除非原本是 HEIC, 那就不管大小照樣過去 因為目的有時是轉檔)
        orig_ext = filepath.suffix.lower()
        if new_size >= original_size and orig_ext not in {'.heic', '.avif'}:
            temp_path.unlink()
            return FileResult(
                'size_skip',
                f"檔案 {filepath.name} 越壓越大，捨棄變更",
            )

        # 改名成正式檔
        if target_path.exists():
            target_path.unlink()
        temp_path.rename(target_path)

        return FileResult(
            'success',
            "已隱藏",
            original_size, new_size,
        )

    except Exception as e:
        return FileResult('failed', f"檔案 {filepath.name} 解析失敗: {e}")


def main():
    setup_logger()
    
    parser = create_base_parser(
        description='圖片批量壓縮工具 (支援 HEIC 讀取與尺寸過濾)',
        epilog='''
範例:
  python compress_images.py "D:\\Photos" -O "E:\\Photos_Zip" -q 50
  
  # 過濾：只挑選大於 1MB 且小於 50MB 的圖庫進行原地壓圖
  python compress_images.py "D:\\Photos" --min-size 1MB --max-size 50MB
        '''
    )
    parser.add_argument('-q', '--quality', type=int, default=70,
                        help='壓縮品質 1-100 (預設: 70)')
    parser.add_argument('-o', '--overwrite', action='store_true',
                        help='覆蓋已存在的壓縮檔')
    parser.add_argument('-e', '--keep-exif', action='store_true',
                        help='保留 EXIF 資訊 (GPS、拍攝時間等)')

    args = parser.parse_args()

    min_size = parse_size_to_bytes(args.min_size)
    max_size = parse_size_to_bytes(args.max_size)

    directory = resolve_directory(args)
    if not directory or not validate_quality(args.quality):
        return

    root_path = Path(directory)
    if not root_path.exists():
        console.print(f"[bold red]❌ 目錄不存在: {directory}[/bold red]")
        return
        
    out_dir_path = Path(args.out_dir) if args.out_dir else None

    from rich.panel import Panel
    
    welcome_str = (
        f"📂 [bold cyan]目標歸檔來源[/bold cyan]: {directory}\n"
        f"📁 [bold magenta]最後存放位置[/bold magenta]: {args.out_dir if args.out_dir else '[原地放置並加後綴字]'}\n"
        f"⚙️  [bold yellow]壓縮品質[/bold yellow]: {args.quality}%\n"
        f"⚖️  [bold yellow]檔案過濾範圍[/bold yellow]: {'不限' if not min_size else format_size(min_size)} ~ {'不限' if not max_size else format_size(max_size)}\n"
        f"🚀 [bold green]並發數量[/bold green]: {args.workers}"
    )
    console.print(Panel.fit(welcome_str, title="[bold]圖片壓縮工具 v6.0[/bold]"))

    files = collect_files(
        root_path, SUPPORTED_FORMATS, max_depth=args.max_depth,
        min_size_bytes=min_size, max_size_bytes=max_size
    )

    worker = partial(
        compress_image,
        root_dir=root_path,
        out_dir=out_dir_path,
        quality=args.quality,
        overwrite=args.overwrite,
        keep_exif=args.keep_exif,
        dry_run=args.dry_run,
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="壓縮與格式標準化")
    print_summary(summary, success_label="精簡與輸出成功", skip_label="條件不符跳過")

if __name__ == "__main__":
    main()

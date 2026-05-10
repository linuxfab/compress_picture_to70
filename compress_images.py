"""
圖片壓縮工具
遍歷指定目錄及子目錄，將圖片壓縮後另存新檔
"""

from pathlib import Path
from functools import partial

from utils import (
    FileResult, collect_files, run_pipeline, print_summary,
    create_base_parser, resolve_directory, validate_quality, validate_scale,
    parse_size_to_bytes, format_size, build_filter_info, setup_logger, console,
    SUPPORTED_FORMATS, COMPRESSED_SUFFIX_PATTERN, FORMAT_MAP, process_image_core,
    __version__
)
from rich.panel import Panel

def compress_image(
    filepath: Path, root_dir: Path, out_dir: Path | None, 
    quality: int, overwrite: bool, keep_exif: bool, dry_run: bool,
    skip_if_newer: bool = False, scale: float = 1.0, in_place: bool = False,
    min_size_bytes: int | None = None, max_size_bytes: int | None = None
) -> FileResult:
    """壓縮單張圖片並另存新檔"""
    try:
        # 單次取得檔案狀態，減少 I/O
        try:
            f_stat = filepath.stat()
        except Exception as e:
            return FileResult('failed', f"讀取檔案狀態失敗 {filepath.name}: {e}")

        suffix = f"_{quality}%"
        
        # BMP 直接跳過 (雖然 PIL 支援，但通常壓縮效果差)
        if filepath.suffix.lower() == '.bmp':
            return FileResult('skipped', f"跳過 BMP: {filepath.name}")

        # 0. 大小過濾
        file_size = f_stat.st_size
        if min_size_bytes is not None and file_size < min_size_bytes:
            return FileResult('skipped', f"跳過 (太小): {filepath.name} ({format_size(file_size)})")
        if max_size_bytes is not None and file_size > max_size_bytes:
            return FileResult('skipped', f"跳過 (太大): {filepath.name} ({format_size(file_size)})")

        # 1. 決定輸出目標的「相對存儲目錄」與「檔名」
        if in_place:
            target_path = filepath
        elif out_dir:
            try:
                rel_path = filepath.relative_to(root_dir)
            except ValueError:
                rel_path = Path(filepath.name)
            target_path = out_dir / rel_path
        else:
            if COMPRESSED_SUFFIX_PATTERN.search(filepath.stem):
                return FileResult('skipped', f"跳過已壓縮: {filepath.name}")
            target_path = filepath.parent / f"{filepath.stem}{suffix}{filepath.suffix}"

        # HEIC / AVIF 強制轉 JPEG 確保相容性
        if filepath.suffix.lower() in {'.heic', '.avif'}:
            target_path = target_path.with_suffix('.jpg')

        # 檢查檔案是否已存在或較新
        if target_path.exists():
            if skip_if_newer and target_path.stat().st_mtime >= f_stat.st_mtime:
                return FileResult('skipped', f"目標檔案較新: {target_path.name}")
            elif not overwrite and not in_place:
                return FileResult('skipped', f"檔案已存在: {target_path.name}")

        if dry_run:
            return FileResult('dry_run', f"[預覽] 將壓縮: {target_path.name} ({format_size(file_size)})")

        # 呼叫核心處理 — 使用集中管理的 FORMAT_MAP
        output_format = FORMAT_MAP.get(target_path.suffix.lower(), 'JPEG')
        
        result = process_image_core(
            filepath=filepath,
            target_path=target_path,
            quality=quality,
            keep_exif=keep_exif,
            scale=scale,
            output_format=output_format,
            force_convert_from={'.heic', '.avif'},
            file_stat=f_stat
        )

        # in_place 且格式轉換時 (e.g. .heic → .jpg)，刪除原始檔案避免孤兒檔
        if result.status == 'success' and in_place and target_path != filepath:
            if target_path.exists() and target_path.stat().st_size > 0:
                try:
                    filepath.unlink()
                except Exception:
                    pass  # 刪不掉也不影響壓縮結果

        return result

    except Exception as e:
        return FileResult('failed', f"檔案 {filepath.name} 解析失敗: {e}")


def main():
    parser = create_base_parser(
        description='圖片批量壓縮工具 (支援 HEIC 讀取與尺寸過濾)',
        epilog='範例: python compress_images.py "D:\\Photos" -O "E:\\Photos_Zip" -q 50'
    )
    parser.add_argument('-q', '--quality', type=int, default=70, help='壓縮品質 1-100 (預設: 70)')
    parser.add_argument('-o', '--overwrite', action='store_true', help='覆蓋已存在的壓縮檔')
    parser.add_argument('-e', '--keep-exif', action='store_true', help='保留 EXIF 資訊')

    args = parser.parse_args()
    setup_logger(verbose=args.verbose)
    
    if not validate_scale(args.scale):
        return
        
    directory = resolve_directory(args)
    if not directory or not validate_quality(args.quality):
        return

    try:
        min_size = parse_size_to_bytes(args.min_size)
        max_size = parse_size_to_bytes(args.max_size)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        return
    root_path = Path(directory)
    out_dir_path = Path(args.out_dir) if args.out_dir else None

    filter_str = build_filter_info(min_size, max_size, args.scale)

    welcome_str = (
        f"[來源] [bold cyan]目標來源[/bold cyan]: {directory}\n"
        f"[輸出] [bold magenta]輸出位置[/bold magenta]: {args.out_dir if args.out_dir else ('[原地覆蓋]' if args.in_place else '[原地後綴]')}\n"
        f"[設定] [bold yellow]品質[/bold yellow]: {args.quality}% | [bold green]並發[/bold green]: {args.workers}{filter_str}"
    )
    console.print(Panel.fit(welcome_str, title=f"[bold]圖片壓縮工具 v{__version__}[/bold]"))

    files = collect_files(
        root_path, SUPPORTED_FORMATS, max_depth=args.max_depth
    )

    worker = partial(
        compress_image, root_dir=root_path, out_dir=out_dir_path,
        quality=args.quality, overwrite=args.overwrite, keep_exif=args.keep_exif,
        dry_run=args.dry_run, skip_if_newer=args.skip_if_newer, scale=args.scale, in_place=args.in_place,
        min_size_bytes=min_size, max_size_bytes=max_size
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="壓縮與格式化")
    print_summary(summary, success_label="精簡與輸出成功")

if __name__ == "__main__":
    main()

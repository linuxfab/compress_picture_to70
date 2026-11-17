"""
圖片壓縮工具
遍歷指定目錄及子目錄，將圖片壓縮或轉換為指定格式後另存新檔
"""

from functools import partial
from pathlib import Path

from rich.panel import Panel

from cli import (
    __version__,
    assign_conflict_tags,
    collect_files,
    create_base_parser,
    make_output_dir_excluder,
    parse_size_to_bytes,
    resolve_directory,
    validate_quality,
    validate_max_dim,
    validate_scale,
)
from image_core import (
    COMPRESSED_SUFFIX_PATTERN,
    EXT_BY_FORMAT,
    FORMAT_MAP,
    SUPPORTED_FORMATS,
    process_image_core,
)
from ui import (
    FileResult,
    build_filter_info,
    console,
    format_size,
    print_conflict_notice,
    print_summary,
    run_pipeline,
    setup_logger,
)

# 這些格式相容性較差，auto 模式下壓縮時強制轉為 JPEG 輸出
FORCE_JPEG_EXTS = {'.heic', '.avif'}
SUPPORTED_OUTPUT_FORMATS = ('auto', 'jpeg', 'png', 'webp', 'avif')


def build_suffix(quality: int, target_size_bytes: int | None) -> str:
    """產生「原地後綴」模式的檔名後綴：有目標大小時顯示大小 (_500.0KB)，否則顯示品質 (_70%)"""
    if target_size_bytes is not None:
        return f"_{format_size(target_size_bytes).replace(' ', '')}"
    return f"_{quality}%"


def build_target_path(
    filepath: Path, root_dir: Path, out_dir: Path | None,
    in_place: bool, suffix: str, tag: str = '',
    target_format: str = 'auto',
) -> Path:
    """
    計算單一來源檔案的輸出路徑 (主程序的衝突偵測與 worker 共用同一套規則，確保結果一致)。
    - tag 非空時插入檔名主體之後，用來區分同名不同副檔名的來源 (例如 IMG_heic.jpg)。
    - target_format 為 'auto' 時，HEIC / AVIF 一律改為 .jpg；其餘維持原副檔名。
    - target_format 指定明確格式 (如 'avif', 'webp') 時，使用對應副檔名。
    """
    stem = f"{filepath.stem}_{tag}" if tag else filepath.stem
    fmt = target_format.lower()
    if fmt != 'auto':
        ext = EXT_BY_FORMAT[fmt.upper()]
    elif filepath.suffix.lower() in FORCE_JPEG_EXTS:
        ext = '.jpg'
    else:
        ext = filepath.suffix

    if in_place:
        return filepath.parent / f"{stem}{ext}"
    if out_dir:
        try:
            rel_parent = filepath.relative_to(root_dir).parent
        except ValueError:
            rel_parent = Path()
        return out_dir / rel_parent / f"{stem}{ext}"
    return filepath.parent / f"{stem}{suffix}{ext}"


def compress_image(
    filepath: Path, root_dir: Path, out_dir: Path | None,
    quality: int, overwrite: bool, keep_exif: bool, dry_run: bool,
    skip_if_newer: bool = False, scale: float = 1.0, in_place: bool = False,
    min_size_bytes: int | None = None, max_size_bytes: int | None = None,
    target_size_bytes: int | None = None,
    conflict_tags: dict[str, str] | None = None,
    target_format: str = 'auto',
    png_quantize: bool = False,
    max_dim: int | None = None,
    strip_gps: bool = False,
) -> FileResult:
    """壓縮單張圖片並另存新檔"""
    try:
        try:
            f_stat = filepath.stat()
        except Exception as e:
            return FileResult('failed', f"讀取檔案狀態失敗 {filepath.name}: {e}")

        suffix = build_suffix(quality, target_size_bytes)

        # auto 模式下跳過 BMP；若有指定 --format 轉檔 (如 avif/webp/jpeg) 則允許轉換 BMP
        if target_format.lower() == 'auto' and filepath.suffix.lower() == '.bmp':
            return FileResult('skipped', f"跳過 BMP: {filepath.name}")

        # 0. 大小過濾
        file_size = f_stat.st_size
        if min_size_bytes is not None and file_size < min_size_bytes:
            return FileResult('skipped', f"跳過 (太小): {filepath.name} ({format_size(file_size)})")
        if max_size_bytes is not None and file_size > max_size_bytes:
            return FileResult('skipped', f"跳過 (太大): {filepath.name} ({format_size(file_size)})")

        # 原地後綴模式下，已帶有壓縮後綴的檔案不再重複處理
        if not in_place and not out_dir and COMPRESSED_SUFFIX_PATTERN.search(filepath.stem):
            return FileResult('skipped', f"跳過已壓縮: {filepath.name}")

        # 1. 決定輸出路徑
        tag = (conflict_tags or {}).get(str(filepath), '')
        target_path = build_target_path(
            filepath, root_dir, out_dir, in_place, suffix, tag, target_format=target_format
        )

        # 2. 檢查檔案是否已存在或較新
        if target_path.exists():
            is_self = in_place and target_path == filepath
            if skip_if_newer and target_path.stat().st_mtime >= f_stat.st_mtime:
                return FileResult('skipped', f"目標檔案較新: {target_path.name}")
            elif not overwrite and not is_self:
                return FileResult(
                    'skipped', f"檔案已存在: {target_path.name}",
                    warn=in_place,
                )

        if dry_run:
            return FileResult(
                'dry_run',
                f"[預覽] 將壓縮: {filepath.name} → {target_path.name} ({format_size(file_size)})",
                original_size=file_size,
                target_path=str(target_path),
            )

        if target_format.lower() != 'auto':
            output_format = target_format.upper()
            force_from = {filepath.suffix.lower()} if target_path.suffix.lower() != filepath.suffix.lower() else None
        else:
            output_format = FORMAT_MAP.get(target_path.suffix.lower(), 'JPEG')
            force_from = FORCE_JPEG_EXTS

        result = process_image_core(
            filepath=filepath,
            target_path=target_path,
            quality=quality,
            keep_exif=keep_exif,
            scale=scale,
            output_format=output_format,
            force_convert_from=force_from,
            file_stat=f_stat,
            target_size_bytes=target_size_bytes,
            png_quantize=png_quantize,
            max_dim=max_dim,
            strip_gps=strip_gps,
        )

        # in_place 且格式轉換時 (e.g. .heic → .jpg 或 --format avif)，刪除原始檔案避免孤兒檔
        if result.status == 'success' and in_place and target_path != filepath:
            if target_path.exists() and target_path.stat().st_size > 0:
                try:
                    filepath.unlink()
                except Exception:
                    pass

        return result

    except Exception as e:
        return FileResult('failed', f"檔案 {filepath.name} 解析失敗: {e}")


def main(argv: list[str] | None = None) -> None:
    parser = create_base_parser(
        description='圖片批量壓縮工具 (支援 HEIC/AVIF 與尺寸過濾)',
        epilog='範例: python compress_images.py "D:\\Photos" -O "E:\\Photos_Zip" -q 50 -f avif'
    )
    parser.add_argument('-q', '--quality', type=int, default=70, help='壓縮品質 1-100 (預設: 70)')
    parser.add_argument('-o', '--overwrite', action='store_true', help='覆蓋已存在的壓縮檔')
    parser.add_argument('-e', '--keep-exif', action='store_true', help='保留 EXIF 資訊')
    parser.add_argument(
        '-f', '--format',
        type=str.lower,
        choices=SUPPORTED_OUTPUT_FORMATS,
        default='auto',
        help='輸出圖片格式 (預設: auto，維持原格式並將 HEIC/AVIF 轉為 JPEG)',
    )
    parser.add_argument(
        '--png-quantize',
        action='store_true',
        help='將輸出 PNG 減色為 256 色調色盤 (保留透明通道，大幅縮減 PNG 體積並支援 --target-size)',
    )

    args = parser.parse_args(argv)
    setup_logger(verbose=args.verbose)

    if not validate_scale(args.scale) or not validate_max_dim(args.max_dim):
        return
    # --strip-gps 的意義是「保留 EXIF 但去掉位置」，因此自動啟用 --keep-exif
    keep_exif = args.keep_exif or args.strip_gps

    directory = resolve_directory(args)
    if not directory or not validate_quality(args.quality):
        return

    try:
        min_size = parse_size_to_bytes(args.min_size)
        max_size = parse_size_to_bytes(args.max_size)
        target_size = parse_size_to_bytes(args.target_size)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        return

    root_path = Path(directory)
    out_dir_path = Path(args.out_dir) if args.out_dir and not args.in_place else None

    filter_str = build_filter_info(
        min_size, max_size, args.scale, target_size,
        max_dim=args.max_dim, strip_gps=args.strip_gps,
    )
    format_str = f" | [bold cyan]格式[/bold cyan]: {args.format.upper()}" if args.format != 'auto' else ""
    quant_str = " | [bold green]PNG 減色[/bold green]: 開啟" if args.png_quantize else ""

    welcome_str = (
        f"[來源] [bold cyan]目標來源[/bold cyan]: {directory}\n"
        f"[輸出] [bold magenta]輸出位置[/bold magenta]: {out_dir_path if out_dir_path else ('[原地覆蓋]' if args.in_place else '[原地後綴]')}\n"
        f"[設定] [bold yellow]品質[/bold yellow]: {args.quality}%{format_str}{quant_str}"
        f"{f' | [bold magenta]目標大小[/bold magenta]: {args.target_size}' if args.target_size else ''} | [bold green]並發[/bold green]: {args.workers}{filter_str}"
    )
    console.print(Panel.fit(welcome_str, title=f"[bold]圖片壓縮工具 v{__version__}[/bold]"))

    files = collect_files(
        root_path, SUPPORTED_FORMATS, max_depth=args.max_depth,
        exclude_fn=make_output_dir_excluder(root_path, out_dir_path),
    )

    suffix = build_suffix(args.quality, target_size)

    def target_fn(f: Path, tag: str) -> Path:
        return build_target_path(
            f, root_path, out_dir_path, args.in_place, suffix, tag, target_format=args.format
        )

    conflict_tags = assign_conflict_tags(files, target_fn)
    print_conflict_notice(conflict_tags, target_fn)

    worker = partial(
        compress_image, root_dir=root_path, out_dir=out_dir_path,
        quality=args.quality, overwrite=args.overwrite, keep_exif=keep_exif,
        dry_run=args.dry_run, skip_if_newer=args.skip_if_newer, scale=args.scale, in_place=args.in_place,
        min_size_bytes=min_size, max_size_bytes=max_size, target_size_bytes=target_size,
        conflict_tags=conflict_tags, target_format=args.format,
        max_dim=args.max_dim, strip_gps=args.strip_gps,
        png_quantize=args.png_quantize,
    )

    report_path = Path(args.report) if args.report else None
    summary = run_pipeline(
        files, worker, args.workers, args.dry_run,
        label="壓縮與格式化", verbose=args.verbose, report_path=report_path,
    )
    print_summary(summary, success_label="精簡與輸出成功")


if __name__ == "__main__":
    main()

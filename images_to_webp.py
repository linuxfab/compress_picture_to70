"""
圖片轉 WebP / AVIF 工具
遍歷指定目錄及子目錄，將圖片轉換為 WebP 或 AVIF 格式
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
    validate_scale,
)
from image_core import EXT_BY_FORMAT, SUPPORTED_FORMATS, process_image_core
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

SUPPORTED_TARGET_FORMATS = ('webp', 'avif')


def build_webp_target(
    filepath: Path, root_dir: Path, target_root: Path, tag: str = '',
    target_format: str = 'webp',
) -> Path:
    """
    計算單一來源檔案的 WebP / AVIF 輸出路徑 (主程序的衝突偵測與 worker 共用同一套規則)。
    tag 非空時用來區分同名不同副檔名的來源，例如 a.png → a_png.webp。
    """
    try:
        rel_parent = filepath.relative_to(root_dir).parent
    except ValueError:
        rel_parent = Path()
    stem = f"{filepath.stem}_{tag}" if tag else filepath.stem
    ext = EXT_BY_FORMAT.get(target_format.upper(), '.webp')
    return target_root / rel_parent / f"{stem}{ext}"


def convert_to_webp(
    filepath: Path, root_dir: Path, target_root: Path, quality: int,
    overwrite: bool, dry_run: bool, lossless: bool, keep_exif: bool,
    skip_if_newer: bool = False, scale: float = 1.0, in_place: bool = False,
    min_size_bytes: int | None = None, max_size_bytes: int | None = None,
    skip_if_larger: bool = False, target_size_bytes: int | None = None,
    conflict_tags: dict[str, str] | None = None,
    target_format: str = 'webp',
) -> FileResult:
    """將單張圖片轉換為 WebP / AVIF 並另存新檔"""
    try:
        try:
            f_stat = filepath.stat()
        except Exception as e:
            return FileResult('failed', f"讀取檔案狀態失敗 {filepath.name}: {e}")

        file_size = f_stat.st_size
        if min_size_bytes is not None and file_size < min_size_bytes:
            return FileResult('skipped', f"跳過 (太小): {filepath.name} ({format_size(file_size)})")
        if max_size_bytes is not None and file_size > max_size_bytes:
            return FileResult('skipped', f"跳過 (太大): {filepath.name} ({format_size(file_size)})")

        fmt_upper = target_format.upper()
        tag = (conflict_tags or {}).get(str(filepath), '')
        target_path = build_webp_target(filepath, root_dir, target_root, tag, target_format=target_format)

        if target_path.exists():
            is_self = in_place and target_path == filepath
            if skip_if_newer and target_path.stat().st_mtime >= f_stat.st_mtime:
                return FileResult('skipped', f"目標較新: {target_path.name}")
            elif not overwrite and not is_self:
                return FileResult(
                    'skipped', f"檔案已存在: {target_path.name}",
                    warn=in_place,
                )

        if dry_run:
            return FileResult('dry_run', f"[預覽] 轉 {fmt_upper}: {filepath.name} → {target_path.name} ({format_size(file_size)})")

        result = process_image_core(
            filepath=filepath,
            target_path=target_path,
            quality=quality,
            keep_exif=keep_exif,
            scale=scale,
            output_format=fmt_upper,
            lossless=lossless,
            skip_if_larger=skip_if_larger,
            file_stat=f_stat,
            target_size_bytes=target_size_bytes
        )

        if result.status == 'success' and in_place and not dry_run:
            if target_path != filepath:
                if target_path.exists() and target_path.stat().st_size > 0:
                    filepath.unlink()
                else:
                    return FileResult('failed', f"轉換後檔案異常，保留原檔: {filepath.name}")

        return result

    except Exception as e:
        return FileResult('failed', f"檔案 {filepath.name} 處理失敗: {e}")


def main(argv: list[str] | None = None) -> None:
    parser = create_base_parser(
        description='圖片轉 WebP / AVIF 工具 (支援 HEIC 與尺寸過濾)',
        epilog='範例: python images_to_webp.py "D:\\Photos" --lossless -f avif'
    )
    parser.add_argument('-q', '--quality', type=int, default=80, help='輸出品質 (1-100, 預設: 80)')
    parser.add_argument('-o', '--overwrite', action='store_true', help='覆蓋已存在檔案')
    parser.add_argument('-l', '--lossless', action='store_true', help='無損壓縮')
    parser.add_argument('-e', '--keep-exif', action='store_true', help='保留 EXIF')
    parser.add_argument('--skip-if-larger', action='store_true', help='若輸出大於原圖則捨棄變更')
    parser.add_argument(
        '-f', '--format',
        type=str.lower,
        choices=SUPPORTED_TARGET_FORMATS,
        default='webp',
        help='目標轉換格式 (預設: webp，可選 avif)',
    )

    args = parser.parse_args(argv)
    setup_logger(verbose=args.verbose)

    if not validate_scale(args.scale):
        return

    directory = resolve_directory(args)
    if not directory or not (args.lossless or validate_quality(args.quality)):
        return

    if args.lossless and args.target_size:
        console.print("[bold yellow]警告：--lossless (無損模式) 與 --target-size 不能同時使用，目標大小限制將被忽略。[/bold yellow]")

    try:
        min_size = parse_size_to_bytes(args.min_size)
        max_size = parse_size_to_bytes(args.max_size)
        target_size = parse_size_to_bytes(args.target_size)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        return

    root_path = Path(directory)
    fmt_upper = args.format.upper()
    target_ext = EXT_BY_FORMAT[fmt_upper]

    if args.in_place:
        out_dir_path = root_path
    else:
        default_dir = "webp_output" if args.format == 'webp' else f"{args.format}_output"
        out_dir_path = Path(args.out_dir) if args.out_dir else root_path / default_dir

    filter_str = build_filter_info(min_size, max_size, args.scale, target_size)

    target_size_desc = f" | [bold magenta]目標大小[/bold magenta]: {args.target_size}" if args.target_size else ""
    welcome_str = (
        f"[來源] [bold cyan]來源掃描[/bold cyan]: {directory}\n"
        f"[輸出] [bold magenta]輸出位置[/bold magenta]: {out_dir_path if not args.in_place else '[原地轉換並刪除原檔]'}\n"
        f"[設定] [bold cyan]目標格式[/bold cyan]: {fmt_upper} | [bold yellow]模式[/bold yellow]: {'無損' if args.lossless else f'有損 ({args.quality}%)'}{target_size_desc} | [bold green]並發[/bold green]: {args.workers}{filter_str}"
    )
    console.print(Panel.fit(welcome_str, title=f"[bold]圖片轉 {fmt_upper} 工具 v{__version__}[/bold]"))

    # 不需要掃描已經是目標格式的檔案，避免重複處理與潛在的覆寫
    input_formats = {fmt for fmt in SUPPORTED_FORMATS if fmt != target_ext}

    files = collect_files(
        root_path, input_formats,
        max_depth=args.max_depth,
        exclude_fn=make_output_dir_excluder(root_path, out_dir_path),
    )

    def target_fn(f: Path, tag: str) -> Path:
        return build_webp_target(f, root_path, out_dir_path, tag, target_format=args.format)

    conflict_tags = assign_conflict_tags(files, target_fn)
    print_conflict_notice(conflict_tags, target_fn)

    worker = partial(
        convert_to_webp, root_dir=root_path, target_root=out_dir_path,
        quality=args.quality, overwrite=args.overwrite, dry_run=args.dry_run,
        lossless=args.lossless, keep_exif=args.keep_exif, skip_if_newer=args.skip_if_newer,
        scale=args.scale, in_place=args.in_place,
        min_size_bytes=min_size, max_size_bytes=max_size,
        skip_if_larger=args.skip_if_larger, target_size_bytes=target_size,
        conflict_tags=conflict_tags, target_format=args.format,
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="跨格式轉換")
    print_summary(summary, success_label=f"{fmt_upper} 轉換成功", after_label=f"{fmt_upper} 後")


if __name__ == "__main__":
    main()

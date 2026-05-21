"""
圖片轉 WebP 工具
遍歷指定目錄及子目錄，將圖片轉換為 WebP 格式
"""

from pathlib import Path
from functools import partial

from utils import (
    FileResult, collect_files, run_pipeline, print_summary,
    create_base_parser, resolve_directory, validate_quality, validate_scale,
    parse_size_to_bytes, format_size, build_filter_info, setup_logger, console,
    SUPPORTED_FORMATS, process_image_core, __version__
)
from rich.panel import Panel

def convert_to_webp(
    filepath: Path, root_dir: Path, target_root: Path, quality: int, 
    overwrite: bool, dry_run: bool, lossless: bool, keep_exif: bool,
    skip_if_newer: bool = False, scale: float = 1.0, in_place: bool = False,
    min_size_bytes: int | None = None, max_size_bytes: int | None = None,
    skip_if_larger: bool = False
) -> FileResult:
    """將單張圖片轉換為 WebP 並另存新檔"""
    try:
        # 單次取得檔案狀態，減少 I/O
        try:
            f_stat = filepath.stat()
        except Exception as e:
            return FileResult('failed', f"讀取檔案狀態失敗 {filepath.name}: {e}")

        # 0. 大小過濾
        file_size = f_stat.st_size
        if min_size_bytes is not None and file_size < min_size_bytes:
            return FileResult('skipped', f"跳過 (太小): {filepath.name} ({format_size(file_size)})")
        if max_size_bytes is not None and file_size > max_size_bytes:
            return FileResult('skipped', f"跳過 (太大): {filepath.name} ({format_size(file_size)})")
        try:
            rel_path = filepath.relative_to(root_dir)
        except ValueError:
            rel_path = Path(filepath.name)

        target_path = target_root / rel_path.with_suffix('.webp')

        if target_path.exists():
            if skip_if_newer and target_path.stat().st_mtime >= f_stat.st_mtime:
                return FileResult('skipped', f"目標較新: {target_path.name}")
            elif not overwrite and not in_place:
                return FileResult('skipped', f"檔案已存在: {target_path.name}")

        if dry_run:
            return FileResult('dry_run', f"[預覽] 轉 WebP: {target_path.name} ({format_size(file_size)})")

        result = process_image_core(
            filepath=filepath,
            target_path=target_path,
            quality=quality,
            keep_exif=keep_exif,
            scale=scale,
            output_format='WEBP',
            lossless=lossless,
            skip_if_larger=skip_if_larger,
            file_stat=f_stat
        )

        if result.status == 'success' and in_place and not dry_run:
            # 確保 target_path 和 filepath 不同，避免自我刪除
            if target_path != filepath:
                if target_path.exists() and target_path.stat().st_size > 0:
                    filepath.unlink()
                else:
                    return FileResult('failed', f"轉換後檔案異常，保留原檔: {filepath.name}")

        return result

    except Exception as e:
        return FileResult('failed', f"檔案 {filepath.name} 處理失敗: {e}")


def main():
    parser = create_base_parser(
        description='圖片轉 WebP 工具 (支援 HEIC 與尺寸過濾)',
        epilog='範例: python images_to_webp.py "D:\\Photos" --lossless'
    )
    parser.add_argument('-q', '--quality', type=int, default=80, help='WebP 品質 (1-100, 預設: 80)')
    parser.add_argument('-o', '--overwrite', action='store_true', help='覆蓋已存在檔案')
    parser.add_argument('-l', '--lossless', action='store_true', help='無損壓縮')
    parser.add_argument('-e', '--keep-exif', action='store_true', help='保留 EXIF')
    parser.add_argument('--skip-if-larger', action='store_true', help='若 WebP 大於原圖則捨棄變更')

    args = parser.parse_args()
    setup_logger(verbose=args.verbose)
    
    if not validate_scale(args.scale):
        return
        
    directory = resolve_directory(args)
    if not directory or not (args.lossless or validate_quality(args.quality)):
        return

    try:
        min_size = parse_size_to_bytes(args.min_size)
        max_size = parse_size_to_bytes(args.max_size)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        return
    root_path = Path(directory)
    
    # 若為原地轉換，則輸出目錄為原目錄；否則預設輸出到 webp_output 目錄
    if args.in_place:
        out_dir_path = root_path
    else:
        out_dir_path = Path(args.out_dir) if args.out_dir else root_path / "webp_output"

    filter_str = build_filter_info(min_size, max_size, args.scale)

    welcome_str = (
        f"[來源] [bold cyan]來源掃描[/bold cyan]: {directory}\n"
        f"[輸出] [bold magenta]輸出位置[/bold magenta]: {out_dir_path if not args.in_place else '[原地轉換並刪除原檔]'}\n"
        f"[設定] [bold yellow]模式[/bold yellow]: {'無損' if args.lossless else f'有損 ({args.quality}%)'} | [bold green]並發[/bold green]: {args.workers}{filter_str}"
    )
    console.print(Panel.fit(welcome_str, title=f"[bold]圖片轉 WebP 工具 v{__version__}[/bold]"))

    # 排除 webp_output 本身避免遞迴掃描
    def should_exclude(dir_path: Path) -> bool:
        try:
            return dir_path.resolve() == out_dir_path.resolve() or dir_path.resolve().is_relative_to(out_dir_path.resolve())
        except Exception:
            return False

    exclude_targets = set()
    if not args.in_place:
        try:
            # 如果輸出目錄是來源目錄的直接子目錄，將其名字加入 exclude_dirs 以優化掃描效能
            if out_dir_path.parent.resolve() == root_path.resolve():
                exclude_targets.add(out_dir_path.name)
        except Exception:
            pass

    # 轉 WebP 工具不需要掃描已經是 WebP 的檔案，避免重複處理與潛在的覆寫
    input_formats = {fmt for fmt in SUPPORTED_FORMATS if fmt != '.webp'}
    
    files = collect_files(
        root_path, input_formats, exclude_dirs=exclude_targets, 
        max_depth=args.max_depth,
        exclude_fn=should_exclude if not args.in_place else None
    )

    worker = partial(
        convert_to_webp, root_dir=root_path, target_root=out_dir_path,
        quality=args.quality, overwrite=args.overwrite, dry_run=args.dry_run,
        lossless=args.lossless, keep_exif=args.keep_exif, skip_if_newer=args.skip_if_newer,
        scale=args.scale, in_place=args.in_place,
        min_size_bytes=min_size, max_size_bytes=max_size,
        skip_if_larger=args.skip_if_larger
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="跨格式轉換")
    print_summary(summary, success_label="WebP 轉換成功", after_label="WebP 後")

if __name__ == "__main__":
    main()

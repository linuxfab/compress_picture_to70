"""
圖片壓縮工具 v5.0
遍歷指定目錄及子目錄，將圖片壓縮後另存新檔

功能:
- 自訂壓縮比例 (--quality)
- 並行處理加速 (多執行緒)
- 支援 `--out-dir` 將檔案以同樣的樹狀結構鏡像匯出 (不污染原資料夾)
- 覆蓋/跳過已存在檔案 (--overwrite)
- 保留 EXIF 資訊 (--keep-exif)
- 自動跳過壓縮後變大的檔案
- Dry-run 模式預覽
- 總空間節省統計
- 支援深度控制 (--max-depth)
- 跳過無效壓縮格式 (BMP)
- Rich UI 全面升級！
"""

import re
from pathlib import Path
from functools import partial
from PIL import Image

from utils import (
    FileResult, collect_files, run_pipeline, print_summary,
    create_base_parser, resolve_directory, validate_quality,
    setup_logger, console
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
    filepath: Path, root_dir: Path, out_dir: Path | None, 
    quality: int, overwrite: bool, keep_exif: bool, dry_run: bool
) -> FileResult:
    """壓縮單張圖片並另存新檔"""
    try:
        suffix = f"_{quality}%"
        
        # BMP 直接跳過
        if filepath.suffix.lower() == '.bmp':
            return FileResult('skipped', f"跳過 BMP (不支援無損或有損壓縮): {filepath.name}")

        # 決定我們的目標存放位置
        # 如果使用者有傳入 --out-dir，我們複製他的樹狀目錄；否則存於原本的旁邊
        if out_dir:
            try:
                rel_path = filepath.relative_to(root_dir)
            except ValueError:
                rel_path = Path(filepath.name)
            
            # 目標資料夾已經獨立，所以我們不再需要醜醜的 _70% 綴詞來防呆了
            target_path = out_dir / rel_path
            new_name = target_path.name
        else:
            # 這是原本老式的原地壓縮：避免檔名衝突所以冠上品質後綴字
            if COMPRESSED_SUFFIX_PATTERN.search(filepath.stem):
                return FileResult('skipped', f"跳過已壓縮: {filepath.name}")
            new_name = f"{filepath.stem}{suffix}{filepath.suffix}"
            target_path = filepath.parent / new_name

        # 確保目標檔案的資料夾存在（為了 --out-dir 設計）
        if dry_run is False:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        # 檢查檔案是否已存在
        if target_path.exists() and not overwrite:
            return FileResult('skipped', f"檔案已存在(跳過): {new_name}")

        original_size = filepath.stat().st_size

        # Dry-run 模式
        if dry_run:
            return FileResult(
                'dry_run',
                f"[預覽] 將會建立: {target_path} ({original_size / 1024:.1f}KB)",
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
        temp_path = target_path.with_suffix('.tmp')
        img.save(temp_path, format=output_format, **save_kwargs)
        new_size = temp_path.stat().st_size

        # 壓縮後反而變大
        if new_size >= original_size:
            temp_path.unlink()
            return FileResult(
                'size_skip',
                f"壓縮後無效，原檔較小: {filepath.name} "
                f"({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB)",
            )

        # 重新命名為正式檔名
        if target_path.exists():
            target_path.unlink()
        temp_path.rename(target_path)

        return FileResult(
            'success',
            "不會再印出因為有 Progress UI 掌控",
            original_size, new_size,
        )

    except Exception as e:
        return FileResult('failed', f"處理失敗 [{filepath.name}]: {e}")


def main():
    setup_logger()
    
    parser = create_base_parser(
        description='圖片批量壓縮工具',
        epilog='''
範例:
  # 將 D:\\Photos 目錄獨立壓縮後，以同樣結構放至 E:\\Photos_Zip
  python compress_images.py "D:\\Photos" -O "E:\\Photos_Zip" -q 50
  
  # 原地覆蓋式壓縮
  python compress_images.py "D:\\Photos" --quality 80 --overwrite --keep-exif
  
  # 跑空包彈測試預覽會生出什麼
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
        console.print(f"[bold red]❌ 目錄不存在: {directory}[/bold red]")
        return
        
    out_dir_path = Path(args.out_dir) if args.out_dir else None

    # TUI 介面：畫個美觀的 Panel 
    from rich.panel import Panel
    from rich.text import Text
    
    welcome_str = (
        f"📂 [bold cyan]目標歸檔來源[/bold cyan]: {directory}\n"
        f"📁 [bold magenta]最後存放位置[/bold magenta]: {args.out_dir if args.out_dir else '[原地放置並加後綴字]'}\n"
        f"⚙️  [bold yellow]壓縮品質[/bold yellow]: {args.quality}%\n"
        f"🚀 [bold green]並發數量[/bold green]: {args.workers}"
    )
    console.print(Panel.fit(welcome_str, title="[bold]圖片壓縮工具 v5.0[/bold]"))

    files = collect_files(root_path, SUPPORTED_FORMATS, max_depth=args.max_depth)

    worker = partial(
        compress_image,
        root_dir=root_path,
        out_dir=out_dir_path,
        quality=args.quality,
        overwrite=args.overwrite,
        keep_exif=args.keep_exif,
        dry_run=args.dry_run,
    )

    summary = run_pipeline(files, worker, args.workers, args.dry_run, label="壓縮")
    print_summary(summary, success_label="壓縮精簡成功", skip_label="跳過 (已備份/或是 BMP)")

if __name__ == "__main__":
    main()

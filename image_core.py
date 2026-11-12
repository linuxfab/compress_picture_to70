"""
圖片處理工具 - 影像編碼核心與原子寫入模組
"""

import io
import os
import re
import stat
import tempfile
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from ui import FileResult

pillow_heif.register_heif_opener()

# --- 集中管理常數 ---
# 支援的圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic', '.avif'}

# 用於偵測已壓縮檔案的 regex pattern (e.g. _70%, _50%, _500.0KB, _1.0MB)
COMPRESSED_SUFFIX_PATTERN = re.compile(r'_(\d+%|[\d.]+(B|KB|MB|GB))$', re.IGNORECASE)

# 格式映射表 (副檔名 → PIL format string)
FORMAT_MAP = {
    '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG',
    '.webp': 'WEBP', '.avif': 'AVIF',
}

# 反向映射表 (PIL format string → 輸出副檔名)
EXT_BY_FORMAT = {
    'JPEG': '.jpg',
    'JPG': '.jpg',
    'PNG': '.png',
    'WEBP': '.webp',
    'AVIF': '.avif',
}

# 支援動畫輸出的格式 (其餘格式遇到多影格來源會被跳過，避免只剩第一格)
ANIMATED_OUTPUT_FORMATS = {'WEBP'}


def tune_quality_for_target_size(
    img: Image.Image,
    target_bytes: int,
    output_format: str,
    save_kwargs: dict,
    return_data: bool = False,
) -> int | tuple[int, bytes | None]:
    """使用記憶體二分搜尋法動態逼近符合大小上限的最佳品質 (不超過目標體積，且畫質最高)"""
    low, high = 40, 95
    best_q = low
    best_data: bytes | None = None
    fallback_data: bytes | None = None
    kwargs = save_kwargs.copy()

    # 5 次迭代即可在 40-95 之間精確收斂
    for _ in range(5):
        mid = (low + high) // 2
        kwargs['quality'] = mid
        buf = io.BytesIO()
        try:
            img.save(buf, format=output_format, **kwargs)
            size = buf.tell()
            cur_data = buf.getvalue() if return_data else None
        except Exception:
            size = float('inf')
            cur_data = None
        finally:
            buf.close()

        if size <= target_bytes:
            best_q = mid
            best_data = cur_data
            low = mid + 1
        else:
            if mid == 40:
                fallback_data = cur_data
            high = mid - 1

    if return_data:
        return best_q, (best_data if best_data is not None else fallback_data)
    return best_q


def get_exif_data(img: Image.Image) -> bytes | None:
    """取得圖片的 EXIF 資料"""
    try:
        return img.info.get('exif')
    except Exception:
        return None


def is_animated_image(img: Image.Image) -> bool:
    """判斷圖片是否為多影格動畫 (動畫 WebP / APNG / 動畫 AVIF 等)"""
    return bool(getattr(img, 'is_animated', False)) and getattr(img, 'n_frames', 1) > 1


def _encode_animated_webp(
    src: Image.Image,
    quality: int,
    scale: float,
    lossless: bool,
    exif_data: bytes | None,
) -> bytes:
    """
    逐格讀取動畫並重新編碼為動畫 WebP，保留每一格的顯示時間 (duration) 與循環次數 (loop)。
    """
    frames: list[Image.Image] = []
    durations: list[int] = []
    default_duration = int(src.info.get('duration') or 100)

    for frame in ImageSequence.Iterator(src):
        f = frame.convert('RGBA')
        if 0.1 <= scale < 1.0:
            f = f.resize(
                (max(1, int(f.width * scale)), max(1, int(f.height * scale))),
                Image.Resampling.LANCZOS,
            )
        frames.append(f)
        durations.append(int(frame.info.get('duration') or default_duration))

    save_kwargs: dict = {
        'format': 'WEBP',
        'save_all': True,
        'append_images': frames[1:],
        'duration': durations,
        'loop': int(src.info.get('loop', 0)),
    }
    if lossless:
        save_kwargs['lossless'] = True
    else:
        save_kwargs['quality'] = quality
        save_kwargs['method'] = 4
    if exif_data:
        save_kwargs['exif'] = exif_data

    buf = io.BytesIO()
    try:
        frames[0].save(buf, **save_kwargs)
        return buf.getvalue()
    finally:
        buf.close()


def _encode_still_image(
    img: Image.Image,
    output_format: str,
    quality: int,
    keep_exif: bool,
    scale: float,
    lossless: bool,
    original_size: int,
    target_size_bytes: int | None,
) -> bytes:
    """單張靜態圖片的完整編碼流程：EXIF 轉正 → 縮放 → 色彩模式標準化 → (目標大小逼近) → 編碼"""
    img = ImageOps.exif_transpose(img)

    if 0.1 <= scale < 1.0:
        new_width = max(1, int(img.width * scale))
        new_height = max(1, int(img.height * scale))
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    exif_data = get_exif_data(img) if keep_exif else None

    # 若為 P (調色盤) 模式且含透明資訊，先轉為 RGBA 以保留透明通道供後續白底融合或透明輸出
    if img.mode == 'P' and 'transparency' in img.info:
        img = img.convert('RGBA')

    # 色彩模式標準化與透明背景融合
    if img.mode in ('RGBA', 'LA') and output_format in ('JPEG', 'JPG'):
        bg_color = (255, 255, 255) if img.mode == 'RGBA' else 255
        background = Image.new(img.mode[:-1] if img.mode == 'RGBA' else 'L', img.size, bg_color)
        if img.mode == 'RGBA':
            background.paste(img, mask=img.split()[3])
            img = background.convert('RGB')
        else:
            background.paste(img, mask=img.split()[1])
            img = background.convert('RGB')
    elif img.mode in ('CMYK', 'P') and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        img = img.convert('RGB')

    save_kwargs: dict = {'optimize': True}

    if lossless and output_format in ('WEBP', 'AVIF'):
        save_kwargs['lossless'] = True

    if output_format in ('JPEG', 'JPG'):
        if original_size > 10240:
            save_kwargs['progressive'] = True
    elif output_format == 'WEBP' and not lossless:
        save_kwargs['method'] = 6

    if exif_data:
        save_kwargs['exif'] = exif_data

    data: bytes | None = None

    if target_size_bytes is not None and not lossless and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        quality, data = tune_quality_for_target_size(
            img, target_size_bytes, output_format, save_kwargs, return_data=True
        )

    if not lossless and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        save_kwargs['quality'] = quality

    if data is None:
        buf = io.BytesIO()
        try:
            img.save(buf, format=output_format, **save_kwargs)
            data = buf.getvalue()
        finally:
            buf.close()
    return data


def _atomic_write(target_path: Path, data: bytes) -> None:
    """
    嚴格原子寫入：
    先寫入同目錄下的暫存檔，清除目標唯讀屬性後再以 os.replace() 原子置換。
    若寫入或置換失敗，僅清理暫存檔並向上拋出例外，絕不 fallback 成非原子直寫覆蓋原檔。
    """
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=target_path.suffix,
            dir=str(target_path.parent),
        )
        with os.fdopen(fd, 'wb') as f:
            f.write(data)

        if target_path.exists():
            try:
                os.chmod(target_path, stat.S_IWRITE)
            except OSError:
                pass

        os.replace(tmp_path, str(target_path))
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def process_image_core(
    filepath: Path,
    target_path: Path,
    quality: int,
    keep_exif: bool = True,
    scale: float = 1.0,
    output_format: str | None = None,
    lossless: bool = False,
    skip_if_larger: bool = True,
    force_convert_from: set[str] | None = None,
    file_stat: os.stat_result | None = None,
    target_size_bytes: int | None = None,
) -> FileResult:
    """
    圖片處理核心邏輯：
    1. 開啟圖片並判斷是否為動畫
    2. 動畫：輸出格式支援 (WebP) 則逐格重新編碼；否則跳過並保留原檔
    3. 靜態：EXIF 轉正 → 縮放 → 色彩空間轉換 → (目標大小逼近) → 編碼
    4. 儲存至緩衝區檢查大小
    5. 嚴格原子寫入硬碟並保留 mtime
    """
    try:
        orig_stat = file_stat if file_stat is not None else filepath.stat()
        original_size = orig_stat.st_size

        if not output_format:
            output_format = FORMAT_MAP.get(target_path.suffix.lower(), 'JPEG')
        else:
            output_format = output_format.upper()

        src = Image.open(filepath)
        try:
            if is_animated_image(src):
                if output_format not in ANIMATED_OUTPUT_FORMATS:
                    return FileResult(
                        'skipped',
                        f"跳過動畫圖片 ({getattr(src, 'n_frames', '?')} 格)：輸出格式 {output_format} "
                        f"不支援動畫，已保留原檔 → {filepath.name}",
                        warn=True,
                    )
                exif_data = get_exif_data(src) if keep_exif else None
                data = _encode_animated_webp(src, quality, scale, lossless, exif_data)
            else:
                src.load()
                data = _encode_still_image(
                    src, output_format, quality, keep_exif, scale,
                    lossless, original_size, target_size_bytes,
                )
        finally:
            src.close()

        new_size = len(data)

        orig_ext = filepath.suffix.lower()
        should_force = force_convert_from and orig_ext in force_convert_from

        if skip_if_larger and new_size >= original_size and not should_force:
            return FileResult('size_skip', f"檔案 {filepath.name} 越壓越大，捨棄變更")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target_path, data)
        os.utime(target_path, (orig_stat.st_atime, orig_stat.st_mtime))

        return FileResult('success', "OK", original_size, new_size)

    except UnidentifiedImageError:
        return FileResult('failed', f"無法辨識圖片: {filepath.name}")
    except Exception as e:
        return FileResult('failed', f"處理失敗 {filepath.name}: {e}")

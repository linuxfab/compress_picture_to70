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

from ui import FileResult, format_size

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
    """
    使用記憶體二分搜尋法在 40-95 之間精確逼近符合大小上限的最佳品質 (不超過目標體積且畫質最高)。
    若連品質 40 仍超過目標體積，回傳保底品質 40 與對應編碼結果。
    """
    low, high = 40, 95
    min_quality = low
    best_q = min_quality
    best_data: bytes | None = None
    fallback_data: bytes | None = None
    kwargs = save_kwargs.copy()

    while low <= high:
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
            if mid == min_quality:
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


def get_icc_profile(img: Image.Image) -> bytes | None:
    """取得圖片的 ICC 色彩描述檔 (例如 Display P3 / AdobeRGB)，避免轉檔後色彩偏淡"""
    try:
        icc = img.info.get('icc_profile')
        return icc if isinstance(icc, (bytes, bytearray)) and len(icc) > 0 else None
    except Exception:
        return None


def is_animated_image(img: Image.Image) -> bool:
    """判斷圖片是否為多影格動畫 (動畫 WebP / APNG / 動畫 AVIF 等)"""
    return bool(getattr(img, 'is_animated', False)) and getattr(img, 'n_frames', 1) > 1


def _normalize_image_mode(img: Image.Image, output_format: str) -> Image.Image:
    """
    統一標準化影像色彩模式：
    1. 16-bit 灰階 (I;16 / I;16B / I;16L / I;16N) 先依 8-bit 等比例縮放轉為 L，防止被截斷成全白。
    2. 含透明通道的調色盤 (PA 或含 transparency 的 P) 轉為 RGBA，保留透明度。
    3. 輸出為 JPEG 時：RGBA/LA 與白底融合並轉為 RGB；其餘非 RGB/L 模式一律轉為 RGB。
    4. 輸出為 WebP/AVIF/PNG 時：保留 RGB/L/RGBA/LA (PNG 亦可保留 P)；其餘模式 (CMYK/YCbCr/I/F/1 等) 轉為 RGB。
    """
    if img.mode.startswith('I;16'):
        img = img.point(lambda i: i * (1 / 256)).convert('L')
    elif img.mode == 'PA' or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')

    if output_format in ('JPEG', 'JPG'):
        if img.mode in ('RGBA', 'LA'):
            bg_color = (255, 255, 255) if img.mode == 'RGBA' else 255
            background = Image.new('RGB' if img.mode == 'RGBA' else 'L', img.size, bg_color)
            alpha_idx = 3 if img.mode == 'RGBA' else 1
            background.paste(img, mask=img.split()[alpha_idx])
            return background.convert('RGB')
        if img.mode not in ('RGB', 'L'):
            return img.convert('RGB')
        return img

    allowed_modes = {'RGB', 'L', 'RGBA', 'LA'}
    if output_format == 'PNG':
        allowed_modes.add('P')
    if img.mode not in allowed_modes:
        return img.convert('RGB')
    return img


def _quantize_png(img: Image.Image, colors: int = 256) -> Image.Image:
    """將圖片減色為指定色數的調色盤模式 (保留 Alpha 透明通道)"""
    if img.mode in ('L', 'LA'):
        img = img.convert('RGBA' if img.mode == 'LA' else 'RGB')
    elif img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA' if 'A' in img.mode else 'RGB')
    return img.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)


def _encode_bytes(img: Image.Image, output_format: str, save_kwargs: dict) -> bytes:
    """將單張影像依指定格式與參數編碼為 bytes"""
    buf = io.BytesIO()
    try:
        img.save(buf, format=output_format, **save_kwargs)
        return buf.getvalue()
    finally:
        buf.close()


def _encode_animated_webp(
    src: Image.Image,
    quality: int,
    scale: float,
    lossless: bool,
    exif_data: bytes | None,
    icc_profile: bytes | None = None,
) -> bytes:
    """
    逐格讀取動畫並重新編碼為動畫 WebP，保留每一格的顯示時間 (duration)、循環次數 (loop) 與 ICC 色彩描述檔。
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
    if icc_profile:
        save_kwargs['icc_profile'] = icc_profile

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
    png_quantize: bool = False,
) -> tuple[bytes, str | None, int | None]:
    """
    單張靜態圖片的完整編碼流程：
    取 EXIF/ICC → EXIF 轉正 → 縮放 → 色彩模式標準化 → (目標大小逼近 / 自動縮小) → 編碼
    回傳 (bytes, 提醒訊息或 None, 實際使用的 quality 或 None)
    """
    exif_data = get_exif_data(img) if keep_exif else None
    icc_profile = get_icc_profile(img)

    img = ImageOps.exif_transpose(img)

    if 0.1 <= scale < 1.0:
        new_width = max(1, int(img.width * scale))
        new_height = max(1, int(img.height * scale))
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    img = _normalize_image_mode(img, output_format)

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
    if icc_profile:
        save_kwargs['icc_profile'] = icc_profile

    # PNG 減色量化模式
    if output_format == 'PNG' and png_quantize:
        if target_size_bytes is not None:
            for colors in (256, 128, 64, 32):
                q_img = _quantize_png(img, colors=colors)
                data = _encode_bytes(q_img, 'PNG', save_kwargs)
                if len(data) <= target_size_bytes:
                    return data, None, None
            # 減色至 32 色仍超過目標大小，嘗試漸進縮放
            cur_img = img
            cur_ratio = 1.0
            for _ in range(3):
                cur_ratio *= 0.85
                nw = max(1, int(img.width * cur_ratio))
                nh = max(1, int(img.height * cur_ratio))
                cur_img = img.resize((nw, nh), Image.Resampling.LANCZOS)
                data = _encode_bytes(_quantize_png(cur_img, colors=64), 'PNG', save_kwargs)
                if len(data) <= target_size_bytes:
                    return data, f"PNG 減色並縮放至 {cur_ratio:.0%} 以符合目標大小", None
            return data, (
                f"PNG 減色並縮放後仍大於目標大小 "
                f"({format_size(len(data))} > {format_size(target_size_bytes)})"
            ), None
        return _encode_bytes(_quantize_png(img, colors=256), 'PNG', save_kwargs), None, None

    # 有損格式目標體積自動逼近
    if target_size_bytes is not None and not lossless and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        tuned_q, data = tune_quality_for_target_size(
            img, target_size_bytes, output_format, save_kwargs, return_data=True
        )
        if data is not None and len(data) <= target_size_bytes:
            return data, None, tuned_q

        # 連品質 40 都還是超過目標大小時，自動漸進縮小尺寸 (最多 3 次)
        min_kwargs = save_kwargs.copy()
        min_kwargs['quality'] = 40
        cur_ratio = 1.0
        for _ in range(3):
            cur_ratio *= 0.85
            nw = max(1, int(img.width * cur_ratio))
            nh = max(1, int(img.height * cur_ratio))
            resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
            data = _encode_bytes(resized, output_format, min_kwargs)
            if len(data) <= target_size_bytes:
                return data, f"已降至品質 {tuned_q} 並自動縮放至 {cur_ratio:.0%} 以符合目標大小", tuned_q

        assert data is not None
        return data, (
            f"已降至品質 {tuned_q} 並自動縮放至 {cur_ratio:.0%}，體積仍略大於目標 "
            f"({format_size(len(data))} > {format_size(target_size_bytes)})"
        ), tuned_q

    used_q: int | None = None
    if not lossless and output_format in ('JPEG', 'JPG', 'WEBP', 'AVIF'):
        save_kwargs['quality'] = quality
        used_q = quality

    return _encode_bytes(img, output_format, save_kwargs), None, used_q


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
    png_quantize: bool = False,
) -> FileResult:
    """
    圖片處理核心邏輯：
    1. 若原檔已符合 target_size 且為原地覆蓋 (無縮放/跨格式需求)，直接跳過避免多餘重編碼
    2. 開啟圖片並判斷是否為動畫
    3. 動畫：輸出格式支援 (WebP) 則逐格重新編碼；否則跳過並保留原檔
    4. 靜態：EXIF 轉正 → 縮放 → 色彩空間轉換 → (目標大小逼近) → 編碼 (保留 ICC)
    5. 儲存至緩衝區檢查大小
    6. 嚴格原子寫入硬碟並保留 mtime
    """
    try:
        orig_stat = file_stat if file_stat is not None else filepath.stat()
        original_size = orig_stat.st_size

        if not output_format:
            output_format = FORMAT_MAP.get(target_path.suffix.lower(), 'JPEG')
        else:
            output_format = output_format.upper()

        orig_ext = filepath.suffix.lower()
        should_force = bool(force_convert_from and orig_ext in force_convert_from)

        # 若原檔體積已小於等於目標大小：
        # - 原地覆蓋且無縮放/轉檔需求時，直接保留原檔避免無謂損耗畫質
        # - 其他情況 (例如另存新檔或跨格式) 則免跑二分搜尋，直接以指定 quality 單次編碼
        effective_target_size = target_size_bytes
        if target_size_bytes is not None and original_size <= target_size_bytes and scale >= 1.0 and not should_force:
            if target_path == filepath:
                return FileResult(
                    'skipped',
                    f"檔案已符合目標大小 ({format_size(original_size)} <= {format_size(target_size_bytes)})，跳過重新編碼",
                )
            effective_target_size = None

        warn_note: str | None = None
        quality_used: int | None = None
        src = Image.open(filepath)
        try:
            if is_animated_image(src):
                if output_format not in ANIMATED_OUTPUT_FORMATS:
                    return FileResult(
                        'skipped',
                        f"跳過動畫圖片 ({getattr(src, 'n_frames', '?')} 格)：輸出格式 {output_format} "
                        f"不支援動畫，已保留原檔 → {filepath.name}",
                        original_size=original_size,
                        warn=True,
                        target_path=str(target_path),
                    )
                exif_data = get_exif_data(src) if keep_exif else None
                icc_profile = get_icc_profile(src)
                data = _encode_animated_webp(src, quality, scale, lossless, exif_data, icc_profile)
                quality_used = None if lossless else quality
            else:
                src.load()
                data, warn_note, quality_used = _encode_still_image(
                    src, output_format, quality, keep_exif, scale,
                    lossless, original_size, effective_target_size,
                    png_quantize=png_quantize,
                )
        finally:
            src.close()

        new_size = len(data)

        if skip_if_larger and new_size >= original_size and not should_force:
            return FileResult(
                'size_skip',
                f"檔案 {filepath.name} 越壓越大，捨棄變更",
                original_size=original_size,
                new_size=new_size,
                quality_used=quality_used,
                target_path=str(target_path),
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target_path, data)
        os.utime(target_path, (orig_stat.st_atime, orig_stat.st_mtime))

        if warn_note:
            return FileResult(
                'success', f"{filepath.name}: {warn_note}",
                original_size, new_size, warn=True,
                quality_used=quality_used, target_path=str(target_path),
            )
        return FileResult(
            'success', "OK", original_size, new_size,
            quality_used=quality_used, target_path=str(target_path),
        )

    except UnidentifiedImageError:
        return FileResult('failed', f"無法辨識圖片: {filepath.name}")
    except Exception as e:
        return FileResult('failed', f"處理失敗 {filepath.name}: {e}")

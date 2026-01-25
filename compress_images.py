"""
圖片壓縮工具
遍歷指定目錄及子目錄，將圖片壓縮至70%品質後另存新檔
"""

import os
from pathlib import Path
from PIL import Image

# 支援的圖片格式
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

def compress_image(filepath: Path, quality: int = 70) -> bool:
    """
    壓縮單張圖片並另存新檔
    
    Args:
        filepath: 圖片路徑
        quality: 壓縮品質 (1-100)
    
    Returns:
        bool: 是否成功
    """
    try:
        # 檢查是否已經是壓縮過的檔案
        if '70%' in filepath.stem:
            print(f"跳過已壓縮檔案: {filepath}")
            return False
        
        # 開啟圖片
        img = Image.open(filepath)
        
        # 建立新檔名
        new_name = f"{filepath.stem}_70%{filepath.suffix}"
        new_path = filepath.parent / new_name
        
        # 如果是PNG且有透明度，轉換為RGBA
        if filepath.suffix.lower() == '.png':
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # PNG保持原格式，使用optimize
                img.save(new_path, optimize=True)
            else:
                img.save(new_path, optimize=True)
        else:
            # JPG/JPEG/WEBP 使用quality參數
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img.save(new_path, quality=quality, optimize=True)
        
        original_size = filepath.stat().st_size
        new_size = new_path.stat().st_size
        reduction = (1 - new_size / original_size) * 100
        
        print(f"✓ {filepath.name} -> {new_name}")
        print(f"  原始大小: {original_size/1024:.1f}KB, 壓縮後: {new_size/1024:.1f}KB, 減少: {reduction:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"✗ 處理失敗 {filepath}: {e}")
        return False


def process_directory(directory: str) -> tuple[int, int]:
    """
    處理目錄及所有子目錄中的圖片
    
    Args:
        directory: 目標目錄
    
    Returns:
        tuple: (成功數量, 失敗數量)
    """
    root_path = Path(directory)
    
    if not root_path.exists():
        print(f"目錄不存在: {directory}")
        return 0, 0
    
    success_count = 0
    fail_count = 0
    
    # 遍歷所有檔案
    for filepath in root_path.rglob('*'):
        if filepath.is_file() and filepath.suffix.lower() in SUPPORTED_FORMATS:
            if compress_image(filepath):
                success_count += 1
            else:
                fail_count += 1
    
    return success_count, fail_count


def main():
    import sys
    
    if len(sys.argv) < 2:
        # 互動模式
        directory = input("請輸入目標目錄路徑: ").strip()
        if not directory:
            print("未輸入目錄，程式結束")
            return
    else:
        directory = sys.argv[1]
    
    print(f"\n開始處理目錄: {directory}")
    print("=" * 50)
    
    success, fail = process_directory(directory)
    
    print("=" * 50)
    print(f"處理完成! 成功: {success}, 跳過/失敗: {fail}")


if __name__ == "__main__":
    main()

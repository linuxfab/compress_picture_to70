# 圖片批量壓縮工具

遍歷目錄及所有子目錄，將圖片壓縮後另存新檔。

## 功能

- ✅ 自訂壓縮品質 (1-100%)
- ✅ 並行處理加速批量壓縮
- ✅ 保留 EXIF 資訊 (GPS、拍攝時間等)
- ✅ 覆蓋/跳過已存在檔案
- ✅ 智能判斷：壓縮後變大則自動跳過
- ✅ 支援格式：JPG、JPEG、PNG、WebP、BMP

## 安裝

```bash
pip install Pillow
```

## 使用方式

### 基本用法
```bash
python compress_images.py "D:\Photos"
```

### 完整參數
```bash
python compress_images.py <目錄路徑> [選項]
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-q, --quality` | 壓縮品質 1-100 | 70 |
| `-o, --overwrite` | 覆蓋已存在的壓縮檔 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-w, --workers` | 並行執行緒數 | 4 |

### 範例

```bash
# 50% 品質，8 執行緒並行處理
python compress_images.py "D:\Photos" -q 50 -w 8

# 80% 品質，保留 EXIF，覆蓋舊檔
python compress_images.py "D:\Photos" -q 80 --keep-exif --overwrite

# 互動模式 (會提示輸入目錄)
python compress_images.py
```

## 輸出範例

```
圖片壓縮工具 v2.0
目標目錄: D:\Photos
壓縮品質: 70%
============================================================
找到 15 張圖片，開始處理...
[1/15] ✓ photo1.jpg -> photo1_70%.jpg (2048.0KB -> 512.3KB, -75.0%)
[2/15] ✓ photo2.jpg -> photo2_70%.jpg (1024.0KB -> 320.5KB, -68.7%)
[3/15] 壓縮後變大，跳過: small.jpg (15.2KB -> 18.1KB)
============================================================
處理完成!
  成功壓縮: 12
  跳過(已存在/已壓縮): 1
  跳過(壓縮後變大): 2
  失敗: 0
```

## License

MIT

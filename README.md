# 圖片批量壓縮與轉檔工具

遍歷目錄及所有子目錄，支援圖片壓縮與 WebP 轉檔。已改用 `uv` 進行環境與依賴管理。

## 專案功能

**compress-img (圖片壓縮)**
- ✅ 自訂壓縮品質 (1-100%)
- ✅ 並行處理加速批量壓縮
- ✅ 保留 EXIF 資訊 (GPS、拍攝時間等)
- ✅ 覆蓋/跳過已存在檔案
- ✅ 智能判斷：壓縮後變大則自動跳過
- ✅ 支援格式：JPG、JPEG、PNG、WebP、BMP
- ✅ Dry-run 預覽模式
- ✅ 總空間節省統計 (原始大小 / 壓縮後大小 / 節省百分比)

**images-to-webp (WebP 轉檔)**
- ✅ 將 JPG/PNG/BMP 轉換為 WebP 格式
- ✅ **保持原始目錄結構**：轉檔後存於 `webpimage` 資料夾中，子目錄結構與來源相同
- ✅ 自訂 WebP 壓縮品質
- ✅ 並行處理加速
- ✅ 支援覆蓋已存在檔案
- ✅ Dry-run 預覽模式
- ✅ 總空間節省統計

## 安裝與執行

本專案使用 [uv](https://github.com/astral-sh/uv) 進行管理。

### 1. 安裝 uv
若尚未安裝 uv，請參考 [官方文件](https://docs.astral.sh/uv/getting-started/installation/)。

### 2. 初始化環境
```bash
uv sync
```

### 3. 執行程式

**圖片壓縮 (原地壓縮/另存新檔)**
```bash
uv run compress-img "D:\Photos"
```

**圖片轉 WebP (輸出至 webpimage)**
```bash
uv run images-to-webp "D:\Photos"
```

## 使用方式

### compress-img (圖片壓縮)

```bash
uv run compress-img <目錄路徑> [選項]
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-q, --quality` | 壓縮品質 1-100 | 70 |
| `-o, --overwrite` | 覆蓋已存在的壓縮檔 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-w, --workers` | 並行執行緒數 | 4 |
| `-n, --dry-run` | 預覽模式：僅列出待處理檔案，不實際壓縮 | 否 |

### images-to-webp (WebP 轉檔)

```bash
uv run images-to-webp <目錄路徑> [選項]
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-q, --quality` | WebP 壓縮品質 1-100 | 80 |
| `-o, --overwrite` | 覆蓋已存在的 WebP 檔案 | 否 |
| `-w, --workers` | 並行執行緒數 | 4 |
| `-n, --dry-run` | 預覽模式：僅列出待處理檔案，不實際轉換 | 否 |

### 範例

```bash
# [壓縮] 50% 品質，8 執行緒並行處理
uv run compress-img "D:\Photos" -q 50 -w 8

# [壓縮] 預覽模式，不實際壓縮
uv run compress-img "D:\Photos" --dry-run

# [轉檔] 將 D:\Photos 下所有圖片轉為 WebP，存入 D:\Photos\webpimage，品質 90%
uv run images-to-webp "D:\Photos" -q 90 --overwrite

# [轉檔] 預覽模式
uv run images-to-webp "D:\Photos" --dry-run

# 互動模式 (會提示輸入目錄)
uv run compress-img
uv run images-to-webp
```

### 輸出範例

```
圖片壓縮工具 v2.1
目標目錄: D:\Photos
壓縮品質: 70%
============================================================
[1/50] ✓ photo1.jpg -> photo1_70%.jpg (2048.0KB -> 512.0KB, -75.0%)
[2/50] ✓ photo2.jpg -> photo2_70%.jpg (1024.0KB -> 350.0KB, -65.8%)
...
============================================================
處理完成!
  成功壓縮: 48
  跳過(已存在/已壓縮): 1
  跳過(壓縮後變大): 1
  失敗: 0

  📊 空間統計:
     原始總大小: 150.2 MB
     壓縮後總大小: 82.3 MB
     總共節省: 67.9 MB (45.2%)
```

## 專案結構
- `compress_images.py`: 核心壓縮邏輯
- `images_to_webp.py`: WebP 轉檔與目錄鏡像邏輯
- `pyproject.toml`: 專案設定與依賴管理 (uv)
- `uv.lock`: 依賴鎖定檔

## License

MIT

## Authors
- [linuxfab](https://github.com/linuxfab)
- Last Update: 2026-02-22

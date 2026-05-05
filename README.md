# 圖片批量壓縮與轉檔工具

- GitHub: [https://github.com/linuxfab/compress_picture_to70](https://github.com/linuxfab/compress_picture_to70)
- 最後更新時間: 2026-05-05

遍歷目錄及所有子目錄，支援圖片壓縮與 WebP 轉檔。已改用 `uv` 進行環境與依賴管理。

## 專案功能

**compress-img (圖片壓縮)**
- ✅ 自訂壓縮品質 (1-100%)
- ✅ 並行處理加速批量壓縮 (ProcessPoolExecutor)
- ✅ 保留 EXIF 資訊 (GPS、拍攝時間等)
- ✅ 覆蓋/跳過已存在檔案
- ✅ 智慧判斷：壓縮後變大則自動跳過 (除非是 HEIC/AVIF 轉檔需求)
- ✅ 支援格式：JPG、JPEG、PNG、WebP、BMP、**全新支援 `HEIC` / `AVIF`**（BMP 會自動跳過）
- ✅ Dry-run 預覽模式
- ✅ 總空間節省統計 (原始大小 / 壓縮後大小 / 節省百分比)
- ✅ 支援深度控制 (`--max-depth`)
- ✅ **針對檔案大小進行智慧過濾 (`--min-size`、`--max-size`)**
- ✅ **全新: 支援圖片縮放 (`--scale`)，例如 0.5 可將解析度長寬各減半**
- ✅ Rich 終端機視覺化 (動態進度條、精美報表)
- ✅ 自訂遠端輸出目錄 `--out-dir` 不落地污染資料夾
- ✅ 自動略過隱藏目錄 (`.git`, `.venv` 等)

**images-to-webp (WebP 轉檔)**
- ✅ 將 JPG/PNG/BMP 等格式（**包含 Apple 的 .HEIC**）無縫轉換為 WebP 格式
- ✅ **保持原始目錄結構**：轉檔後存於 `webpimage` 資料夾或自訂 `--out-dir`，子目錄結構不變
- ✅ 自訂 WebP 壓縮品質或無損壓縮 (--lossless)
- ✅ 保留 EXIF 資訊 (--keep-exif)
- ✅ 並行處理加速 (ProcessPoolExecutor)
- ✅ 支援覆蓋已存在檔案
- ✅ Dry-run 預覽模式
- ✅ 總空間節省統計
- ✅ 支援 **深度控制 (--max-depth)** 以及 **智慧大小過濾 (--min-size, --max-size)**
- ✅ **全新: 支援圖片縮放 (`--scale`)**
- ✅ Rich 終端機視覺化 (動態進度條、精美報表)
- ✅ 自動略過隱藏目錄

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
| `-O, --out-dir` | 自訂輸出目錄 (留空則在原地建立) | (無) |
| `-q, --quality` | 壓縮品質 1-100 | 70 |
| `--scale` | 縮放比例 (0.1-1.0)，如 0.5 為長寬減半 | 1.0 |
| `--min-size` | 最小檔案過濾 (低於此大小將跳過，如 500KB, 1MB) | (無) |
| `--max-size` | 最大檔案過濾 (高於此大小將跳過) | (無) |
| `-o, --overwrite` | 覆蓋已存在的壓縮檔 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-w, --workers` | Process 數量 (並行) | 4 |
| `-n, --dry-run` | 預覽模式：僅列出待處理檔案 | 否 |
| `-d, --max-depth`| 最大遞迴深度 (0=不進入子目錄) | 無限 |
| `--skip-if-newer` | 若目標檔案存在且比來源新則跳過 | 否 |

### images-to-webp (WebP 轉檔)

```bash
uv run images-to-webp <目錄路徑> [選項]
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-O, --out-dir` | 自訂輸出目錄 (留空則建立 webpimage 夾) | (無) |
| `-q, --quality` | WebP 壓縮品質 1-100 | 80 |
| `--scale` | 縮放比例 (0.1-1.0) | 1.0 |
| `--min-size` | 最小檔案過濾 (低於此大小將跳過，如 500KB) | (無) |
| `--max-size` | 最大檔案過濾 | (無) |
| `--skip-if-newer` | 若目標檔案存在且比來源新則跳過 (適用於增量備份) | 否 |
| `-o, --overwrite` | 覆蓋已存在的 WebP 檔案 | 否 |
| `-l, --lossless` | 使用無損壓縮 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-w, --workers` | Process 數量 (並行) | 4 |
| `-n, --dry-run` | 預覽模式：僅列出待處理檔案 | 否 |
| `-d, --max-depth`| 最大遞迴深度 | 無限 |

### 範例

```bash
# [解析度減半] 將 D:\Photos 的圖片長寬縮小為 50%，品質維持 70%
uv run compress-img "D:\Photos" --scale 0.5

# [壓縮] 不落地：將 D:\Photos 目錄的結構跟檔案，壓縮存出至 E:\Backup，且品質 50%
uv run compress-img "D:\Photos" -O "E:\Backup" -q 50

# [過濾壓縮] 針對硬碟上 "大於 1MB 且小於 50MB" 的圖去執行減肥
uv run compress-img "D:\Photos" --min-size 1MB --max-size 50MB

# [過濾轉檔] 挑出資料夾中 500KB 以上的圖與 .HEIC 手機照片，跨碟鏡像為 WebP 無損壓縮
uv run images-to-webp "D:\Photos" -O "F:\WebP_Exports" --min-size 500KB --lossless --keep-exif

# [轉檔] 將 D:\Photos 下所有圖片轉為 WebP，存入 D:\Photos\webpimage，無損壓縮並保留 EXIF
uv run images-to-webp "D:\Photos" --lossless --keep-exif

# 互動模式 (會提示輸入目錄)
uv run compress-img
uv run images-to-webp
```

### 輸出範例

```
╭────────────────── 圖片壓縮工具 v7.0 ──────────────────╮
│ 📂 目標歸檔來源: D:\Photos                          │
│ 📁 最後存放位置: [原地放置並加後綴字]                 │
│ ⚙️   壓縮品質: 70%                                   │
│ 📐 縮放比例: 0.5                                     │
│ 🚀 並發數量: 4                                       │
╰─────────────────────────────────────────────────────╯
找到 50 張圖片，開始進行 壓縮與格式標準化...

⠋ 壓縮中... ━━━━━━━━━━━━━━━━━━━━━━━━━╸ 100% 0:00:03

╭─ 📊 執行結果分析 ─┬──────╮
│ 狀態              │ 數量 │
├───────────────────┼──────┤
│ 精簡與輸出成功    │   48 │
│ 條件不符跳過      │    1 │
│ 跳過 (無效壓縮)   │    1 │
│ 失敗              │    0 │
╰───────────────────┴──────╯
╭────────────────┬────────────────────╮
│ 💾 磁碟空間變化   │           容量大小 │
├────────────────┼────────────────────┤
│ 原始總大小      │          150.2 MB  │
│ 處理後總大小    │           82.3 MB  │
│ 實際節省空間    │     67.9 MB (45.2%)│
╰────────────────┴────────────────────╯
```

## 專案結構
- `utils.py`: 共用模組 (FileResult、並行管線、統計彙整、CLI 共用元件)
- `compress_images.py`: 圖片壓縮邏輯 (v7.0)
- `images_to_webp.py`: WebP 轉檔與目錄鏡像邏輯 (v6.0)
- `pyproject.toml`: 專案設定與依賴管理 (uv)
- `uv.lock`: 依賴鎖定檔

## 架構設計

```
utils.py
├── FileResult (dataclass)     — 單檔處理結果，取代全域 mutable state
├── ProcessingSummary           — 批次統計摘要
├── collect_files()             — 遞迴收集圖片檔案 (支援深度/大小過濾)
├── run_pipeline()              — 並行處理管線 (ProcessPoolExecutor)
├── print_summary()             — 結果/空間統計輸出 (Rich Table)
├── create_base_parser()        — 共用 argparse 建構
├── resolve_directory()         — 目錄解析 (含互動模式)
└── validate_quality()          — 品質參數驗證

compress_images.py (v7.0)
├── compress_image()            — 單張壓縮 Worker (支援 HEIC/AVIF 轉 JPEG 與縮放)
└── main()                      — CLI 入口 (整合 Rich UI)

images_to_webp.py (v6.0)
├── convert_to_webp()           — 單張轉檔 Worker (保持目錄樹狀結構與縮放)
└── main()                      — CLI 入口 (整合 Rich UI)
```

## License

MIT

## Authors
- [linuxfab](https://github.com/linuxfab)
- Last Update: 2026-05-05

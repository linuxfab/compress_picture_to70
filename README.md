# 圖片批量壓縮與轉檔工具

遍歷目錄及所有子目錄，支援圖片壓縮與 WebP 轉檔。已改用 `uv` 進行環境與依賴管理。

## 專案功能

**compress-img (圖片壓縮)**
- ✅ 自訂壓縮品質 (1-100%)
- ✅ 並行處理加速批量壓縮
- ✅ 保留 EXIF 資訊 (GPS、拍攝時間等)
- ✅ 覆蓋/跳過已存在檔案
- ✅ 智能判斷：壓縮後變大則自動跳過
- ✅ 支援格式：JPG、JPEG、PNG、WebP、BMP、**全新支援 `HEIC` / `AVIF`**（BMP 會自動跳過）
- ✅ Dry-run 預覽模式
- ✅ 總空間節省統計 (原始大小 / 壓縮後大小 / 節省百分比)
- ✅ 支援深度控制 (--max-depth)
- ✅ **全新: 針對檔案大小進行智慧過濾 (`--min-size`、`--max-size`)**
- ✅ ProcessPoolExecutor 多行程充分利用多核 CPU
- ✅ 全新: Rich 終端機視覺化 (動態進度條、精美報表)
- ✅ 全新: 自訂遠端輸出目錄 `--out-dir` 不落地污染資料夾
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
- ✅ 全新: Rich 終端機視覺化 (動態進度條、精美報表)
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
| `--min-size` | 最小檔案過濾 (低於此大小將跳過，如 500KB, 1MB) | (無) |
| `--max-size` | 最大檔案過濾 (高於此大小將跳過) | (無) |
| `-o, --overwrite` | 覆蓋已存在的壓縮檔 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-w, --workers` | Process 數量 (並行) | 4 |
| `-n, --dry-run` | 預覽模式：僅列出待處理檔案 | 否 |
| `-d, --max-depth`| 最大遞迴深度 (0=不進入子目錄) | 無限 |

### images-to-webp (WebP 轉檔)

```bash
uv run images-to-webp <目錄路徑> [選項]
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-O, --out-dir` | 自訂輸出目錄 (留空則建立 webpimage 夾) | (無) |
| `-q, --quality` | WebP 壓縮品質 1-100 | 80 |
| `--min-size` | 最小檔案過濾 (低於此大小將跳過，如 500KB) | (無) |
| `--max-size` | 最大檔案過濾 | (無) |
| `-o, --overwrite` | 覆蓋已存在的 WebP 檔案 | 否 |
| `-l, --lossless` | 使用無損壓縮 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-w, --workers` | Process 數量 (並行) | 4 |
| `-n, --dry-run` | 預覽模式：僅列出待處理檔案 | 否 |
| `-d, --max-depth`| 最大遞迴深度 | 無限 |

### 範例

```bash
# [壓縮] 不落地：將 D:\Photos 目錄的結構跟檔案，壓縮存出至 E:\Backup，且品質 50%
uv run compress-img "D:\Photos" -O "E:\Backup" -q 50

# [過濾壓縮] 針對硬碟上 "大於 1MB 且小於 50MB" 的圖去執行減肥
uv run compress-img "D:\Photos" --min-size 1MB --max-size 50MB

# [過濾轉檔] 挑出資料夾中 500KB 以上的圖與 .HEIC 手機照片，跨碟鏡像為 WebP 無損壓縮
uv run images-to-webp "D:\Photos" -O "F:\WebP_Exports" --min-size 500KB --lossless --keep-exif

# [轉檔] 將 D:\Photos 下所有圖片轉為 WebP，存入 D:\Photos\webpimage，無損壓縮並保留 EXIF
uv run images-to-webp "D:\Photos" --lossless --keep-exif

# [轉檔] 預覽模式
uv run images-to-webp "D:\Photos" --dry-run

# 互動模式 (會提示輸入目錄)
uv run compress-img
uv run images-to-webp
```

### 輸出範例

```
╭────────────────── 圖片壓縮工具 v5.0 ──────────────────╮
│ 📂 目標歸檔來源: D:\Photos                          │
│ 📁 最後存放位置: [原地放置並加後綴字]                 │
│ ⚙️   壓縮品質: 70%                                   │
│ 🚀 並發數量: 4                                       │
╰─────────────────────────────────────────────────────╯
找到 50 張圖片，開始進行 壓縮...

⠋ 壓縮中... ━━━━━━━━━━━━━━━━━━━━━━━━━╸ 100% 0:00:03

╭─ 📊 執行結果分析 ─┬──────╮
│ 狀態              │ 數量 │
├───────────────────┼──────┤
│ 壓縮精簡成功      │   48 │
│ 跳過 (已備份/隱藏)│    1 │
│ 跳過 (無效壓縮)   │    1 │
│ 失敗              │    0 │
╰───────────────────┴──────╯
╭────────────────┬────────────────────╮
│ 💾 磁碟空間變化   │           容量大小 │
├────────────────┼────────────────────┤
│ 原始總大小      │          150.2 MB  │
│ 壓縮後總大小    │           82.3 MB  │
│ 實際節省空間    │     67.9 MB (45.2%)│
╰────────────────┴────────────────────╯
```

## 專案結構
- `utils.py`: 共用模組 (FileResult、並行管線、統計彙整、CLI 共用元件)
- `compress_images.py`: 圖片壓縮邏輯
- `images_to_webp.py`: WebP 轉檔與目錄鏡像邏輯
- `pyproject.toml`: 專案設定與依賴管理 (uv)
- `uv.lock`: 依賴鎖定檔

## 架構設計

```
utils.py
├── FileResult (dataclass)     — 單檔處理結果，取代全域 mutable state
├── ProcessingSummary           — 批次統計摘要
├── collect_files()             — 遞迴收集圖片檔案
├── run_pipeline()              — 並行處理管線 (ThreadPoolExecutor)
├── print_summary()             — 結果/空間統計輸出
├── create_base_parser()        — 共用 argparse 建構
├── resolve_directory()         — 目錄解析 (含互動模式)
└── validate_quality()          — 品質參數驗證

compress_images.py
├── compress_image()            — 單張壓縮 Worker (回傳 FileResult)
└── main()                      — CLI 入口 (partial 綁定 → run_pipeline)

images_to_webp.py
├── convert_to_webp()           — 單張轉檔 Worker (回傳 FileResult)
└── main()                      — CLI 入口 (partial 綁定 → run_pipeline)
```

## License

MIT

## Authors
- [linuxfab](https://github.com/linuxfab)
- Last Update: 2026-02-22

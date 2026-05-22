# 圖片批量壓縮與轉檔工具 v8.5.0

- GitHub: [https://github.com/linuxfab/compress_picture_to70](https://github.com/linuxfab/compress_picture_to70)
- 最後更新時間: 2026-05-22

遍歷目錄及所有子目錄，支援圖片壓縮與 WebP 轉檔。本版本進行了進階的影像效能優化與 TUI 終端體驗提升。

## 最新改進 (v8.5.0)
- **圖片目標大小自動逼近 (Target-Size Auto-Tuning)**：引進 `-T` / `--target-size` 參數。在有損壓縮 (JPEG/WebP/AVIF) 時，自動採用記憶體二分搜尋法進行逼近計算，使輸出體積不高於目標限制，同時保留最優影像畫質。
- **測試套件擴充**：單元測試從 27 個擴展至 29 個（全數通過），完整覆蓋了二分逼近演算法與核心壓縮流程的目標大小限制功能。

## 最新改進 (v8.4.0)
- **透明通道融合 (Alpha Blending)**：當 `RGBA` / `LA` 圖片轉換為不支援透明的 `JPEG` 時，自動融合白色背景，解決透明像素被轉成黑色斑斑點點的問題。
- **漸進式 JPEG 寫入**：大於 10KB 的 JPEG 寫入時自動啟用 `progressive=True`，不僅利於網頁加速載入，更能額外多省下 2% ~ 8% 的空間。
- **WebP 最高壓縮演算**：WebP 轉換時預設啟用 `method=6`。此模式計算稍慢但能壓出最小體積，對於批量壓縮極具效益。
- **動態進度條狀態 (TUI 提升)**：進度管線中，動態在進度條更新目前剛處理完的檔案名稱，提升視覺互動體驗。
- **WebP 轉換防膨脹**：在 `images_to_webp.py` 引入 `--skip-if-larger` 可選參數，防止某些高壓縮 JPEG 轉換為 WebP 時體積反而膨脹。
- **測試擴增**：單元測試從 24 個擴增至 27 個（全數通過），完整覆蓋了透明背景融合、Progressive JPEG 以及 WebP 防膨脹功能。

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
- ✅ **支援圖片縮放 (`--scale`)**
- ✅ **支援原地覆蓋 (`--in-place`)**，直接取代原檔不加後綴字
- ✅ Rich 終端機視覺化 (動態進度條、精美報表)

**images-to-webp (WebP 轉檔)**
- ✅ 將 JPG/PNG/BMP 等格式（**包含 Apple 的 .HEIC**）無縫轉換為 WebP 格式
- ✅ **保持原始目錄結構**：轉檔後子目錄結構不變
- ✅ 自訂 WebP 壓縮品質或無損壓縮 (--lossless)
- ✅ 保留 EXIF 資訊 (--keep-exif)
- ✅ 並行處理加速 (ProcessPoolExecutor)
- ✅ 支援 **原地轉換 (`--in-place`)**，轉換成功後自動刪除原始檔案
- ✅ Rich 終端機視覺化 (動態進度條、精美報表)

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
# 備註：也可使用別名 compress-images 或 compress_images
```

**圖片轉 WebP (輸出至 webp_output)**
```bash
uv run images-to-webp "D:\Photos"
```

## 使用方式

### compress-img (圖片壓縮)

```bash
uv run compress-img <目錄路徑> [選項]
# 或使用: uv run compress_images <目錄路徑> [選項]
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-O, --out-dir` | 自訂輸出目錄 (留空則在原地建立) | (無) |
| `-q, --quality` | 壓縮品質 1-100 | 70 |
| `--scale` | 縮放比例 (0.1-1.0)，如 0.5 為長寬減半 | 1.0 |
| `--in-place` | 原地覆蓋：直接取代原始檔案 (不加後綴) | 否 |
| `-m, --min-size` | 最小檔案過濾 (如 500KB, 1MB) | (無) |
| `-M, --max-size` | 最大檔案過濾 | (無) |
| `-T, --target-size`| 目標檔案大小限制 (如 500KB, 1MB)，自動逼近最優 quality | (無) |
| `-o, --overwrite` | 覆蓋已存在的壓縮檔 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-w, --workers` | Process 數量 (並行) | 自動偵測 CPU 核心數 (上限 8) |
| `--version` | 顯示版本號 | — |
| `-n, --dry-run` | 預覽模式：僅列出待處理檔案 | 否 |
| `-d, --max-depth`| 最大遞迴深度 (0=不進入子目錄) | 無限 |

### images-to-webp (WebP 轉檔)

```bash
uv run images-to-webp <目錄路徑> [選項]
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-O, --out-dir` | 自訂輸出目錄 | (無) |
| `-q, --quality` | WebP 壓縮品質 1-100 | 80 |
| `--in-place` | 原地轉換：轉換成功後刪除原始檔案 | 否 |
| `-l, --lossless` | 使用無損壓縮 | 否 |
| `-T, --target-size`| 目標檔案大小限制 (如 500KB, 1MB)，自動逼近最優 quality | (無) |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `--skip-if-larger` | 若 WebP 體積大於原圖則捨棄變更 | 否 |

## 專案結構
- `utils.py`: 共用核心模組 (v8.4.0)
- `compress_images.py`: 圖片壓縮 CLI
- `images_to_webp.py`: WebP 轉檔 CLI
- `tests/`: 單元測試 (27 個測試案例)
- `pyproject.toml`: 專案設定與依賴管理 (uv)

## 架構設計

```
utils.py
├── FORMAT_MAP                  — 集中管理的格式映射表
├── process_image_core()        — 統一的圖片處理核心 (開啟/縮放/轉換/原子寫入)
├── collect_files()             — os.walk 掃描 + sorted() 排序
├── run_pipeline()              — 並行處理管線 (ProcessPoolExecutor)
├── validate_scale()            — 共用 scale 參數驗證
├── build_filter_info()         — 共用過濾條件顯示字串組裝
└── print_summary()             — 含平均節省空間的報表
```

## License
MIT

## Authors
- [linuxfab](https://github.com/linuxfab)
- Last Update: 2026-05-21 19:15

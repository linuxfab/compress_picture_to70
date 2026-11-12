# 圖片批量壓縮與轉檔工具 v8.7.0

- GitHub: [https://github.com/linuxfab/compress_picture_to70](https://github.com/linuxfab/compress_picture_to70)
- 最後更新時間: 2026-11-12 19:15

遍歷目錄及所有子目錄，支援圖片壓縮與 WebP / AVIF 轉檔。本版本進行了模組架構重構、嚴格原子寫入保護與完整測試覆蓋。

## 最新改進 (v8.7.0) — 程式碼品質與架構重構
- **單一職責模組拆分**：將原本超過 800 行的 `utils.py` 拆分為三個獨立模組：
  - `ui.py`：Rich 終端機輸出、進度條、`run_pipeline()` 並行管線與統計報表。
  - `cli.py`：CLI 共用參數解析、容量單位轉換、目錄遍歷與檔名衝突標籤分配。
  - `image_core.py`：圖片編碼核心、目標體積二分搜尋與嚴格原子寫入。
  - `utils.py` 保留作為向後相容的統一匯出層 (Facade)。
- **嚴格原子寫入保護 (`_atomic_write`)**：將重複的函式內 `import stat` 移至頂層並抽出 `_atomic_write()`；當 `os.replace()` 失敗時僅清理暫存檔並向上拋出錯誤，移除會破壞原子性的直寫 fallback，確保原檔在任何異常下皆不被損毀。
- **新增 `--format` 參數 (啟用 AVIF 輸出)**：`compress_images.py` 新增 `-f / --format {auto,jpeg,png,webp,avif}`，`images_to_webp.py` 新增 `-f / --format {webp,avif}`，使內建的 `AVIF` 編碼能力正式開放給 CLI 使用。
- **`pyproject.toml` 打包與腳本清理**：改用 `only-include` 精準打包核心模組（排除 `tests/` 與 `scratch/`），並移除重複的 `compress_images` script 定義。
- **測試覆蓋率擴充**：新增 `tests/test_architecture_v87.py`（13 個案例），涵蓋 `run_pipeline()`、`main()` CLI 參數解析、嚴格原子寫入保護、`--format avif` 轉檔與 `pyproject.toml` 設定驗證，總計 **66 個測試全數通過**。

## 歷史改進 (v8.6.0) — 資料安全修復
- **同名不同副檔名衝突保護**：`a.jpg` 與 `a.png` 轉 WebP 時原本都會輸出成 `a.webp` 互相覆蓋（原地模式下兩個原檔還會被刪除）。現在由主程序在送進多程序管線前呼叫 `assign_conflict_tags()` 一次性偵測衝突（不分大小寫），衝突檔案改為 `a_jpg.webp`、`a_png.webp`，並在開始前列出改名清單；同時徹底消除多程序同時寫入同一檔案的競態。
- **原地模式不再覆蓋其他既有檔案**：`--in-place` 只允許「覆寫自己」。若 `IMG.heic → IMG.jpg` 或 `a.jpg → a.webp` 的目標已是另一個既有檔案，未加 `-o` 時會跳過、保留原檔並以黃字提醒。壓縮工具中同目錄的 `IMG.heic` + `IMG.jpg` 則由衝突偵測自動改為 `IMG_heic.jpg`。
- **動畫圖片保護**：偵測多影格來源（動畫 WebP / APNG / 動畫 AVIF）。輸出為 WebP 時逐格重新編碼並保留每格 duration 與 loop（支援 `--scale`）；輸出為 JPEG 等不支援動畫的格式時跳過並保留原檔，不再悄悄只剩第一格。動畫不套用 `--target-size`。
- **壓縮工具排除自己的輸出目錄**：`-O` 指定的目錄位於來源內時，透過 `make_output_dir_excluder()` 在遍歷階段剪除，重複執行不再產生 `out/out/...`。WebP 工具共用同一實作，並修正舊版以目錄名稱排除時會誤排除任意深度同名資料夾的問題。
- **測試**：新增 `tests/test_safety_v86.py`（23 個案例），總計 **53 個測試全數通過**。

## 歷史改進 (v8.5.1)
- **修復自動輸出格式推斷與色彩模式轉換順序**：在 `process_image_core` 中先推斷 `output_format` 再執行色彩模式標準化，修復 `output_format=None` 時 `RGBA` 轉 `.jpg` 漏轉 `RGB` 的問題。
- **P (Palette) 調色盤透明通道處理**：針對帶有 `transparency` 資訊的 `P` 模式圖片（如 PNG-8），先轉為 `RGBA` 以利後續與白底融合（JPEG）或保留完整透明度（WebP/AVIF）。
- **目標大小二分搜尋快取與保底修正**：`tune_quality_for_target_size` 保底品質修正為 `40`（避免極端大圖退回 `70`），並直接快取二分搜尋命中的記憶體編碼結果，免除二次重複編碼開銷。
- **擴充已壓縮後綴識別**：`COMPRESSED_SUFFIX_PATTERN` 新增支援 `_500.0KB`、`_1.5MB` 等由 `--target-size` 產生的後綴，防止二次執行時重複壓縮。
- **消除 Pillow 14 棄用警告與擴充測試**：將測試中的 `getdata()` 替換為 `getpixel()`，單元測試擴充至 **30 個（全數通過，0 警告）**。

## 歷史改進 (v8.5.0 / v8.4.0)
- **圖片目標大小自動逼近 (Target-Size Auto-Tuning)**：引進 `-T` / `--target-size` 參數。在有損壓縮 (JPEG/WebP/AVIF) 時，自動採用記憶體二分搜尋法進行逼近計算，使輸出體積不高於目標限制，同時保留最優影像畫質。
- **透明通道融合 (Alpha Blending)**：當 `RGBA` / `LA` 圖片轉換為不支援透明的 `JPEG` 時，自動融合白色背景，解決透明像素被轉成黑色斑斑點點的問題。
- **漸進式 JPEG 寫入**：大於 10KB 的 JPEG 寫入時自動啟用 `progressive=True`，不僅利於網頁加速載入，更能額外多省下 2% ~ 8% 的空間。
- **WebP 最高壓縮演算**：WebP 轉換時預設啟用 `method=6`。此模式計算稍慢但能壓出最小體積，對於批量壓縮極具效益。
- **動態進度條狀態 (TUI 提升)**：進度管線中，動態在進度條更新目前剛處理完的檔案名稱，提升視覺互動體驗。
- **WebP 轉換防膨脹**：在 `images_to_webp.py` 引入 `--skip-if-larger` 可選參數，防止某些高壓縮 JPEG 轉換為 WebP 時體積反而膨脹。

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
- ✅ **目標大小動態逼近 (`--target-size`)**
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
| `--in-place` | 原地覆蓋：直接取代原始檔案 (不加後綴)；HEIC/AVIF 轉出的 .jpg 若撞到既有檔案需加 `-o` | 否 |
| `-m, --min-size` | 最小檔案過濾 (如 500KB, 1MB) | (無) |
| `-M, --max-size` | 最大檔案過濾 | (無) |
| `-T, --target-size`| 目標檔案大小限制 (如 500KB, 1MB)，自動逼近最優 quality | (無) |
| `-o, --overwrite` | 覆蓋已存在的壓縮檔 | 否 |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-f, --format` | 指定輸出格式 (`auto`, `jpeg`, `png`, `webp`, `avif`) | `auto` |
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
| `--in-place` | 原地轉換：轉換成功後刪除原始檔案；目標 .webp 已存在時需加 `-o` 才覆蓋 | 否 |
| `-l, --lossless` | 使用無損壓縮 | 否 |
| `-T, --target-size`| 目標檔案大小限制 (如 500KB, 1MB)，自動逼近最優 quality | (無) |
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |
| `-f, --format` | 指定輸出格式 (`webp`, `avif`) | `webp` |
| `--skip-if-larger` | 若輸出體積大於原圖則捨棄變更 | 否 |

## 輸出檔名衝突規則 (v8.6.0)

| 情境 | 來源 | 輸出 |
|------|------|------|
| 轉 WebP，同名不同副檔名 | `a.jpg`、`a.png` | `a_jpg.webp`、`a_png.webp` |
| 原地壓縮，HEIC 與 JPG 同名 | `IMG.jpg`、`IMG.heic` | `IMG.jpg` (保留原名)、`IMG_heic.jpg` |
| 標籤後仍撞名 | `a.jpg`、`a.png`、`a_png.jpg` | `a_jpg.webp`、`a_png2.webp`、`a_png.webp` |

- 群組中若有副檔名本來就與輸出相同的檔案，它保留原名；其餘成員加上 `_原副檔名` 標籤。
- 比對一律不分大小寫 (以 Windows/macOS 檔案系統為準)。

## 專案結構
- `ui.py`: 終端機 UI 與 `ProcessPoolExecutor` 並行管線
- `cli.py`: CLI 共用參數解析、目錄掃描與衝突偵測
- `image_core.py`: 影像編碼核心與嚴格原子寫入
- `utils.py`: 共用模組相容匯出層 (v8.7.0)
- `compress_images.py`: 圖片壓縮 CLI
- `images_to_webp.py`: WebP / AVIF 轉檔 CLI
- `tests/`: 單元測試 (66 個測試案例；涵蓋工具函式、影像邏輯、資料安全與架構測試)
- `pyproject.toml`: 專案設定與依賴管理 (uv)

## 架構設計

```
image_core.py
├── FORMAT_MAP / EXT_BY_FORMAT       — 集中管理的雙向格式映射表
├── COMPRESSED_SUFFIX_PATTERN        — 已壓縮檔案後綴匹配 (含百分比與容量後綴)
├── tune_quality_for_target_size()   — 目標體積記憶體二分搜尋逼近與結果快取
├── _atomic_write()                  — 嚴格原子寫入 (失敗清理暫存，絕不直寫破壞原檔)
└── process_image_core()             — 統一的圖片處理核心 (動畫判斷/分派/大小檢查/寫入)
    ├── _encode_still_image()        — 靜態圖：EXIF 轉正/縮放/色彩轉換/目標大小逼近/編碼
    └── _encode_animated_webp()      — 動畫：逐格轉 RGBA 並保留 duration/loop

cli.py
├── collect_files()                  — os.walk 掃描 + exclude_fn 剪枝 + sorted() 排序
├── make_output_dir_excluder()       — 輸出目錄位於來源內時產生剪枝函式 (避免 out/out/...)
├── assign_conflict_tags()           — 主程序一次性偵測輸出檔名衝突並分配唯一標籤
└── create_base_parser() / validate_* — 共用 CLI 參數與檢核

ui.py
├── run_pipeline()                   — 並行處理管線 (ProcessPoolExecutor)
├── build_filter_info()              — 共用過濾條件顯示字串組裝
├── print_conflict_notice()          — 衝突改名清單提示
└── print_summary()                  — 含平均節省空間的 Rich 報表

utils.py                             — Re-export Facade (維持向後相容)
```

## License
MIT

## Authors
- [linuxfab](https://github.com/linuxfab)
- Last Update: 2026-11-12 19:15

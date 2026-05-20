# 圖片批量壓縮與轉檔工具 v8.3.0

- GitHub: [https://github.com/linuxfab/compress_picture_to70](https://github.com/linuxfab/compress_picture_to70)
- 最後更新時間: 2026-05-20

遍歷目錄及所有子目錄，支援圖片壓縮與 WebP 轉檔。本版本進行了重大重構，大幅提升了效能與代碼品質。

## 最新改進 (v8.3.0)
- **Bug 修復**: 修正 `process_image_core` 的 `with Image.open()` context manager 過早退出問題；修正 `buf.getvalue()` 重複記憶體拷貝；修復 HEIC/AVIF `--in-place` 模式下格式轉換後原始檔案未刪除的孤兒檔 bug；**新增 nested 輸出目錄精準過濾**，徹底修復 `images_to_webp.py` 當輸出目錄是深度 nested 子目錄時過濾失效進而重複掃描轉檔檔的漏洞。
- **架構優化**: 提取 `FORMAT_MAP` 常數取代散落各處的 local 映射表；新增 `validate_scale()` 與 `build_filter_info()` 共用函式消滅兩個腳本的重複代碼。
- **可預測性**: `collect_files` 回傳排序後的列表，確保跨平台執行結果一致。
- **CLI**: 新增 `--version` flag；`pyproject.toml` 版本號同步至 `8.3.0`。
- **測試**: 重寫 `test_image_logic.py`，從脆弱的 mock 改為真實 PIL 圖片整合測試 (18 個測試已擴增至 23 個全數通過)。

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
| `-e, --keep-exif` | 保留 EXIF 資訊 | 否 |

## 專案結構
- `utils.py`: 共用核心模組 (v8.3.0)
- `compress_images.py`: 圖片壓縮 CLI
- `images_to_webp.py`: WebP 轉檔 CLI
- `tests/`: 單元測試 (18 個測試案例)
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
- Last Update: 2026-05-10 09:44

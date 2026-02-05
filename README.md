# 圖片批量壓縮工具

遍歷目錄及所有子目錄，將圖片壓縮後另存新檔。已改用 `uv` 進行環境與依賴管理。

## 功能

- ✅ 自訂壓縮品質 (1-100%)
- ✅ 並行處理加速批量壓縮
- ✅ 保留 EXIF 資訊 (GPS、拍攝時間等)
- ✅ 覆蓋/跳過已存在檔案
- ✅ 智能判斷：壓縮後變大則自動跳過
- ✅ 支援格式：JPG、JPEG、PNG、WebP、BMP

## 安裝與執行

本專案使用 [uv](https://github.com/astral-sh/uv) 進行管理。

### 1. 安裝 uv
若尚未安裝 uv，請參考 [官方文件](https://docs.astral.sh/uv/getting-started/installation/)。

### 2. 初始化環境
```bash
uv sync
```

### 3. 執行程式
你可以使用以下指令執行：
```bash
# 使用 uv 執行的腳本別名
uv run compress-img "D:\Photos"

# 或者直接執行 main.py
uv run python main.py "D:\Photos"
```

## 使用方式

### 完整參數
```bash
uv run compress-img <目錄路徑> [選項]
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
uv run compress-img "D:\Photos" -q 50 -w 8

# 80% 品質，保留 EXIF，覆蓋舊檔
uv run compress-img "D:\Photos" -q 80 --keep-exif --overwrite

# 互動模式 (會提示輸入目錄)
uv run compress-img
```

## 專案結構
- `compress_images.py`: 核心壓縮邏輯
- `main.py`: 程式入口
- `pyproject.toml`: 專案設定與依賴管理 (uv)
- `uv.lock`: 依賴鎖定檔

## License

MIT

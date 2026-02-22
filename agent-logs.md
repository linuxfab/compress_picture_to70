# Agent Logs

- 2026-02-22 21:47
  - 重點: 架構重構 — 抽共用模組 `utils.py`、消滅全域 mutable state
  - 影響:
    - 新增 `utils.py`: 包含 `FileResult` dataclass、`ProcessingSummary`、`run_pipeline()` 並行管線、`collect_files()`、`print_summary()`、`create_base_parser()`、`resolve_directory()`、`validate_quality()` 等共用邏輯
    - 重構 `compress_images.py`: 移除全域 `stats`/`stats_lock`，`compress_image()` 改回傳 `FileResult`，使用 `functools.partial` 綁定參數後交由 `run_pipeline()` 執行。版本升至 v3.0
    - 重構 `images_to_webp.py`: 同上重構模式，版本升至 v2.0
    - 更新 `README.md`: 新增架構設計圖、更新專案結構說明
  - 結果: 兩個工具不再有任何全域 mutable state (stats, stats_lock)，消除 thread-safety 隱患。重複邏輯 (argparse setup, stats counting, directory walking, print summary) 全部集中到 `utils.py`，各工具檔只保留業務邏輯 (compress_image / convert_to_webp) 和 CLI 入口。
  - 更新者: Antigravity Agent

- 2026-02-22 21:42
  - 重點: 修復 bug、移除冗餘 import、新增 dry-run 模式與空間節省統計
  - 影響:
    - 修改 `compress_images.py`: 修復 hardcoded `_70%` bug，改用 regex `_\d+%` 通用匹配；移除未使用的 `import os`；新增 `--dry-run` 預覽模式；新增總空間節省統計 (原始/壓縮後/節省百分比)；版本升至 v2.1
    - 修改 `images_to_webp.py`: 移除未使用的 `import os`；新增 `--dry-run` 預覽模式；新增總空間節省統計；版本升至 v1.1
    - 更新 `README.md`: 補充 dry-run 與空間統計說明、新增輸出範例區塊
  - 結果: 兩個工具現在都支援預覽模式，使用者可以在不實際壓縮/轉檔的情況下預覽影響範圍；完成後會顯示詳細的空間節省報告。壓縮檔名偵測不再 hardcode `_70%`，改為通用 regex 匹配。
  - 更新者: Antigravity Agent

- 2026-02-17 17:59
  - 重點: 新增 `images_to_webp.py` 腳本，支援圖片轉 WebP 並保持目錄結構。
  - 影響: 
    - 新增 `d:\googledrive\MyData\antigravity_workspace\工具-壓圖70\images_to_webp.py`
    - 修改 `pyproject.toml` 加入 `images-to-webp` 指令
    - 更新 `README.md` 說明文件
  - 結果: 使用者現在可以使用 `uv run images-to-webp` 將目錄下的圖片批量轉換為 WebP 格式，並會自動建立 `webpimage` 目錄存放結果。
  - 更新者: Antigravity Agent

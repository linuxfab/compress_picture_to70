# Agent Logs

- 2026-05-05 22:45
  - 重點: 導入自動旋轉校正 (Auto-Orientation) 與 AVIF 輸出支援
  - 影響: 
    - 修改 `utils.py`: 引入 `ImageOps.exif_transpose` 解決手機照片縮放後旋轉角度不正確的問題。
    - 擴充 `process_image_core`: 支援 `.avif` 格式輸出與其對應的色彩空間轉換邏輯。
  - 結果: 提升了工具對移動端照片處理的魯棒性，並讓使用者可以選擇更先進的 AVIF 格式以獲得更高的壓縮率。
  - 更新者: Antigravity Agent

- 2026-05-05 22:35
  - 重點: 解決 Git 同步衝突與清理 `.gitignore` 漏網之魚
  - 影響: 
    - 執行 `git rm -r --cached __pycache__`: 修正 `__pycache__` 被錯誤追蹤的問題。
    - 解決 `git pull` 衝突: 處理 `__pycache__` 檔案的 modify/delete 衝突。
    - 執行 `git push`: 同步本地修復至遠端。
  - 結果: 恢復倉庫整潔，確保後續同步不再受編譯暫存檔干擾。
  - 更新者: Antigravity Agent

- 2026-05-05 14:35
  - 重點: 代碼架構大重構與效能優化 (v8.1 / v7.1)
  - 影響: 
    - 修改 `utils.py`: 實作 `process_image_core` 統一處理圖片邏輯；優化 `collect_files` 使用 `os.walk` 提升效能。
    - 修改 `compress_images.py`: 使用 `process_image_core` 簡化邏輯，提升至 v8.1。
    - 修改 `images_to_webp.py`: 使用 `process_image_core` 簡化邏輯，提升至 v7.1。
    - 更新 `README.md`: 反映重構後的架構與新功能（如平均節省空間）。
  - 結果: 大幅提升程式碼重用性與執行效能，減少磁碟 I/O，並提供更詳細的統計數據。
  - 更新者: Gemini CLI Agent

- 2026-05-05 16:51
  - 重點: 實作原地覆蓋功能 (`--in-place`)
  - 影響: 
    - 修改 `utils.py`: 新增 `--in-place` 參數。
    - 修改 `compress_images.py` (v8.0): 支援不加後綴直接蓋掉原檔。
    - 修改 `images_to_webp.py` (v7.0): 支援轉檔後自動刪除來源原檔。
    - 更新 `README.md`: 加入 `--in-place` 的使用範例。
  - 結果: 滿足使用者「解析度減半、畫質80%且直接蓋掉原檔」的需求。
  - 更新者: Antigravity Agent


- 2026-05-05 16:44
  - 重點: 實作圖片縮放功能 (`--scale`)
  - 影響: 
    - 修改 `utils.py`: 在共用 parser 中加入 `--scale` 參數。
    - 修改 `compress_images.py` (v7.0): 在 `compress_image` 中實作縮放邏輯 (LANCZOS)。
    - 修改 `images_to_webp.py` (v6.0): 在 `convert_to_webp` 中實作縮放邏輯。
    - 更新 `README.md`: 加入縮放功能使用範例。
  - 結果: 使用者現在可以使用 `--scale 0.5` 輕鬆將圖片解析度減半，進一步節省儲存空間。
  - 更新者: Antigravity Agent


- 2026-05-05 16:42
  - 重點: README 文件優化與版本資訊校正
  - 影響: 
    - 修改 `README.md`: 移除末尾重複的架構說明與作者資訊，更新 `compress-img` 版本至 v6.0，統一最後更新時間。
    - 修正 `agent-logs.md`: 依照規定格式插入本次更新紀錄。
  - 結果: 文件結構更清晰，消滅了冗餘內容，且版本號與實際程式碼 v6.0 保持一致。
  - 更新者: Antigravity Agent


- 2026-05-03 10:31
  - 重點: 同步變更至 GitHub
  - 影響: 
    - 修改 `.gitignore`: 確保 `.venv` 被正確排除。
    - 執行 `git push`: 將本地提交推送到遠端 `master` 分支。
  - 結果: 確保遠端倉庫與本地開發環境同步，排除不必要的虛擬環境檔案。
  - 更新者: Antigravity Agent


- 2026-05-03 10:30
  - 重點: 程式碼結構與維護性優化 (Type Hinting, 常數集中管理, 測試覆蓋率)
  - 影響: 
    - `utils.py`: 強化 Type Hinting (Callable, Iterable 等)，並集中定義 `SUPPORTED_FORMATS` 與 `COMPRESSED_SUFFIX_PATTERN`。
    - `compress_images.py` 與 `images_to_webp.py`: 移除重複定義的常數，改為從 `utils.py` 匯入。
    - `tests/`: 擴充 `test_utils.py` 並新增 `test_image_logic.py`，使用 Mock 模擬圖片處理流程，大幅提升邏輯驗證的穩定性。
  - 結果: 程式碼更符合現代 Python 規範 (穩健的類型檢查)，減少維護負擔，並透過單元測試確保核心邏輯在重構過程中未發生倒退。
  - 更新者: Gemini CLI Agent

- 2026-05-03 10:15
  - 重點: 實作檔案與目錄處理優化 (保留 mtime、增量備份、例外處理)
  - 影響: 
    - `utils.py` 新增 `--skip-if-newer` CLI 參數支援。
    - `compress_images.py` 和 `images_to_webp.py` 新增使用 `os.utime` 同步來源圖片的建立/修改時間至新圖片上。
    - 加入了針對損壞圖檔的 `PIL.UnidentifiedImageError` 特化例外處理。
    - 修改檔案存在時的覆寫邏輯，搭配 `--skip-if-newer` 實作增量備份過濾機制。
  - 結果: 產出的檔案能完美保留原始照片的拍攝整理時間順序，並能安全地對大型資料夾進行增量壓縮，同時不會因少數損壞圖檔而發生難以理解的報錯。
  - 更新者: Gemini CLI Agent

- 2026-05-03 10:00
  - 重點: 專案分析與 GitHub 資訊同步
  - 影響: 
    - 更新 `README.md`，加入 GitHub 專案網址與最後更新日期。
    - 準備將變動推送到遠端儲存庫。
  - 結果: 專案文件更符合規範，並確保遠端同步。
  - 更新者: Gemini CLI Agent

- 2026-02-22 23:05
  - 重點: 實裝 `pillow-heif` 支援 Apple 高效圖檔及 `min-size` / `max-size` 智慧檔案過濾
  - 影響:
    - `pyproject.toml` 加入了 `pillow-heif` 依賴以支援讀取 `.heic` / `.avif`。
    - `utils.py` 新增 `parse_size_to_bytes` 模組，並將參數 `--min-size` 與 `--max-size` 掛載於 argparse。藉由判斷檔案實際大小精準略過過小或過大的圖檔，極大化 CPU 算力投報率。
    - `compress_images.py` 與 `images_to_webp.py` 新增 .heic / .avif 的註冊以及轉換識別。若壓縮器遇見這兩種特規格式會自動將其轉存為標準的 JPEG (或 WebP)。
  - 結果: 大幅拓寬工具的實用範圍，能一鍵處理來自 iPhone 備份的圖庫。大小過濾則能省下無謂的算力，免於處理幾 KB 的網頁圖示。
  - 更新者: Antigravity Agent
- 2026-02-22 22:15
  - 重點: TUI 終端視覺化、安全避開隱藏目錄、不落地 `--out-dir` 參數導入
  - 影響:
    - `pyproject.toml` 加入了 `rich` 依賴。
    - `utils.py` 進行了 UI 翻新，移除會破壞版面的 `print` 與 `logger`，全部改交由 `rich.progress` 與 `rich.table` 繪製動態進度條及空間報表；
    - 修改 `collect_files` 函式，自動過濾掉任何以 `.` 或 `__` 開頭之隱藏或專案配置目錄。
    - `compress_images.py` 與 `images_to_webp.py` 新增 `-O / --out-dir` 選項，容許使用者將壓縮過的檔案完整鏡像（包含同等樹狀目錄）輸往另一個實體路徑避免原資料夾污染。並新增了美觀的起始歡迎面板 (`Panel`)。
  - 結果: 大幅改善使用者體驗（UX）；進度條讓時間預估更為直觀，且新增之 `--out-dir` 徹底解決了備份檔案雜亂無章的痛點。
  - 更新者: Antigravity Agent
- 2026-02-22 21:55
  - 重點: 實作 7 項優化 (ProcessPoolExecutor, lossless, exif, max-depth, logging, ... )
  - 影響:
    - 修改 `utils.py`: 升級 `run_pipeline` 改用 `ProcessPoolExecutor` 加速 CPU 運算；加入 `setup_logger` 使用 `logging` 取代 `print`；在 `collect_files` 加入深度參數 `-d/--max-depth` 支援。
    - 修改 `compress_images.py`: 加入 BMP 跳過機制；加入 `-d` 參數綁定；更新為 Python logging 機制。升級至 v4.0。
    - 修改 `images_to_webp.py`: 加入 `-l/--lossless` 與 `-e/--keep-exif` 參數，強化 WebP 轉換。升級至 v3.0。
    - 加入了基本的單元測試 `tests/test_utils.py`
  - 結果: 執行速度因多行程可平行化而變得更快；支援深入子目錄控制；支援無損 WebP 轉換；更好的 logging 格式化。
  - 更新者: Antigravity Agent
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

"""
圖片處理工具 - 共用模組匯出層 (Backward Compatibility Facade)

已重構拆分為三個職責單一的子模組：
- `ui.py`: Rich 終端機輸出、進度條、統計報表與並行處理管線
- `cli.py`: CLI 參數解析、檔案大小解析、目錄掃描與衝突偵測
- `image_core.py`: 影像編碼核心、目標大小二分搜尋與嚴格原子寫入

本模組保留所有公開符號的 re-export，維持與舊版 `from utils import ...` 的完全相容。
"""

from cli import (
    __version__,
    assign_conflict_tags,
    collect_files,
    create_base_parser,
    make_output_dir_excluder,
    parse_size_to_bytes,
    resolve_directory,
    validate_max_dim,
    validate_quality,
    validate_scale,
)
from image_core import (
    ANIMATED_OUTPUT_FORMATS,
    COMPRESSED_SUFFIX_PATTERN,
    EXT_BY_FORMAT,
    FORMAT_MAP,
    SUPPORTED_FORMATS,
    get_exif_data,
    get_icc_profile,
    is_animated_image,
    process_image_core,
    tune_quality_for_target_size,
)
from ui import (
    FileResult,
    ProcessingSummary,
    build_filter_info,
    console,
    export_csv_report,
    logger,
    format_size,
    print_conflict_notice,
    print_summary,
    run_pipeline,
    setup_logger,
)

__all__ = [
    "__version__",
    "ANIMATED_OUTPUT_FORMATS",
    "COMPRESSED_SUFFIX_PATTERN",
    "EXT_BY_FORMAT",
    "FORMAT_MAP",
    "SUPPORTED_FORMATS",
    "FileResult",
    "ProcessingSummary",
    "assign_conflict_tags",
    "build_filter_info",
    "collect_files",
    "console",
    "create_base_parser",
    "export_csv_report",
    "format_size",
    "get_exif_data",
    "get_icc_profile",
    "is_animated_image",
    "logger",
    "make_output_dir_excluder",
    "parse_size_to_bytes",
    "print_conflict_notice",
    "print_summary",
    "process_image_core",
    "resolve_directory",
    "run_pipeline",
    "setup_logger",
    "tune_quality_for_target_size",
    "validate_max_dim",
    "validate_quality",
    "validate_scale",
]

"""
專案配置檔案示例
將此檔案複製為 settings.py 並填入您的配置資訊
"""

import os

# 專案根目錄
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# OpenClaw 服務配置
OPENCLAW_CONFIG = {
    "url": "http://127.0.0.1:18789/v1/responses",
    "auth_token": "Bearer YOUR_AUTH_TOKEN_HERE",  # 請替換為您自己的認證token
    "agent_id": "main",
    "model": "YOUR_MODEL_NAME_HERE",  # 請替換為您自己的模型名稱
    "timeout": 120,
}

# 測試配置
TEST_CONFIG = {
    "wait_time": 30,
    "log_dir": os.path.join(BASE_DIR, "logs"),
    "report_dir": os.path.join(BASE_DIR, "reports"),
}

# 日誌配置
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard", "level": "INFO"},
        "file": {
            "class": "logging.FileHandler",
            "filename": os.path.join(TEST_CONFIG["log_dir"], "test_run.log"),
            "formatter": "detailed",
            "level": "DEBUG",
            "encoding": "utf-8",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "DEBUG"},
}

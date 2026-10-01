"""
OpenClaw 客戶端封裝
"""

import json
import logging
from typing import Any, Dict, Optional

import requests
from config.settings import OPENCLAW_CONFIG

logger = logging.getLogger(__name__)


class OpenClawClient:
    """
    OpenClaw HTTP 客戶端
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化客戶端
        """
        self.config = config or OPENCLAW_CONFIG
        self.url = self.config["url"]
        self.timeout = self.config.get("timeout", 30)

    def _get_headers(self) -> Dict[str, str]:
        """
        獲取請求頭
        """
        return {
            "Authorization": self.config["auth_token"],
            "Content-Type": "application/json",
            "x-openclaw-agent-id": self.config["agent_id"],
        }

    def send_message(self, message: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        傳送訊息到 OpenClaw
        """
        headers = self._get_headers()
        if agent_id:
            headers["x-openclaw-agent-id"] = agent_id

        payload = {"model": self.config["model"], "input": message}

        try:
            logger.info("=" * 80)
            logger.info("📤 傳送請求到 OpenClaw")
            logger.info("=" * 80)
            logger.info(f"URL: {self.url}")
            logger.info(f"Agent ID: {headers.get('x-openclaw-agent-id')}")
            logger.info(f"輸入訊息: {message}")
            logger.info(f"完整 Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

            logger.info(f"⏳ 等待響應 (超時: {self.timeout}秒)...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)

            logger.info(f"✅ 收到響應 - HTTP 狀態碼: {response.status_code}")
            response.raise_for_status()

            result = response.json()

            logger.info("=" * 80)
            logger.info("📥 OpenClaw 響應內容:")
            logger.info("=" * 80)
            logger.info(json.dumps(result, ensure_ascii=False, indent=2))
            logger.info("=" * 80)

            return result
        except requests.exceptions.RequestException as e:
            error_msg = f"❌ 請求失敗: {str(e)}"
            logger.error("=" * 80)
            logger.error(error_msg)
            logger.error("=" * 80)
            return {"error": error_msg, "success": False}
        except json.JSONDecodeError as e:
            error_msg = f"❌ JSON 解析失敗: {str(e)}"
            logger.error("=" * 80)
            logger.error(error_msg)
            logger.error(f"響應文本: {response.text if 'response' in locals() else 'N/A'}")
            logger.error("=" * 80)
            return {"error": error_msg, "success": False}

"""
斷言工具模組
提供關鍵詞匹配和文本相似度兩種斷言方式
"""

import difflib
import logging
from typing import List, Union

logger = logging.getLogger(__name__)


class AssertionHelper:
    """
    斷言輔助類
    """

    @staticmethod
    def _strip_tool_result_prefix(text: str) -> str:
        """
        去除 LLM 響應中的工具呼叫結果字首
        例如: '[{"name":"none"}] 您的臨時密碼...' -> '您的臨時密碼...'
        """
        import re

        stripped = text.strip()
        tool_prefix_pattern = r"^\s*\[?\{[^}]*\}\]?\s*"
        while re.match(tool_prefix_pattern, stripped):
            remaining = re.sub(tool_prefix_pattern, "", stripped, count=1)
            if remaining == stripped:
                break
            stripped = remaining.strip()
        return stripped if stripped else text

    @staticmethod
    def extract_response_text(response: dict) -> str:
        """
        從響應中提取文本內容
        支援多種響應格式
        """
        if isinstance(response, str):
            return AssertionHelper._strip_tool_result_prefix(response)

        if isinstance(response, dict):
            if "output" in response:
                return AssertionHelper._strip_tool_result_prefix(str(response["output"]))
            if "message" in response:
                return AssertionHelper._strip_tool_result_prefix(str(response["message"]))
            if "content" in response:
                return AssertionHelper._strip_tool_result_prefix(str(response["content"]))
            if "text" in response:
                return AssertionHelper._strip_tool_result_prefix(str(response["text"]))
            if "result" in response and isinstance(response["result"], dict):
                result = response["result"]
                payloads = result.get("payloads")
                if isinstance(payloads, list) and len(payloads) > 0:
                    texts = []
                    for p in payloads:
                        if isinstance(p, dict) and "text" in p:
                            texts.append(str(p["text"]))
                    if texts:
                        return AssertionHelper._strip_tool_result_prefix("\n".join(texts))
                for key in ("output", "text", "content", "message", "response"):
                    if key in result and result[key]:
                        return AssertionHelper._strip_tool_result_prefix(str(result[key]))
                messages = result.get("messages")
                if isinstance(messages, list) and len(messages) > 0:
                    for msg in reversed(messages):
                        if isinstance(msg, dict):
                            role = msg.get("role", "")
                            if role == "assistant":
                                c = msg.get("content", "")
                                if c:
                                    return AssertionHelper._strip_tool_result_prefix(str(c))
            if "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                if isinstance(choice, dict):
                    if "message" in choice:
                        msg = choice["message"]
                        if isinstance(msg, dict) and "content" in msg:
                            return str(msg["content"])
                        return str(msg)
                    elif "text" in choice:
                        return str(choice["text"])
                return str(choice)
            if "error" in response:
                return str(response["error"])

        logger.warning("extract_response_text: no text found in response, returning empty string")
        return ""

    @staticmethod
    def assert_keywords_in_response(
        response: Union[dict, str],
        keywords: List[str],
        require_all: bool = True,
        case_sensitive: bool = False,
    ) -> bool:
        """
        斷言響應中包含指定關鍵詞

        Args:
            response: 響應內容，可以是字典或字串
            keywords: 要匹配的關鍵詞列表
            require_all: 是否要求所有關鍵詞都必須出現，預設 True
            case_sensitive: 是否區分大小寫，預設 False

        Returns:
            bool: 斷言是否通過
        """
        text = AssertionHelper.extract_response_text(response)

        if not case_sensitive:
            text = text.lower()
            keywords = [kw.lower() for kw in keywords]

        found_keywords = []
        missing_keywords = []

        for keyword in keywords:
            if keyword in text:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

        logger.info(f"找到的關鍵詞: {found_keywords}")
        if missing_keywords:
            logger.warning(f"缺失的關鍵詞: {missing_keywords}")

        if require_all:
            success = len(missing_keywords) == 0
        else:
            success = len(found_keywords) > 0

        if success:
            logger.info("✅ 關鍵詞斷言通過")
        else:
            logger.error("❌ 關鍵詞斷言失敗")

        return success

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """
        計算兩個文本的相似度

        Args:
            text1: 文本1
            text2: 文本2

        Returns:
            float: 相似度，範圍 0.0 - 1.0
        """
        return difflib.SequenceMatcher(None, text1, text2).ratio()

    @staticmethod
    def assert_similarity(
        response: Union[dict, str], expected_text: str, min_similarity: float = 0.6
    ) -> bool:
        """
        斷言響應文本與期望文本的相似度

        Args:
            response: 響應內容
            expected_text: 期望的文本
            min_similarity: 最小相似度閾值，預設 0.6

        Returns:
            bool: 斷言是否通過
        """
        actual_text = AssertionHelper.extract_response_text(response)
        similarity = AssertionHelper.calculate_similarity(actual_text, expected_text)

        logger.info(f"期望文本: {expected_text[:100]}...")
        logger.info(f"實際文本: {actual_text[:100]}...")
        logger.info(f"相似度: {similarity:.2%}")

        success = similarity >= min_similarity

        if success:
            logger.info(f"✅ 相似度斷言通過 (>= {min_similarity:.0%})")
        else:
            logger.error(f"❌ 相似度斷言失敗 (期望 >= {min_similarity:.0%}, 實際 {similarity:.0%})")

        return success

    @staticmethod
    def assert_any_keyword_in_response(
        response: Union[dict, str], keyword_groups: List[List[str]], case_sensitive: bool = False
    ) -> bool:
        """
        斷言響應中包含任意一組關鍵詞中的任意一個

        Args:
            response: 響應內容
            keyword_groups: 關鍵片語列表，每組中任意一個匹配即可
            case_sensitive: 是否區分大小寫

        Returns:
            bool: 斷言是否通過
        """
        text = AssertionHelper.extract_response_text(response)

        if not case_sensitive:
            text = text.lower()

        for i, group in enumerate(keyword_groups):
            for keyword in group:
                kw = keyword if case_sensitive else keyword.lower()
                if kw in text:
                    logger.info(f"✅ 在第 {i + 1} 組中找到關鍵詞: {keyword}")
                    return True

        logger.error("❌ 未在任何關鍵片語中找到匹配")
        return False

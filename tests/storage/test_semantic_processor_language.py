# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openviking.prompts import render_prompt
from openviking.session.memory.utils.language import (
    _detect_language_from_text,
    resolve_output_language,
    resolve_output_language_from_conversation,
    resolve_output_language_from_text,
)


class TestLanguageDetection:
    """語言檢測功能測試。"""

    def test_detect_language_chinese(self):
        text = "這是一箇中文文件，用於測試語言檢測功能"
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "zh-CN"

    def test_detect_language_english_fallback(self):
        text = "This is an English document for testing language detection"
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "en"

    def test_detect_language_japanese(self):
        text = "これは日本語のドキュメントです"
        language = _detect_language_from_text(text, fallback_language="ja")
        assert language == "ja"

    def test_detect_language_kanji_heavy_japanese(self):
        text = "明日は会議です"
        language = _detect_language_from_text(text, fallback_language="ja")
        assert language == "ja"

    @pytest.mark.parametrize(
        "text",
        [
            "明日は会議です",
            "東京都内の企業向け業務管理システム導入に関する技術仕様書",
            "本規約は当社が提供する全てのサービスの利用条件を定めるものです",
        ],
    )
    def test_kanji_heavy_japanese_is_not_mistaken_for_chinese(self, text):
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "ja"

    def test_strong_japanese_text_can_override_system_fallback(self):
        text = (
            "今日は新しい機能の設計を進めます。明日の会議で方針を確認します。"
            "そのあとで実装とテストをまとめます。"
        )
        language = _detect_language_from_text(text, fallback_language="zh-CN")
        assert language == "ja"

    def test_japanese_title_does_not_override_chinese_fallback(self):
        text = "请记住我最近在读《ノルウェイの森》，后面继续用中文讨论这个内容"
        language = _detect_language_from_text(text, fallback_language="zh-CN")
        assert language == "zh-CN"

    def test_single_kana_does_not_override_chinese(self):
        text = "这是中文の测试"
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "zh-CN"

    def test_detect_language_korean(self):
        text = "이것은 한국어 문서입니다"
        language = _detect_language_from_text(text, fallback_language="ko")
        assert language == "ko"

    def test_strong_korean_text_can_override_system_fallback(self):
        text = "이것은 한국어로 작성된 긴 문서입니다 사용자의 선호와 프로젝트 내용을 기록합니다"
        language = _detect_language_from_text(text, fallback_language="zh-CN")
        assert language == "ko"

    def test_detect_language_russian(self):
        text = "Это русский документ"
        language = _detect_language_from_text(text, fallback_language="ru")
        assert language == "ru"

    def test_strong_russian_text_can_override_system_fallback(self):
        text = "Это русский документ для проверки памяти пользователя и настроек проекта"
        language = _detect_language_from_text(text, fallback_language="zh-CN")
        assert language == "ru"

    def test_detect_language_arabic(self):
        text = "هذا مستند باللغة العربية"
        language = _detect_language_from_text(text, fallback_language="ar")
        assert language == "ar"

    def test_strong_arabic_text_can_override_system_fallback(self):
        text = "هذا مستند عربي طويل لتسجيل تفضيلات المستخدم ومعلومات المشروع"
        language = _detect_language_from_text(text, fallback_language="zh-CN")
        assert language == "ar"

    def test_detect_language_empty_text(self):
        text = ""
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "en"

    def test_detect_language_mixed_chinese_english(self):
        text = "這是一個 mixed 文件"
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "zh-CN"

    def test_detect_language_chinese_with_single_korean_char(self):
        text = "這是中文需求，繼續最佳化記憶。한"
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "zh-CN"

    def test_detect_language_chinese_with_single_cyrillic_char(self):
        text = "這是中文需求，繼續最佳化記憶。Д"
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "zh-CN"

    def test_detect_language_english_with_single_korean_char(self):
        text = "Please optimize memory extraction 한"
        language = _detect_language_from_text(text, fallback_language="en")
        assert language == "en"

    def test_detect_language_italian(self):
        text = "Questo documento descrive le preferenze dell utente e il progetto da completare."
        language = _detect_language_from_text(text, fallback_language="it")
        assert language == "it"

    def test_strong_italian_text_can_override_system_fallback(self):
        text = (
            "Questo documento descrive le preferenze dell utente e il progetto da completare. "
            "Il contenuto include le decisioni, le attività, la priorità e una nota finale."
        )
        language = _detect_language_from_text(text, fallback_language="zh-CN")
        assert language == "it"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("project document user data model profile", "en"),
            ("Ce document décrit les préférences de l utilisateur et le projet à terminer.", "fr"),
            (
                "Este documento describe las preferencias del usuario y el proyecto para completar.",
                "es",
            ),
            ("Dieses Dokument beschreibt die Präferenzen der Benutzer und das Projekt.", "de"),
            (
                "Este documento descreve as preferências do usuário e o projeto para completar.",
                "pt",
            ),
        ],
    )
    def test_detect_latin_language_conservatively(self, text, expected):
        language = _detect_language_from_text(text, fallback_language=expected)
        assert language == expected


class TestLanguageFlow:
    """語言檢測 + 模板渲染流程測試。"""

    @pytest.mark.parametrize(
        "lang,content,file_name",
        [
            ("zh-CN", "這是一箇中文Python檔案，包含測試程式碼", "chinese_code.py"),
            ("en", "This is an English Python file for testing", "english_code.py"),
            ("ja", "これは日本語のPythonコードテストファイルです", "japanese_code.py"),
            ("ko", "이것은 한국어 Python 코드 테스트 파일입니다", "korean_code.py"),
            ("ru", "Это русский тестовый файл Python кода", "russian_code.py"),
            ("ar", "هذا ملف اختبار كود بايثون عربي", "arabic_code.py"),
        ],
    )
    def test_language_detection_to_template_flow(self, lang, content, file_name):
        """語言檢測 -> output_language 注入模板 -> prompt 包含語言指令"""
        detected_lang = _detect_language_from_text(content, fallback_language=lang)
        assert detected_lang == lang, f"Expected {lang}, got {detected_lang}"

        prompt = render_prompt(
            "semantic.code_summary",
            {"file_name": file_name, "content": content, "output_language": detected_lang},
        )
        assert f"Output Language: {lang}" in prompt


class TestOverviewGenerationFlow:
    """目錄概述生成流程測試。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "description,override,expected_language",
        [
            ("", "", "en"),
            ("這是用於查詢任務狀態和統計執行時間的客戶端程式碼。", "", "zh-TW"),
            (
                "Este documento descreve as preferências do usuário e o projeto para completar.",
                "",
                "en",
            ),
            ("", "zh-TW", "zh-TW"),
        ],
    )
    async def test_import_paths_do_not_set_overview_language(
        self, description, override, expected_language
    ):
        from openviking.storage.queuefs.semantic_processor import SemanticProcessor

        imports = [f'"github.com/example/module{index}"' for index in range(6)]
        skeleton = "package client\nimport (\n" + "\n".join(imports) + "\n)\nfunc NewClient()"
        config = MagicMock()
        config.output_language_override = override
        config.semantic.max_overview_prompt_chars = 60_000
        config.semantic.overview_batch_size = 50
        config.vlm.get_completion_async = AsyncMock(return_value="# client\nClient overview.")

        with patch(
            "openviking.storage.queuefs.semantic_processor.get_openviking_config",
            return_value=config,
        ):
            await SemanticProcessor()._generate_overview(
                "viking://resources/example/client",
                [{"name": "client.go", "summary": description + "\n" + skeleton}],
                [],
            )

        prompt = config.vlm.get_completion_async.call_args.args[0]
        assert f"Output Language: {expected_language}" in prompt
        assert all(path in prompt for path in imports)

    @pytest.mark.parametrize(
        "lang,file_summaries",
        [
            ("zh-TW", "[1] file1.py: 這是一個Python檔案\n[2] file2.py: 這是另一個檔案"),
            ("en", "[1] file1.py: This is a Python file\n[2] file2.py: Another file"),
            ("en", "[1] file1.py: それはPythonファイルです\n[2] file2.py: これもPython"),
        ],
    )
    def test_overview_generation_language_flow(self, lang, file_summaries):
        """目錄摘要 -> 語言檢測 -> overview 模板"""
        config = MagicMock()
        config.output_language_override = ""
        detected_lang = resolve_output_language(file_summaries, config=config)
        assert detected_lang == lang

        prompt = render_prompt(
            "semantic.overview_generation",
            {
                "dir_name": "test_dir",
                "file_summaries": file_summaries,
                "children_abstracts": "",
                "output_language": detected_lang,
            },
        )
        assert f"Output Language: {lang}" in prompt
        assert "Output in Markdown format" in prompt
        expected_brief_heading = "簡要描述" if lang == "zh-TW" else "Brief Description"
        assert expected_brief_heading in prompt
        assert "abstract_max_chars" not in prompt

    def test_overview_generation_prompt_preserves_repository_hierarchy(self):
        prompt = render_prompt(
            "semantic.overview_generation",
            {
                "dir_name": "repo-root",
                "file_summaries": "[1] pyproject.toml: Python project config",
                "children_abstracts": "- backend/: API service\n- frontend/: web UI",
                "output_language": "en",
            },
        )

        assert "Relationship rules:" in prompt
        assert (
            "- Treat child directories as parts of the same repository unless the summaries clearly show they are independent projects."
            in prompt
        )
        assert (
            "- Do not describe every child directory as an independent project by default."
            in prompt
        )
        assert (
            "- When the summaries indicate a code repository, explain how subdirectories relate to the whole repo, such as services, libraries, apps, modules, or support folders."
            in prompt
        )
        assert (
            "- Describe only what the provided summaries state; do not invent entities, facts, or relationships not present in them."
            in prompt
        )
        assert "Before output, remove any named entity absent from the provided summaries" in prompt
        assert "never fill gaps with outside knowledge" in prompt
        assert "Who it's suitable for, if stated in the provided summaries" in prompt
        assert "keep this paragraph useful as a standalone retrieval abstract" in prompt
        assert "**Directory Coverage** (H2)" in prompt

    def test_chinese_overview_uses_localized_headings(self):
        prompt = render_prompt(
            "semantic.overview_generation",
            {
                "dir_name": "測試",
                "file_summaries": "[1] test.md: 測試文件",
                "children_abstracts": "",
                "output_language": "zh-TW",
            },
        )

        assert "**快速導航** (H2)" in prompt
        assert "**詳細說明** (H2)" in prompt
        assert "**目錄覆蓋** (H2)" in prompt
        assert "**Directory Coverage** (H2)" not in prompt
        assert "**Quick Navigation** (H2)" not in prompt
        assert "**Detailed Description** (H2)" not in prompt


class LanguageAwareMockVLM:
    """語言感知的 MockVLM，根據 prompt 中的 Output Language 返回對應語言的響應。"""

    def __init__(self):
        self.is_available = MagicMock(return_value=True)
        self.prompts_received = []
        self.language_responses = {
            "zh-TW": "中文摘要：這是一個測試函式",
            "en": "English summary: This is a test function",
            "ja": "日本語要約：これはテスト関数です",
            "ko": "한국어 요약: 이것은 테스트 함수입니다",
            "ru": "Резюме на русском: это тестовая функция",
            "ar": "ملخص عربي: هذه وظيفة اختبار",
        }

    async def get_completion_async(self, prompt: str) -> str:
        self.prompts_received.append(prompt)
        for lang, response in self.language_responses.items():
            if f"Output Language: {lang}" in prompt:
                return response
        return self.language_responses["en"]


def _verify_content_language(text: str, expected_lang: str) -> bool:
    """驗證文本內容語言是否符合預期。"""
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    japanese_chars = sum(1 for c in text if "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff")
    korean_chars = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
    russian_chars = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06ff")

    thresholds = {
        "zh-TW": chinese_chars >= 2,
        "en": re.search(r"\b(the|is|are|test|function)\b", text, re.I) is not None,
        "ja": japanese_chars >= 2,
        "ko": korean_chars >= 2,
        "ru": russian_chars >= 2,
        "ar": arabic_chars >= 2,
    }
    return thresholds.get(expected_lang, False)


class TestGenerateTextSummaryOutputLanguage:
    """端到端測試：驗證 _generate_text_summary 生成的內容語言是否符合預期。"""

    _LANGUAGE_LOCALE = {
        "zh-TW": "zh_TW.UTF-8",
        "en": "en_US.UTF-8",
        "ja": "ja_JP.UTF-8",
        "ko": "ko_KR.UTF-8",
        "ru": "ru_RU.UTF-8",
        "ar": "ar_SA.UTF-8",
    }

    @pytest.fixture
    def temp_multilang_files(self):
        """建立包含多種語言內容的臨時測試檔案。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            files = {}

            files["chinese_py"] = tmppath / "chinese_code.py"
            files["chinese_py"].write_text("# 中文Python文件\ndef 你好():\n    print('你好世界')\n")

            files["english_py"] = tmppath / "english_code.py"
            files["english_py"].write_text(
                "# English Python file\ndef hello():\n    print('Hello World')\n"
            )

            files["japanese_py"] = tmppath / "japanese_code.py"
            files["japanese_py"].write_text(
                "# 日本語Pythonファイル\ndef こんにちは():\n    print('こんにちは世界')\n"
            )

            files["korean_py"] = tmppath / "korean_code.py"
            files["korean_py"].write_text(
                "# 한국어 Python 파일\ndef 안녕하세요():\n    print('안녕하세요')\n"
            )

            files["chinese_md"] = tmppath / "chinese_doc.md"
            files["chinese_md"].write_text("# 中文文件\n\n這是一個測試文件，包含中文技術內容。\n")

            files["english_md"] = tmppath / "english_doc.md"
            files["english_md"].write_text(
                "# English Documentation\n\nThis is a test document with English content.\n"
            )

            yield files

    def _create_mock_viking_fs(self, content: str) -> MagicMock:
        mock_fs = MagicMock()
        mock_fs.read_file = AsyncMock(return_value=content)
        return mock_fs

    def _create_mock_config(self, mock_vlm: LanguageAwareMockVLM) -> MagicMock:
        mock_config = MagicMock()
        mock_config.vlm = mock_vlm
        mock_config.output_language_override = ""
        mock_config.language_fallback = "en"
        mock_config.semantic.max_file_content_chars = 10000
        return mock_config

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "file_key,file_name,expected_lang",
        [
            ("chinese_md", "chinese_doc.md", "zh-TW"),
            ("english_md", "english_doc.md", "en"),
        ],
    )
    async def test_e2e_code_output_language(
        self, temp_multilang_files, file_key, file_name, expected_lang
    ):
        """端到端測試：檔案 -> 語言檢測 -> 生成對應語言摘要"""
        from openviking.storage.queuefs.semantic_processor import SemanticProcessor

        content = Path(temp_multilang_files[file_key]).read_text()
        mock_vlm = LanguageAwareMockVLM()
        mock_viking_fs = self._create_mock_viking_fs(content)
        mock_config = self._create_mock_config(mock_vlm)

        with (
            patch.dict(
                os.environ,
                {"LC_ALL": self._LANGUAGE_LOCALE[expected_lang]},
            ),
            patch(
                "openviking.storage.queuefs.semantic_processor.get_viking_fs",
                return_value=mock_viking_fs,
            ),
            patch(
                "openviking.storage.queuefs.semantic_processor.get_openviking_config",
                return_value=mock_config,
            ),
        ):
            processor = SemanticProcessor()
            processor._current_ctx = MagicMock()

            result = await processor._generate_text_summary(
                file_path=temp_multilang_files[file_key],
                file_name=file_name,
                llm_sem=asyncio.Semaphore(1),
            )

            prompt_sent = mock_vlm.prompts_received[0]
            assert f"Output Language: {expected_lang}" in prompt_sent, (
                f"{file_name}: Prompt missing Output Language: {expected_lang}"
            )

            assert _verify_content_language(result["summary"], expected_lang), (
                f"{file_name}: Content language mismatch. Expected {expected_lang}, got: {result['summary']}"
            )
            assert "content" not in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "content,file_name,source_lang",
        [
            ("Это русский тестовый файл Python", "russian_code.py", "ru"),
            ("هذا ملف اختبار كود بايثون عربي", "arabic_code.py", "ar"),
        ],
    )
    async def test_e2e_russian_arabic_fall_back_to_english(self, content, file_name, source_lang):
        """端到端測試：俄文和阿拉伯文內容只會輸出英文"""
        expected_lang = "en"
        from openviking.storage.queuefs.semantic_processor import SemanticProcessor

        mock_vlm = LanguageAwareMockVLM()
        mock_viking_fs = self._create_mock_viking_fs(content)
        mock_config = self._create_mock_config(mock_vlm)

        with (
            patch.dict(
                os.environ,
                {"LC_ALL": self._LANGUAGE_LOCALE[source_lang]},
            ),
            patch(
                "openviking.storage.queuefs.semantic_processor.get_viking_fs",
                return_value=mock_viking_fs,
            ),
            patch(
                "openviking.storage.queuefs.semantic_processor.get_openviking_config",
                return_value=mock_config,
            ),
        ):
            processor = SemanticProcessor()
            processor._current_ctx = MagicMock()

            result = await processor._generate_text_summary(
                file_path=f"/tmp/{file_name}",
                file_name=file_name,
                llm_sem=asyncio.Semaphore(1),
            )

            prompt_sent = mock_vlm.prompts_received[0]
            assert f"Output Language: {expected_lang}" in prompt_sent

            assert _verify_content_language(result["summary"], expected_lang), (
                f"{file_name}: Content language mismatch. Expected {expected_lang}, got: {result['summary']}"
            )


class TestOutputLanguageOverride:
    """Output language is restricted to English or Traditional Chinese (zh-TW)."""

    def _make_config(self, override: str = ""):
        config = MagicMock()
        config.output_language_override = override
        return config

    def test_override_unset_detects_chinese_as_traditional(self):
        config = self._make_config(override="")
        result = resolve_output_language("這是一份關於專案設定的中文文件", config=config)
        assert result == "zh-TW"

    def test_override_unset_uses_english_for_latin_text(self):
        config = self._make_config(override="")
        result = resolve_output_language(
            "Plain English text with no special scripts", config=config
        )
        assert result == "en"

    @pytest.mark.parametrize(
        "text",
        [
            "これは日本語のテキストです",
            "明日は会議です",
            "東京都内の企業向け業務管理システム導入に関する技術仕様書",
            "이것은 한국어 텍스트입니다",
            "Это русский тестовый текст",
            "Este documento descreve as preferências do usuário e o projeto para completar.",
        ],
    )
    def test_other_detected_languages_fall_back_to_english(self, text):
        config = self._make_config(override="")
        assert resolve_output_language(text, config=config) == "en"

    @pytest.mark.parametrize(
        "env",
        [
            {"LC_ALL": "zh_TW.UTF-8"},
            {"LC_ALL": "ja_JP.UTF-8"},
            {"TZ": "Asia/Taipei"},
        ],
    )
    def test_undetectable_content_falls_back_to_english_regardless_of_system(self, env):
        config = self._make_config(override="")
        with patch.dict(os.environ, env, clear=True):
            assert resolve_output_language("12345 ---", config=config) == "en"
            assert resolve_output_language("", config=config) == "en"

    @pytest.mark.parametrize(
        "text",
        [
            "請記住我最近在讀《ノルウェイの森》，後面繼續用中文討論這個內容",
            "這家店的ラーメン很好吃，我們每週都會去吃一次",
            "幸福の味，台北最好吃的甜點店",
        ],
    )
    def test_chinese_with_japanese_loanwords_stays_traditional_chinese(self, text):
        config = self._make_config(override="")
        assert resolve_output_language(text, config=config) == "zh-TW"

    def test_override_en_bypasses_detection(self):
        config = self._make_config(override="en")
        result = resolve_output_language("這是一份中文文件", config=config)
        assert result == "en"

    def test_override_zh_tw_bypasses_detection(self):
        config = self._make_config(override="zh-TW")
        result = resolve_output_language("Plain English text", config=config)
        assert result == "zh-TW"

    @pytest.mark.parametrize("override,expected", [("zh-CN", "zh-TW"), ("ja", "en"), ("fr", "en")])
    def test_unsupported_override_is_clamped(self, override, expected):
        config = self._make_config(override=override)
        assert resolve_output_language("Plain English text", config=config) == expected

    def test_override_whitespace_treated_as_unset(self):
        config = self._make_config(override="   ")
        result = resolve_output_language("這是一份中文文件", config=config)
        assert result == "zh-TW"

    def test_explicit_fallback_is_clamped(self):
        config = self._make_config(override="")
        result = resolve_output_language_from_text("12345", config=config, fallback_language="ja")
        assert result == "en"

    def test_conversation_override_set_bypasses_detection(self):
        config = self._make_config(override="en")
        conversation = "[user]: 請用中文回覆\n[assistant]: reply"
        result = resolve_output_language_from_conversation(conversation, config=config)
        assert result == "en"

    def test_conversation_japanese_user_content_falls_back_to_english(self):
        config = self._make_config(override="")
        conversation = "[user]: これは日本語のメッセージです\n[assistant]: reply"
        result = resolve_output_language_from_conversation(conversation, config=config)
        assert result == "en"

    def test_indexed_conversation_detects_user_content(self):
        config = self._make_config(override="")
        conversation = "[0][user][alice]: 請使用中文\n[1][assistant][bot]: 한국어 응답"
        result = resolve_output_language_from_conversation(conversation, config=config)
        assert result == "zh-TW"

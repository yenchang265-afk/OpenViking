# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""
Language detection utilities.
"""

import re
from typing import Callable

from openviking_cli.utils import get_logger
from openviking_cli.utils.config import get_openviking_config

logger = get_logger(__name__)

_SCRIPT_MIN_CHARS = 2
_SCRIPT_MIN_RATIO = 0.20
_JAPANESE_KANA_MIN_CHARS = 3
# Japanese grammar needs hiragana particles/okurigana even in kanji-heavy text,
# while Chinese only borrows katakana words or a stylistic "の".
_JAPANESE_GRAMMAR_HIRAGANA_RE = re.compile(r"[ぁ-ねは-ゖ]")
_JAPANESE_GRAMMAR_HIRAGANA_MIN_CHARS = 2
_JAPANESE_GRAMMAR_HIRAGANA_MIN_RATIO = 0.10
_STRONG_DOMINANT_MIN_CHARS = 10
_STRONG_DOMINANT_RATIO = 0.95
_PRIMARY_LANGUAGES = {"zh-CN", "en"}
# Generated summaries and memories are only ever written in these languages.
DEFAULT_OUTPUT_LANGUAGE = "en"
TRADITIONAL_CHINESE = "zh-TW"
# Bare import paths are machine tokens too: repeated .com domains otherwise
# count as the Portuguese stopword "com" in code skeletons.
_URI_LANGUAGE_NOISE_RE = re.compile(
    r"\b(?:(?:viking|https?)://|(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}/)"
    r"[^\s<>\]\)\"'`]+"
)

_LATIN_STOPWORDS = {
    "en": set(
        "a an and are as be document for from in is of on please project that the this to user with".split()
    ),
    "it": set(
        "che con da del della di documento e il la le non per preferenze progetto questo questa un una utente".split()
    ),
    "fr": set(
        "avec ce cette de des document du et la le les pour préférences projet que un une utilisateur".split()
    ),
    "es": set(
        "con de del documento el esta este la las los para preferencias proyecto que un una usuario y".split()
    ),
    "de": set(
        "benutzer das der die diese dieser dokument ein eine für ist mit nicht projekt und zu".split()
    ),
    "pt": set(
        "a as com da de do documento e este esta o os para preferências preferencias projeto que um uma usuário usuario".split()
    ),
}

_LATIN_ACCENT_BONUSES = {
    "it": r"[àèéìòù]",
    "fr": r"[àâæçéèêëîïôœùûüÿ]",
    "es": r"[áéíóúüñ¿¡]",
    "de": r"[äöüß]",
    "pt": r"[áâãàçéêíóôõú]",
}
_LATIN_HINT_LANGUAGES = {"it", "fr", "es", "de", "pt"}


def normalize_output_language(language: str) -> str:
    """Map any language code onto a supported output language.

    Chinese variants become Traditional Chinese (zh-TW); everything else,
    including empty or unrecognized codes, becomes English.
    """
    normalized = (language or "").strip().lower().replace("_", "-")
    if normalized == "zh" or normalized.startswith("zh-"):
        return TRADITIONAL_CHINESE
    return DEFAULT_OUTPUT_LANGUAGE


def _passes_threshold(count: int, total: int) -> bool:
    return count >= _SCRIPT_MIN_CHARS and total > 0 and count / total >= _SCRIPT_MIN_RATIO


def _language_allowed_by_fallback(language: str, fallback_language: str) -> bool:
    return language in _PRIMARY_LANGUAGES or language == fallback_language


def _is_strong_dominant(count: int, total: int) -> bool:
    return (
        count >= _STRONG_DOMINANT_MIN_CHARS
        and total > 0
        and count / total >= _STRONG_DOMINANT_RATIO
    )


def _detect_latin_language(text: str, fallback_language: str) -> str:
    """Best-effort detector for common Latin-script languages.

    This intentionally stays conservative: if the signal is weak or tied, it
    uses English instead of guessing a non-English Latin language.
    """
    words = re.findall(r"[a-z\u00c0-\u024f]+", text.lower())
    if len(words) < 3:
        return "en"

    stopword_scores = {
        lang: sum(1 for word in words if word in stopwords)
        for lang, stopwords in _LATIN_STOPWORDS.items()
    }
    scores = dict(stopword_scores)

    lowered = text.lower()
    accent_hits = {}
    for lang, pattern in _LATIN_ACCENT_BONUSES.items():
        accent_hits[lang] = len(re.findall(pattern, lowered))
        scores[lang] += accent_hits[lang]

    language, score = max(scores.items(), key=lambda item: item[1])
    second_score = max((value for key, value in scores.items() if key != language), default=0)
    if language == "en" and score >= 2 and score > second_score:
        return "en"
    if language in _LATIN_HINT_LANGUAGES and len(words) >= 6:
        strong_hint = accent_hits.get(language, 0) > 0 or stopword_scores[language] >= 4
        strong_latin = len(words) >= 20 and score >= 6 and score >= scores.get("en", 0) + 4
        if (
            strong_hint
            and score >= 3
            and score >= scores.get("en", 0) + 2
            and (_language_allowed_by_fallback(language, fallback_language) or strong_latin)
        ):
            return language
    return "en"


def _detect_language_from_text(user_text: str, fallback_language: str) -> str:
    """Internal shared helper to detect dominant language from text."""
    fallback = (fallback_language or "en").strip() or "en"
    user_text = strip_language_detection_noise(user_text)

    if not user_text:
        return fallback

    counts = {
        "zh-CN": len(re.findall(r"[\u4e00-\u9fff]", user_text)),
        "ja_kana": len(re.findall(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]", user_text)),
        "ko": len(re.findall(r"[\uac00-\ud7af]", user_text)),
        "ru": len(re.findall(r"[\u0400-\u04ff]", user_text)),
        "ar": len(re.findall(r"[\u0600-\u06ff]", user_text)),
        "latin": len(re.findall(r"[A-Za-z\u00c0-\u024f]", user_text)),
    }
    signal_total = sum(counts.values())
    if signal_total == 0:
        return fallback

    japanese_total = counts["zh-CN"] + counts["ja_kana"]
    strong_japanese = (
        counts["ja_kana"] >= _STRONG_DOMINANT_MIN_CHARS
        and japanese_total / signal_total >= _STRONG_DOMINANT_RATIO
        and counts["ja_kana"] / japanese_total >= 0.30
    )
    grammar_hiragana = len(_JAPANESE_GRAMMAR_HIRAGANA_RE.findall(user_text))
    japanese_grammar = (
        grammar_hiragana >= _JAPANESE_GRAMMAR_HIRAGANA_MIN_CHARS
        and grammar_hiragana / japanese_total >= _JAPANESE_GRAMMAR_HIRAGANA_MIN_RATIO
    )
    if counts["ja_kana"] >= _JAPANESE_KANA_MIN_CHARS and (
        _language_allowed_by_fallback("ja", fallback) or strong_japanese or japanese_grammar
    ):
        return "ja"

    non_latin_candidates = {
        "zh-CN": counts["zh-CN"],
        "ko": counts["ko"],
        "ru": counts["ru"],
        "ar": counts["ar"],
    }
    language, score = max(non_latin_candidates.items(), key=lambda item: item[1])
    if _passes_threshold(score, signal_total) and (
        _language_allowed_by_fallback(language, fallback)
        or _is_strong_dominant(score, signal_total)
    ):
        return language

    if counts["latin"] > 0:
        return _detect_latin_language(user_text, fallback)
    return fallback


def resolve_with_override(config, detect: Callable[[], str]) -> str:
    """Return config override if set, else call `detect()`.

    The callable returns the detected output language, letting callers choose
    the detector (text vs conversation vs messages) without duplicating the
    override resolution logic. Either way the result is normalized to a
    supported output language (``en`` or ``zh-TW``).
    """
    if config is None:
        config = get_openviking_config()
    override = (getattr(config, "output_language_override", None) or "").strip()
    return normalize_output_language(override or detect())


def resolve_output_language_from_text(
    text: str,
    config=None,
    *,
    fallback_language: str = "en",
) -> str:
    """Resolve output language from text with an explicit fallback language."""
    fallback = (fallback_language or "en").strip() or "en"
    return resolve_with_override(config, lambda: _detect_language_from_text(text, fallback))


def strip_language_detection_noise(text: str) -> str:
    """Remove URIs and bare domain paths that should not affect output language."""
    return _URI_LANGUAGE_NOISE_RE.sub(" ", text or "")


def resolve_output_language(text: str, config=None) -> str:
    """Resolve output language from text, honoring config override before detection.

    Text without a usable language signal resolves to English.
    """
    return resolve_output_language_from_text(
        text, config=config, fallback_language=DEFAULT_OUTPUT_LANGUAGE
    )


def resolve_output_language_from_conversation(conversation: str, config=None) -> str:
    """Resolve output language from a conversation, honoring config override.

    When no override is set, uses `detect_language_from_conversation` which
    scopes detection to user-role content only.
    """
    return resolve_with_override(
        config,
        lambda: detect_language_from_conversation(conversation, DEFAULT_OUTPUT_LANGUAGE),
    )


def detect_language_from_conversation(conversation: str, fallback_language: str = "en") -> str:
    """Detect dominant language from user messages in conversation.

    We intentionally scope detection to user role content so assistant/system
    text does not bias the target output language for stored memories.
    """
    fallback = (fallback_language or "en").strip() or "en"

    # Try to extract user messages from conversation string.
    # Supports "[user]: ...", "User: ...", and indexed headers like
    # "[0][user][alice]: ...".
    user_lines = []
    for line in conversation.split("\n"):
        stripped = line.strip()
        line_lower = stripped.lower()
        if line_lower.startswith("[user]:") or line_lower.startswith("user:"):
            content = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped
            if content:
                user_lines.append(content)
            continue
        if ":" in stripped:
            header, content = stripped.split(":", 1)
            if re.search(r"\[\s*user\s*\]", header.lower()):
                content = content.strip()
                if content:
                    user_lines.append(content)

    user_text = "\n".join(user_lines)

    # If no user messages found, use the whole conversation as fallback
    if not user_text:
        user_text = conversation

    return _detect_language_from_text(user_text, fallback)

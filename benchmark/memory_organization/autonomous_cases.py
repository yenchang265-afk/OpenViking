from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from benchmark.memory_organization.models import fact_lines


@dataclass(frozen=True, slots=True)
class AutonomousCase:
    case_id: str
    category: str
    schemas: tuple[Any, ...]
    initial_files: dict[str, Any]
    expected_groups: dict[str, tuple[frozenset[str], ...]]
    expected_replacements: dict[str, str]
    messages: tuple[Any, ...] = ()
    additional_facts: dict[str, str] | None = None
    maintenance_review_tokens: int | None = None

    @property
    def expected_facts(self) -> dict[str, str]:
        facts = {
            marker: text
            for memory_file in self.initial_files.values()
            for marker, text in fact_lines(memory_file.content)
        }
        facts.update(self.additional_facts or {})
        return facts


def build_cases() -> list[AutonomousCase]:
    from openviking.message import Message, TextPart
    from openviking.session.memory.dataclass import MemoryFile
    from openviking.session.memory.memory_type_registry import MemoryTypeRegistry
    from openviking.session.memory.utils.template_utils import TemplateUtils

    registry = MemoryTypeRegistry(load_schemas=True)
    directory_schema = registry.get("entities")
    profile_schema = registry.get("profile")
    preferences_schema = registry.get("preferences")
    if directory_schema is None or profile_schema is None or preferences_schema is None:
        raise RuntimeError("Production entities/profile/preferences schemas are required")

    directory_root = TemplateUtils.render(directory_schema.directory, {"user_space": "default"})
    directory_files = {
        f"{directory_root}/Projects/atlas.md": MemoryFile(
            uri=f"{directory_root}/Projects/atlas.md",
            memory_type="entities",
            content=(
                "# Atlas\nAtlas 是一個軟體服務。\n\n## 釋出\n"
                "- [F01] 使用分階段釋出。\n"
                "- [F02] 有明確記錄的回滾流程。"
            ),
            extra_fields={"category": "Projects", "name": "atlas"},
        ),
        f"{directory_root}/projects/atlas.md": MemoryFile(
            uri=f"{directory_root}/projects/atlas.md",
            memory_type="entities",
            content=(
                "# Atlas\nAtlas 是一個軟體服務。\n\n## 歸屬與運維\n"
                "- [F03] 由平臺團隊負責。\n"
                "- [F04] 提供健康檢查介面。"
            ),
            extra_fields={"category": "projects", "name": "atlas"},
        ),
    }

    profile_root = TemplateUtils.render(profile_schema.directory, {"user_space": "default"})
    profile_uri = f"{profile_root}/{profile_schema.filename_template}"
    profile_content = """# 安德魯
- [F01] 是一名後端工程師 (as of 2026-08-01)
- [F02] 居住在新加坡 (as of 2026-08-01)
- [F03] 擁有電腦科學碩士學位 (as of 2026-08-01)
- [F04] 已婚 (as of 2026-08-01)
- [F05] 生日是 4 月 18 日 (as of 2026-08-01)
- [F06] 會說英語和普通話 (as of 2026-08-01)
- [F07] 偏好簡潔的書面狀態更新 (as of 2026-08-01)
- [F08] 喜歡包含具體後續行動的評審意見 (as of 2026-08-01)
- [F09] 小型拉取請求使用 squash 合併 (as of 2026-08-01)
- [F10] 會先運行針對性測試，再執行完整測試套件 (as of 2026-08-01)
- [F11] 比起巧妙抽象，更偏好樸素實現 (as of 2026-08-01)
- [F12] 釋出前會記錄行為變化 (as of 2026-08-01)
- [F13] 喜歡吃辣味麵條 (as of 2026-08-01)
- [F14] 不喜歡苦瓜 (as of 2026-08-01)
- [F15] 喝咖啡不加糖 (as of 2026-08-01)
- [F16] 選擇提供素食選項的餐廳 (as of 2026-08-01)
- [F17] 偏好直飛航班 (as of 2026-08-01)
- [F18] 避免乘坐紅眼航班 (as of 2026-08-01)
- [F19] 喜歡安靜的海濱城市 (as of 2026-08-01)
- [F20] 短途旅行時會輕裝出行 (as of 2026-08-01)
- [F21] 喜歡回合制策略遊戲 (as of 2026-08-01)
- [F22] 喜歡合作解謎遊戲 (as of 2026-08-01)
- [F23] 不喜歡競技射擊遊戲 (as of 2026-08-01)
- [F24] 偏好劇情豐富的角色扮演遊戲 (as of 2026-08-01)"""
    profile_files = {
        profile_uri: MemoryFile(
            uri=profile_uri,
            memory_type="profile",
            content=profile_content,
            extra_fields={},
        )
    }

    preferences_root = TemplateUtils.render(preferences_schema.directory, {"user_space": "default"})
    oversized_preference_uri = f"{preferences_root}/安德魯/工作偏好.md"
    status_update_facts = {
        "F25": "偏好狀態更新第一行直接說明當前結論和整體進展。",
        "F26": "喜歡狀態更新用簡短專案符號列出本週期完成事項。",
        "F27": "偏好狀態更新將已經完成和仍在進行的工作分開呈現。",
        "F28": "喜歡狀態更新為每個進行中事項標註明確負責人。",
        "F29": "偏好狀態更新為每個行動項寫出預計完成日期。",
        "F30": "喜歡狀態更新把已經確認的決定單獨放在決定區。",
        "F31": "偏好狀態更新把尚未解決的問題單獨放在開放問題區。",
        "F32": "喜歡狀態更新為關鍵結論附上可量化的進展證據。",
        "F33": "偏好狀態更新明確指出相較上一次更新發生了什麼變化。",
        "F34": "喜歡狀態更新只保留影響當前進展的必要背景資訊。",
        "F35": "偏好狀態更新使用一致術語描述相同專案和里程碑。",
        "F36": "喜歡狀態更新將阻塞事項放在顯眼位置並說明影響。",
        "F37": "偏好狀態更新為每個阻塞事項寫出解除阻塞的下一步。",
        "F38": "喜歡狀態更新在結尾彙總下一週期最重要的三項工作。",
        "F39": "偏好狀態更新附上相關任務、文件或結果檔案的精確連結。",
        "F40": "喜歡狀態更新保持簡潔，避免重複已經記錄的長篇背景。",
        "F57": "偏好狀態更新註明資料統計的時間範圍和樣本口徑。",
        "F58": "喜歡狀態更新對風險使用高、中、低三級標識。",
        "F59": "偏好狀態更新在需要協助時明確寫出請求內容和截止時間。",
        "F60": "喜歡狀態更新同時提供人類可讀摘要和機器可讀附件。",
    }
    test_execution_facts = {
        "F41": "偏好先執行與改動模組直接相關的聚焦測試。",
        "F42": "喜歡聚焦測試通過後再執行受影響子系統的測試套件。",
        "F43": "偏好根據改動風險決定是否繼續執行完整測試套件。",
        "F44": "喜歡在測試前先執行快速的靜態檢查和格式檢查。",
        "F45": "偏好缺陷修復附帶能夠穩定復現原問題的迴歸測試。",
        "F46": "喜歡每個測試只驗證一個清晰的行為結果。",
        "F47": "偏好測試名稱直接描述輸入條件和預期行為。",
        "F48": "喜歡測試使用固定輸入和確定性斷言，避免隨機波動。",
        "F49": "偏好外部服務測試使用記錄好的 mock 資料而不是即時呼叫。",
        "F50": "喜歡為網路和非同步測試設定明確且有限的超時時間。",
        "F51": "偏好併發測試限制工作執行緒數量以保持結果穩定。",
        "F52": "喜歡在隔離臨時目錄中執行會生成檔案的測試。",
        "F53": "偏好測試失敗時輸出實際值、預期值和關鍵上下文。",
        "F54": "喜歡測試保留失敗樣本的隨機種子和輸入引數。",
        "F55": "偏好昂貴評估前先執行一個最小冒煙測試。",
        "F56": "喜歡測試命令支援機器可讀結果和非互動執行。",
        "F61": "偏好按單元測試、整合測試和端到端測試分層執行。",
        "F62": "喜歡只對涉及的測試檔案啟用詳細除錯日誌。",
        "F63": "偏好測試完成後檢查是否殘留臨時檔案和後臺程序。",
        "F64": "喜歡在提交前重複執行曾經不穩定的測試以確認穩定性。",
    }
    existing_growth_facts = {
        **{marker: text for marker, text in status_update_facts.items() if marker <= "F40"},
        **{marker: text for marker, text in test_execution_facts.items() if marker <= "F56"},
    }
    additional_facts = {
        **{marker: text for marker, text in status_update_facts.items() if marker >= "F57"},
        **{marker: text for marker, text in test_execution_facts.items() if marker >= "F61"},
    }
    oversized_preference_content = "\n".join(
        f"- [{marker}] {text}" for marker, text in existing_growth_facts.items()
    )
    additional_fact_text = "\n".join(
        f"- [{marker}] {text}" for marker, text in additional_facts.items()
    )
    oversized_preference_files = {
        oversized_preference_uri: MemoryFile(
            uri=oversized_preference_uri,
            memory_type="preferences",
            content=oversized_preference_content,
            extra_fields={"user": "安德魯", "topic": "工作偏好"},
        )
    }

    return [
        AutonomousCase(
            case_id="case_insensitive_directory_collision",
            category="directory_merge",
            schemas=(directory_schema,),
            initial_files=directory_files,
            expected_groups={"entities": (frozenset({"F01", "F02", "F03", "F04"}),)},
            expected_replacements={
                f"{directory_root}/Projects/atlas.md": f"{directory_root}/projects/atlas.md"
            },
            messages=(
                Message(
                    id="directory-context",
                    role="user",
                    created_at="2026-08-30T10:00:00+08:00",
                    parts=[TextPart("你還記得 Atlas 專案的釋出方式、回滾流程和日常運維資訊嗎？")],
                ),
            ),
        ),
        AutonomousCase(
            case_id="oversized_profile_routes_preferences",
            category="cross_type_split",
            schemas=(profile_schema, preferences_schema),
            initial_files=profile_files,
            expected_groups={
                "profile": (frozenset({"F01", "F02", "F03", "F04", "F05", "F06"}),),
                "preferences": (
                    frozenset({"F07", "F08"}),
                    frozenset({"F09", "F10", "F11", "F12"}),
                    frozenset({"F13", "F14", "F15", "F16"}),
                    frozenset({"F17", "F18", "F19", "F20"}),
                    frozenset({"F21", "F22", "F23", "F24"}),
                ),
            },
            expected_replacements={},
            maintenance_review_tokens=400,
            messages=(
                Message(
                    id="profile-context",
                    role="user",
                    created_at="2026-08-30T10:00:00+08:00",
                    parts=[
                        TextPart(
                            "你還記得我的基本情況，以及我在工作、飲食、旅行和遊戲方面的偏好嗎？"
                        )
                    ],
                ),
            ),
        ),
        AutonomousCase(
            case_id="oversized_preference_splits",
            category="same_type_split",
            schemas=(preferences_schema,),
            initial_files=oversized_preference_files,
            expected_groups={
                "preferences": (
                    frozenset(status_update_facts),
                    frozenset(test_execution_facts),
                )
            },
            expected_replacements={},
            messages=(
                Message(
                    id="growth-update",
                    role="user",
                    peer_id="安德魯",
                    created_at="2026-08-29T02:30:00+08:00",
                    parts=[TextPart("請記住我新增的這些偏好：\n" + additional_fact_text)],
                ),
            ),
            additional_facts=additional_facts,
        ),
    ]

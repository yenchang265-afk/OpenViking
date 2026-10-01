"""
Pytest 配置檔案 - 新增測試報告中文描述和環境資訊
"""

import datetime
import platform
import subprocess


def get_openclaw_version():
    """獲取 OpenClaw 版本"""
    try:
        result = subprocess.run(
            ["openclaw", "--version"], capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return "Unknown"


def get_openviking_version():
    """獲取 OpenViking 版本"""
    # Method 1: Try to import openviking module directly
    try:
        import openviking

        version = getattr(openviking, "__version__", None)
        if version and version != "0.0.0+unknown":
            return version
    except Exception:
        pass

    # Method 2: Try to use ov CLI
    try:
        result = subprocess.run(["ov", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip()
        if version and version != "0.0.0+unknown":
            return version
    except Exception:
        pass

    # Method 3: Try to get version from pip show
    try:
        result = subprocess.run(
            ["pip", "show", "openviking"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
                if version and version != "0.0.0+unknown":
                    return version
    except Exception:
        pass

    # Method 4: Try to get version from git
    try:
        import os

        project_dir = os.environ.get("PROJECT_DIR", "/root/project/OpenViking")
        if os.path.exists(os.path.join(project_dir, ".git")):
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = result.stdout.strip()
            if version:
                return f"dev-{version}"
    except Exception:
        pass

    return "Unknown"


def pytest_html_report_title(report):
    """自定義報告標題"""
    report.title = "OpenClaw + OpenViking 端到端自動化測試報告"


def pytest_html_results_summary(prefix, summary, postfix):
    """自定義報告摘要 - 新增環境資訊和測試說明"""
    openclaw_version = get_openclaw_version()
    openviking_version = get_openviking_version()
    test_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os_info = f"{platform.system()} {platform.release()}"

    prefix.extend(
        [
            '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 8px; margin-bottom: 20px;">',
            '<h1 style="color: white; margin: 0; font-size: 28px;">OpenClaw + OpenViking 端到端自動化測試報告</h1>',
            '<p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0; font-size: 16px;">驗證記憶讀寫功能的完整性與可靠性</p>',
            "</div>",
            '<div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px;">',
            '<h3 style="margin-top: 0; color: #333;">📊 環境資訊</h3>',
            '<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">',
            '<tr><td style="padding: 8px; border-bottom: 1px solid #ddd; width: 20%;"><strong>📋 專案名稱</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">OpenClaw + OpenViking 端到端自動化測試</td></tr>',
            f'<tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>📅 測試日期</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{test_date}</td></tr>',
            f'<tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>💻 作業系統</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{os_info}</td></tr>',
            f'<tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>🦞 OpenClaw 版本</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{openclaw_version}</td></tr>',
            f'<tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>🧠 OpenViking 版本</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{openviking_version}</td></tr>',
            '<tr><td style="padding: 8px;"><strong>🔗 測試方式</strong></td><td style="padding: 8px;">OpenClaw CLI (--session-id)</td></tr>',
            "</table>",
            "</div>",
            '<h2 style="color: #4a90e2; border-bottom: 2px solid #4a90e2; padding-bottom: 10px;">📖 測試說明</h2>',
            '<div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin: 15px 0;">',
            '<p style="margin: 0 0 10px 0; font-size: 14px;">本測試驗證 OpenClaw 與 OpenViking 之間的核心互動功能，包括：</p>',
            '<ul style="margin: 0; padding-left: 20px; font-size: 14px;">',
            '<li style="margin: 5px 0;">✅ 記憶結構化寫入驗證</li>',
            '<li style="margin: 5px 0;">✅ 記憶讀取/更新/刪除驗證</li>',
            '<li style="margin: 5px 0;">✅ assemble() 歷史組裝回放驗證</li>',
            '<li style="margin: 5px 0;">✅ compact() 壓縮歸檔驗證</li>',
            '<li style="margin: 5px 0;">✅ 跨 session recall 記憶檢索注入驗證</li>',
            '<li style="margin: 5px 0;">✅ memory_recall 顯式搜尋驗證</li>',
            '<li style="margin: 5px 0;">✅ ov_archive_expand 展開驗證</li>',
            '<li style="margin: 5px 0;">✅ session 對話上下文隔離驗證</li>',
            "</ul>",
            "</div>",
            '<hr style="margin: 25px 0; border: none; border-top: 1px solid #e0e0e0;">',
        ]
    )


def pytest_html_results_table_header(cells):
    """自定義結果表格表頭"""
    cells.insert(2, '<th style="width: 35%;">📝 測試描述</th>')


def pytest_html_results_table_row(report, cells):
    """自定義結果表格行 - 新增中文測試描述"""
    description = "暫無描述"

    test_descriptions = {
        "test_memory_update_verify": "驗證記憶更新功能（年齡、職業、地址），確保更新正確生效",
        "test_memory_delete_verify": "驗證記憶刪除功能，寫入臨時資訊後刪除並驗證",
        "test_memory_persistence_group_a": "跨會話讀取驗證-組A：我喜歡吃櫻桃，日常喜歡喝美式咖啡，驗證記憶持久化儲存",
        "test_memory_persistence_group_b": "跨會話讀取驗證-組B：我喜歡吃芒果，日常喜歡喝拿鐵咖啡，驗證記憶持久化儲存",
        "test_memory_persistence_group_c": "跨會話讀取驗證-組C：我喜歡吃草莓，日常喜歡喝抹茶拿鐵，驗證記憶持久化儲存",
        "test_memory_update_overwrite_group_a": "更新覆蓋驗證-組A：初始資訊30歲→更新為31歲+生日8月，驗證舊記憶被覆蓋",
        "test_memory_v2_preferences": "Memory V2偏好設定記憶：對話寫入程式語言/編輯器/咖啡偏好→commit→驗證preferences目錄下新增記憶檔案",
        "test_memory_v2_entities": "Memory V2實體資訊記憶：對話寫入姓名/年齡/職業/公司/住址→commit→驗證entities目錄下新增記憶檔案",
        "test_memory_v2_profile": "Memory V2使用者畫像記憶：對話寫入技術負責人畫像→commit→驗證profile.md檔案新增或更新",
        "test_memory_v2_skills": "Memory V2技能記憶：對話寫入Docker/K8s/CI-CD技能→commit→驗證user/skills目錄下新增記憶檔案",
        "test_assemble_replays_archive_summary": "assemble()歷史組裝驗證：寫入資訊→commit生成archive→新session→驗證archive summary被載入回放",
        "test_compact_produces_archive_on_threshold": "compact()壓縮歸檔驗證：持續對話超閾值→驗證archive生成+記憶檔案生成+上下文被壓縮",
        "test_memory_recall_explicit_search": "memory_recall顯式搜尋驗證：寫入獨特資訊→commit+記憶提取→新session用模糊提示觸發顯式搜尋→驗證搜尋結果",
        "test_archive_expand_restores_details": "ov_archive_expand展開驗證：寫入含細節資訊→commit生成archive→詢問細節觸發展開→驗證原始細節被還原",
        "test_session_isolation_no_cross_contamination": "session對話上下文隔離驗證：session A寫入甲資訊→session B寫入乙資訊→分別查詢對話上下文→驗證互不干擾",
    }

    for test_name, desc in test_descriptions.items():
        if test_name in report.nodeid:
            description = desc
            break

    cells.insert(
        2,
        f'<td style="max-width: 450px; word-wrap: break-word; font-size: 13px; line-height: 1.5;">{description}</td>',
    )

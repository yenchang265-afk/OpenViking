import os
import time

import psutil
import pytest
from api.client import OpenVikingAPIClient
from config import Config

TEST_CASE_DESCRIPTIONS = {
    "test_add_resource.py::TestAddResource::test_add_resource_simple": "向知識庫新增資源",
    "test_pack.py::TestPack::test_export_ovpack": "匯出資源包",
    "test_wait_processed.py::TestWaitProcessed::test_wait_processed": "等待資源處理完成",
    "test_fs_ls.py::TestFsLs::test_fs_ls_root": "列出檔案系統根目錄",
    "test_fs_mkdir.py::TestFsMkdir::test_fs_mkdir": "建立目錄",
    "test_fs_cp.py::TestFsCp::test_cp_file_preserves_source_and_content": "複製檔案和向量",
    "test_fs_mv.py::TestFsMv::test_fs_mv": "移動檔案/目錄",
    "test_fs_read_write.py::TestFsReadWrite::test_fs_read": "讀取檔案內容",
    "test_fs_rm.py::TestFsRm::test_fs_rm": "刪除檔案/目錄",
    "test_fs_stat.py::TestFsStat::test_fs_stat": "獲取檔案狀態",
    "test_fs_tree.py::TestFsTree::test_fs_tree": "獲取目錄樹結構",
    "test_get_abstract.py::TestGetAbstract::test_get_abstract": "獲取內容摘要",
    "test_get_overview.py::TestGetOverview::test_get_overview": "獲取內容概覽",
    "test_add_message.py::TestAddMessage::test_add_message": "向會話新增訊息",
    "test_create_session.py::TestCreateSession::test_create_session": "建立會話",
    "test_delete_session.py::TestDeleteSession::test_delete_session": "刪除會話",
    "test_get_session.py::TestGetSession::test_get_session": "獲取會話資訊",
    "test_list_sessions.py::TestListSessions::test_list_sessions": "列出所有會話",
    "test_find.py::TestFind::test_find_basic": "基礎查詢搜尋",
    "test_find.py::TestFind::test_find_with_different_query": "不同查詢的查詢搜尋",
    "test_search.py::TestSearch::test_basic_search": "基礎語義搜尋",
    "test_search.py::TestSearch::test_search_with_different_query": "不同查詢的語義搜尋",
    "test_grep.py::TestGrep::test_grep_basic": "基礎文本搜尋",
    "test_glob.py::TestGlob::test_glob_basic": "基礎模式匹配",
    "test_is_healthy.py::TestIsHealthy::test_is_healthy": "檢查系統健康狀態",
    "test_observer.py::TestObserver::test_observer_queue": "觀察任務佇列狀態",
    "test_observer.py::TestObserver::test_observer_vikingdb": "觀察向量資料庫狀態",
    "test_observer.py::TestObserver::test_observer_system": "觀察系統整體狀態",
    "test_system_status.py::TestSystemStatus::test_system_status": "獲取系統狀態",
    "test_system_wait.py::TestSystemWait::test_system_wait": "等待系統處理完成",
    "test_admin_accounts.py::TestAdminAccounts::test_admin_list_accounts": "列出所有帳戶",
    "test_admin_accounts.py::TestAdminAccounts::test_admin_create_delete_account": "建立和刪除帳戶",
    "test_admin_regenerate_key.py::TestAdminRegenerateKey::test_admin_regenerate_key": "重新生成API金鑰",
    "test_admin_role.py::TestAdminRole::test_admin_set_role": "設定使用者角色",
    "test_admin_users.py::TestAdminUsers::test_admin_list_users": "列出帳戶下的使用者",
    "test_admin_users.py::TestAdminUsers::test_admin_register_remove_user": "註冊和刪除使用者",
    "test_server_health_check.py::TestServerHealthCheck::test_server_health_check": "伺服器健康檢查",
    "test_semantic_retrieval.py::TestSemanticRetrieval::test_semantic_retrieval_end_to_end": "語義檢索全鏈路驗證",
    "test_resource_swap.py::TestResourceSwap::test_resource_incremental_update": "資源增量更新",
    "test_grep_validation.py::TestGrepValidation::test_grep_pattern_match": "正則檢索驗證",
    "test_delete_sync.py::TestDeleteSync::test_resource_deletion_index_sync": "資源刪除索引同步",
    "test_pack_consistency.py::TestPackConsistency::test_pack_export_import_consistency": "批次匯入匯出一致性",
    "test_intent_extended_search.py::TestIntentExtendedSearch::test_intent_extended_search": "意圖擴充搜尋",
    "test_watch_update.py::TestWatchUpdate::test_watch_update": "定時監聽更新",
    "test_session_commit.py::TestSessionCommit::test_session_persistence_and_commit": "對話持久化與Commit",
    "test_long_context_recall.py::TestLongContextRecall::test_long_context_recall": "長程上下文召回",
    "test_session_delete_cleanup.py::TestSessionDeleteCleanup::test_session_delete_cleanup": "會話刪除與清理",
    "test_concurrent_write.py::TestConcurrentWrite::test_concurrent_write_conflict": "併發寫入衝突驗證",
    "test_account_isolation.py::TestAccountIsolation::test_processed_not_zero_after_resource_ops": "帳戶隔離完整性驗證",
    "test_account_isolation.py::TestAccountIsolation::test_consecutive_health_checks": "帳戶隔離連續健康檢查",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_txt_file": "TC-B01 TXT文本構建",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_markdown_file": "TC-B02 Markdown構建",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_empty_file": "TC-B15 空檔案構建",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_raw_content": "TC-B14 原始內容構建",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_pdf_file": "TC-B03 PDF構建",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_html_file": "TC-B04 HTML構建",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_docx_file": "TC-B05 DOCX構建",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_legacy_doc_file": "TC-B06 .doc構建",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_pptx_file": "TC-B07 PPTX構建",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_xlsx_file": "TC-B08 XLSX構建",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_epub_file": "TC-B09 EPUB構建",
    "test_build_archive_resources.py::TestBuildArchiveResources::test_build_zip_file": "TC-B10 ZIP構建",
    "test_build_archive_resources.py::TestBuildArchiveResources::test_build_directory": "TC-B11 目錄構建",
    "test_build_archive_resources.py::TestBuildArchiveResources::test_build_code_repository_url": "TC-B12 程式碼倉庫URL構建",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_svg": "TC-B13 圖片構建(SVG)",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_jpg": "TC-B13 圖片構建(JPG)",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_png": "TC-B13 圖片構建(PNG)",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_webp": "TC-B13 圖片構建(WebP)",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_audio_mp3": "TC-B14 音訊構建(MP3)",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_audio_wav": "TC-B14 音訊構建(WAV)",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_video_mp4": "TC-B15 影片構建(MP4)",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_repo": "TC-P01 GitHub倉庫構建",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_repo_with_branch": "TC-P02 GitHub分支構建",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_raw_file": "TC-P03 GitHub原始檔案構建",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_blob_page": "TC-P04 GitHub Blob頁構建",
    "test_build_platform_wikipedia.py::TestBuildPlatformWikipedia::test_build_wikipedia_page": "TC-P05 Wikipedia構建",
    "test_build_platform_arxiv.py::TestBuildPlatformArxiv::test_build_arxiv_pdf": "TC-P06 arXiv PDF構建",
    "test_build_platform_arxiv.py::TestBuildPlatformArxiv::test_build_arxiv_abstract_page": "TC-P07 arXiv摘要頁構建",
    "test_build_platform_general_web.py::TestBuildPlatformGeneralWeb::test_build_general_webpage": "TC-P10 通用網頁構建",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_remote_404": "TC-E01 遠端404不存在",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_remote_403": "TC-E02 遠端403禁止訪問",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_remote_500": "TC-E03 遠端500服務錯誤",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_http_to_https_redirect": "TC-E05 HTTP→HTTPS跳轉",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_multi_redirect": "TC-E06 多重跳轉",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_dns_resolve_failure": "TC-E08 DNS解析失敗",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_ssh_url_invalid_format": "TC-E09 SSH URL格式錯誤",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_duplicate_resource_no_to": "TC-E12 同名資源二次新增",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_incremental_update_with_to": "TC-E13 同to增量更新",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_unsupported_file_type": "TC-E15 不支援的檔案型別",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_corrupted_zip": "TC-E16 損壞的ZIP檔案",
    "test_build_uri_params_slow.py::TestBuildUriParamsSlow::test_build_with_to_param": "TC-E17 to引數指定URI",
    "test_build_uri_params_slow.py::TestBuildUriParamsSlow::test_build_with_parent_param": "TC-E18 parent引數指定父目錄",
    "test_build_uri_params_slow.py::TestBuildUriParamsSlow::test_build_non_resources_scope_rejected": "TC-E11 scope引數非resources拒絕",
}


TEST_CASE_APIS = {
    "test_add_resource.py::TestAddResource::test_add_resource_simple": "/api/v1/resources",
    "test_pack.py::TestPack::test_export_ovpack": "/api/v1/resources/pack",
    "test_wait_processed.py::TestWaitProcessed::test_wait_processed": "/api/v1/resources/wait",
    "test_fs_ls.py::TestFsLs::test_fs_ls_root": "/api/v1/fs/ls",
    "test_fs_mkdir.py::TestFsMkdir::test_fs_mkdir": "/api/v1/fs/mkdir",
    "test_fs_cp.py::TestFsCp::test_cp_file_preserves_source_and_content": "/api/v1/fs/cp",
    "test_fs_mv.py::TestFsMv::test_fs_mv": "/api/v1/fs/mv",
    "test_fs_read_write.py::TestFsReadWrite::test_fs_read": "/api/v1/fs/read",
    "test_fs_rm.py::TestFsRm::test_fs_rm": "/api/v1/fs/rm",
    "test_fs_stat.py::TestFsStat::test_fs_stat": "/api/v1/fs/stat",
    "test_fs_tree.py::TestFsTree::test_fs_tree": "/api/v1/fs/tree",
    "test_get_abstract.py::TestGetAbstract::test_get_abstract": "/api/v1/fs/abstract",
    "test_get_overview.py::TestGetOverview::test_get_overview": "/api/v1/fs/overview",
    "test_add_message.py::TestAddMessage::test_add_message": "/api/v1/sessions/messages",
    "test_create_session.py::TestCreateSession::test_create_session": "/api/v1/sessions",
    "test_delete_session.py::TestDeleteSession::test_delete_session": "/api/v1/sessions",
    "test_get_session.py::TestGetSession::test_get_session": "/api/v1/sessions",
    "test_list_sessions.py::TestListSessions::test_list_sessions": "/api/v1/sessions",
    "test_find.py::TestFind::test_find_basic": "/api/v1/search/find",
    "test_find.py::TestFind::test_find_with_different_query": "/api/v1/search/find",
    "test_search.py::TestSearch::test_basic_search": "/api/v1/search",
    "test_search.py::TestSearch::test_search_with_different_query": "/api/v1/search",
    "test_grep.py::TestGrep::test_grep_basic": "/api/v1/search/grep",
    "test_glob.py::TestGlob::test_glob_basic": "/api/v1/search/glob",
    "test_is_healthy.py::TestIsHealthy::test_is_healthy": "/api/v1/system/healthy",
    "test_observer.py::TestObserver::test_observer_queue": "/api/v1/system/observer",
    "test_observer.py::TestObserver::test_observer_vikingdb": "/api/v1/system/observer",
    "test_observer.py::TestObserver::test_observer_system": "/api/v1/system/observer",
    "test_system_status.py::TestSystemStatus::test_system_status": "/api/v1/system/status",
    "test_system_wait.py::TestSystemWait::test_system_wait": "/api/v1/system/wait",
    "test_admin_accounts.py::TestAdminAccounts::test_admin_list_accounts": "/api/v1/admin/accounts",
    "test_admin_accounts.py::TestAdminAccounts::test_admin_create_delete_account": "/api/v1/admin/accounts",
    "test_admin_regenerate_key.py::TestAdminRegenerateKey::test_admin_regenerate_key": "/api/v1/admin/keys",
    "test_admin_role.py::TestAdminRole::test_admin_set_role": "/api/v1/admin/roles",
    "test_admin_users.py::TestAdminUsers::test_admin_list_users": "/api/v1/admin/users",
    "test_admin_users.py::TestAdminUsers::test_admin_register_remove_user": "/api/v1/admin/users",
    "test_server_health_check.py::TestServerHealthCheck::test_server_health_check": "/health",
    "test_semantic_retrieval.py::TestSemanticRetrieval::test_semantic_retrieval_end_to_end": "/api/v1/resources,/api/v1/search/find",
    "test_resource_swap.py::TestResourceSwap::test_resource_incremental_update": "/api/v1/resources,/api/v1/search/find",
    "test_grep_validation.py::TestGrepValidation::test_grep_pattern_match": "/api/v1/resources,/api/v1/search/grep",
    "test_delete_sync.py::TestDeleteSync::test_resource_deletion_index_sync": "/api/v1/resources,/api/v1/fs/rm,/api/v1/search/find",
    "test_pack_consistency.py::TestPackConsistency::test_pack_export_import_consistency": "/api/v1/resources/pack/export,/api/v1/resources/pack/import",
    "test_intent_extended_search.py::TestIntentExtendedSearch::test_intent_extended_search": "/api/v1/sessions,/api/v1/search",
    "test_watch_update.py::TestWatchUpdate::test_watch_update": "/api/v1/resources,/api/v1/system/wait,/api/v1/search",
    "test_session_commit.py::TestSessionCommit::test_session_persistence_and_commit": "/api/v1/sessions,/api/v1/sessions/messages,/api/v1/sessions/commit",
    "test_long_context_recall.py::TestLongContextRecall::test_long_context_recall": "/api/v1/sessions/messages,/api/v1/sessions/commit,/api/v1/search",
    "test_session_delete_cleanup.py::TestSessionDeleteCleanup::test_session_delete_cleanup": "/api/v1/sessions (建立/獲取/刪除)",
    "test_concurrent_write.py::TestConcurrentWrite::test_concurrent_write_conflict": "/api/v1/resources (併發寫入)",
    "test_account_isolation.py::TestAccountIsolation::test_processed_not_zero_after_resource_ops": "/api/v1/resources,/api/v1/search,/api/v1/system/observer",
    "test_account_isolation.py::TestAccountIsolation::test_consecutive_health_checks": "/api/v1/system/healthy,/api/v1/system/observer",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_txt_file": "/api/v1/resources",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_markdown_file": "/api/v1/resources",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_empty_file": "/api/v1/resources",
    "test_build_text_resources_slow.py::TestBuildTextResourcesSlow::test_build_raw_content": "/api/v1/resources",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_pdf_file": "/api/v1/resources",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_html_file": "/api/v1/resources",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_docx_file": "/api/v1/resources",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_legacy_doc_file": "/api/v1/resources",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_pptx_file": "/api/v1/resources",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_xlsx_file": "/api/v1/resources",
    "test_build_document_resources_slow.py::TestBuildDocumentResourcesSlow::test_build_epub_file": "/api/v1/resources",
    "test_build_archive_resources.py::TestBuildArchiveResources::test_build_zip_file": "/api/v1/resources",
    "test_build_archive_resources.py::TestBuildArchiveResources::test_build_directory": "/api/v1/resources",
    "test_build_archive_resources.py::TestBuildArchiveResources::test_build_code_repository_url": "/api/v1/resources",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_svg": "/api/v1/resources",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_jpg": "/api/v1/resources",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_png": "/api/v1/resources",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_image_webp": "/api/v1/resources",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_audio_mp3": "/api/v1/resources",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_audio_wav": "/api/v1/resources",
    "test_build_media_resources_slow.py::TestBuildMediaResourcesSlow::test_build_video_mp4": "/api/v1/resources",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_repo": "/api/v1/resources",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_repo_with_branch": "/api/v1/resources",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_raw_file": "/api/v1/resources",
    "test_build_platform_github.py::TestBuildPlatformGithub::test_build_github_blob_page": "/api/v1/resources",
    "test_build_platform_wikipedia.py::TestBuildPlatformWikipedia::test_build_wikipedia_page": "/api/v1/resources",
    "test_build_platform_arxiv.py::TestBuildPlatformArxiv::test_build_arxiv_pdf": "/api/v1/resources",
    "test_build_platform_arxiv.py::TestBuildPlatformArxiv::test_build_arxiv_abstract_page": "/api/v1/resources",
    "test_build_platform_general_web.py::TestBuildPlatformGeneralWeb::test_build_general_webpage": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_remote_404": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_remote_403": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_remote_500": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_http_to_https_redirect": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_multi_redirect": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_dns_resolve_failure": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_ssh_url_invalid_format": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_duplicate_resource_no_to": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_incremental_update_with_to": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_unsupported_file_type": "/api/v1/resources",
    "test_build_error_handling_slow.py::TestBuildErrorHandlingSlow::test_error_corrupted_zip": "/api/v1/resources",
    "test_build_uri_params_slow.py::TestBuildUriParamsSlow::test_build_with_to_param": "/api/v1/resources",
    "test_build_uri_params_slow.py::TestBuildUriParamsSlow::test_build_with_parent_param": "/api/v1/resources",
    "test_build_uri_params_slow.py::TestBuildUriParamsSlow::test_build_non_resources_scope_rejected": "/api/v1/resources",
}


CATEGORY_NAMES = {
    "admin": "管理API",
    "filesystem": "檔案系統API",
    "health_check": "健康檢查",
    "resources": "資源管理API",
    "retrieval": "檢索API",
    "sessions": "會話管理API",
    "system": "系統管理API",
    "resources_retrieval": "P1 知識中樞場景",
    "scenarios": "場景級測試",
    "stability_error": "P3 運維與異常邊界",
}


def get_test_description(nodeid):
    for key, desc in TEST_CASE_DESCRIPTIONS.items():
        if key in nodeid:
            return desc
    return nodeid.split("::")[-1]


def get_test_api(nodeid):
    for key, api in TEST_CASE_APIS.items():
        if key in nodeid:
            return api
    return ""


def format_memory(bytes_value):
    if bytes_value is None:
        return ""

    if bytes_value < 1024:
        value = bytes_value
        unit = "B"
    elif bytes_value < 1024 * 1024:
        value = bytes_value / 1024
        unit = "KB"
    elif bytes_value < 1024 * 1024 * 1024:
        value = bytes_value / (1024 * 1024)
        unit = "MB"
    else:
        value = bytes_value / (1024 * 1024 * 1024)
        unit = "GB"

    return f"{value:.1f} {unit}"


def format_memory_delta(delta_bytes):
    if delta_bytes is None:
        return ""

    abs_bytes = abs(delta_bytes)
    if abs_bytes < 1024:
        value = abs_bytes
        unit = "B"
    elif abs_bytes < 1024 * 1024:
        value = abs_bytes / 1024
        unit = "KB"
    elif abs_bytes < 1024 * 1024 * 1024:
        value = abs_bytes / (1024 * 1024)
        unit = "MB"
    else:
        value = abs_bytes / (1024 * 1024 * 1024)
        unit = "GB"

    sign = "+" if delta_bytes > 0 else "" if delta_bytes == 0 else "-"
    return f"{sign}{value:.1f} {unit}"


def get_test_category(nodeid):
    parts = nodeid.split(os.sep)

    # 優先匹配更具體的路徑（倒序匹配）
    priority_categories = ["stability_error", "resources_retrieval", "filesystem", "sessions"]

    for part in parts:
        if part in priority_categories:
            # 特殊處理：將子目錄對映到正確的分類
            if part == "stability_error":
                return "P3 運維與異常邊界"
            elif part == "resources_retrieval":
                return "P1 知識中樞場景"
            elif part == "filesystem":
                return "檔案系統API"
            elif part == "sessions":
                return "會話管理API"

    # 如果沒有匹配到優先分類，則按原邏輯匹配
    for part in parts:
        if part in CATEGORY_NAMES:
            return CATEGORY_NAMES[part]

    return "其他"


def _extract_user_key(users, user_id):
    for user in users:
        if isinstance(user, dict) and user.get("user_id") == user_id:
            return user.get("api_key")
    return None


def _fallback_api_test_key(reason: str) -> str:
    if (
        Config.OPENVIKING_ROOT_API_KEY
        and Config.OPENVIKING_API_KEY == Config.OPENVIKING_ROOT_API_KEY
    ):
        raise RuntimeError(
            f"{reason}; refusing to fall back to the ROOT API key for tenant-scoped "
            "API tests. Bootstrap a user/admin key first, or run in trusted mode "
            "with explicit account/user identity headers."
        )
    print(f"{reason}, 使用配置的 API Key")
    return Config.OPENVIKING_API_KEY


def _extract_user_key_from_response(resp, user_id: str) -> str | None:
    if resp.status_code != 200:
        return None
    users = resp.json().get("result", [])
    return _extract_user_key(users, user_id)


def _retry_existing_user_key(
    root_client,
    account_id: str,
    user_id: str,
    *,
    reason: str,
) -> str | None:
    for attempt in range(3):
        resp = root_client.admin_list_users(account_id)
        user_key = _extract_user_key_from_response(resp, user_id)
        if user_key:
            print(f"{reason}; 複用測試使用者 {account_id}/{user_id}")
            return user_key
        if resp.status_code not in (200, 404):
            print(f"{reason}; 查詢使用者列表失敗({resp.status_code}): {resp.text[:200]}")
            return None
        time.sleep(0.2 * (attempt + 1))
    return None


def _ensure_api_test_user_key(root_client, account_id: str, user_id: str) -> str:
    resp = root_client.admin_list_users(account_id)
    if resp.status_code == 404:
        create_resp = root_client.admin_create_account(account_id, user_id)
        if create_resp.status_code in (200, 201):
            data = create_resp.json()
            user_key = data.get("result", {}).get("user_key")
            if user_key:
                print(f"已建立測試帳戶和使用者 {account_id}/{user_id}")
                return user_key
        elif create_resp.status_code == 409:
            user_key = _retry_existing_user_key(
                root_client,
                account_id,
                user_id,
                reason=f"測試帳戶/使用者併發建立衝突({create_resp.status_code})",
            )
            if user_key:
                return user_key
        print(f"建立測試帳戶失敗({create_resp.status_code}): {create_resp.text[:200]}")
        return _fallback_api_test_key("建立測試帳戶失敗")

    if resp.status_code != 200:
        return _fallback_api_test_key(f"無法查詢使用者列表({resp.status_code}): {resp.text[:200]}")

    users = resp.json().get("result", [])
    user_key = _extract_user_key(users, user_id)
    if user_key:
        print(f"複用測試使用者 {account_id}/{user_id}")
        return user_key

    user_exists = any(
        (isinstance(u, dict) and u.get("user_id") == user_id)
        or (isinstance(u, str) and u == user_id)
        for u in users
    )
    if not user_exists:
        reg_resp = root_client.admin_register_user(account_id, user_id, role="admin")
        if reg_resp.status_code in (200, 201):
            data = reg_resp.json()
            user_key = data.get("result", {}).get("user_key")
            if user_key:
                print(f"已註冊測試使用者 {account_id}/{user_id}")
                return user_key
        elif reg_resp.status_code == 409:
            user_key = _retry_existing_user_key(
                root_client,
                account_id,
                user_id,
                reason=f"測試使用者併發註冊衝突({reg_resp.status_code})",
            )
            if user_key:
                return user_key
        print(f"註冊測試使用者失敗({reg_resp.status_code}): {reg_resp.text[:200]}")
        return _fallback_api_test_key("註冊測試使用者失敗")

    role_resp = root_client.admin_set_role(account_id, user_id, "admin")
    if role_resp.status_code != 200:
        print(f"設定測試使用者角色失敗({role_resp.status_code}): {role_resp.text[:200]}")

    key_resp = root_client.admin_regenerate_key(account_id, user_id)
    if key_resp.status_code == 200:
        user_key = key_resp.json().get("result", {}).get("user_key")
        if user_key:
            print(f"已重新整理測試使用者 API Key {account_id}/{user_id}")
            return user_key

    print(f"重新整理測試使用者 API Key 失敗({key_resp.status_code}): {key_resp.text[:200]}")
    return _fallback_api_test_key("重新整理測試使用者 API Key 失敗")


@pytest.fixture(scope="session")
def api_client():
    account_id = Config.OPENVIKING_ACCOUNT
    user_id = Config.OPENVIKING_USER
    root_key = Config.OPENVIKING_ROOT_API_KEY
    root_client = OpenVikingAPIClient(
        server_url=Config.SERVER_URL,
        api_key=root_key,
        root_api_key=root_key,
    )

    try:
        api_key = _ensure_api_test_user_key(root_client, account_id, user_id)
    except Exception as e:
        print(f"使用者註冊檢查異常, 跳過: {e}")
        api_key = Config.OPENVIKING_API_KEY

    return OpenVikingAPIClient(
        server_url=Config.SERVER_URL,
        api_key=api_key,
        root_api_key=root_key,
    )


@pytest.fixture(scope="session", autouse=True)
def ensure_resources_dir(api_client):
    try:
        resp = api_client.fs_mkdir("viking://resources")
        if resp.status_code in (200, 409):
            print("viking://resources 目錄已就緒")
        else:
            stat_resp = api_client.fs_stat("viking://resources")
            if stat_resp.status_code == 200:
                print("viking://resources 目錄已存在")
            else:
                print(
                    f"警告: 無法確保 viking://resources 存在 (mkdir={resp.status_code}, stat={stat_resp.status_code})"
                )
    except Exception as e:
        print(f"警告: ensure_resources_dir 異常: {e}")


def pytest_collection_modifyitems(config, items):
    cache = config.cache
    lastfailed = cache.get("cache/lastfailed", {})

    def item_sort_key(item):
        is_failed = item.nodeid in lastfailed
        category = get_test_category(item.nodeid)
        return (0 if is_failed else 1, category, item.name)

    items.sort(key=item_sort_key)


def pytest_runtest_setup(item):
    process = psutil.Process()
    mem_info = process.memory_info()
    item._start_memory = mem_info.rss


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "call":
        category = get_test_category(item.nodeid)
        description = get_test_description(item.nodeid)
        report.category = category
        report.description = description
        report.nodeid = item.nodeid
        report.is_failed = report.failed

        if hasattr(item, "_start_memory"):
            process = psutil.Process()
            mem_info = process.memory_info()
            delta = mem_info.rss - item._start_memory
            report.memory_current = mem_info.rss
            report.memory_delta = delta

        # 為所有測試新增 cURL 和 Response 資訊
        for _fixture_name, fixture_value in item.funcargs.items():
            if hasattr(fixture_value, "to_curl"):
                curl = fixture_value.to_curl()
                if curl:
                    report.sections.append(("cURL Command", curl))

            # 新增 Response Body 顯示
            if hasattr(fixture_value, "last_response") and fixture_value.last_response:
                response = fixture_value.last_response
                if hasattr(response, "text"):
                    response_text = response.text
                    if response_text:
                        try:
                            import json

                            response_json = json.loads(response_text)
                            formatted_response = json.dumps(
                                response_json, indent=2, ensure_ascii=False
                            )
                            report.sections.append(
                                ("Response Body", f"<pre>{formatted_response}</pre>")
                            )
                        except Exception:
                            report.sections.append(("Response Body", f"<pre>{response_text}</pre>"))


def pytest_report_teststatus(report, config):
    if report.when == "call":
        category = getattr(report, "category", "其他")
        description = getattr(report, "description", "")

        return (report.outcome, f"{category} - {description}", "")


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_header(cells):
    cells.insert(2, "<th>分類</th>")
    cells.insert(3, "<th>描述</th>")
    cells.insert(4, "<th>API</th>")
    cells.insert(6, "<th>記憶體用量</th>")

    result = cells[0]
    test = cells[1]
    category = cells[2]
    description = cells[3]
    api = cells[4]
    duration = cells[5]
    memory = cells[6]

    cells.clear()
    cells.append(result)
    cells.append(category)
    cells.append(description)
    cells.append(api)
    cells.append(duration)
    cells.append(memory)
    cells.append(test)


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_row(report, cells):
    if hasattr(report, "nodeid"):
        category = get_test_category(report.nodeid)
        description = get_test_description(report.nodeid)
        api = get_test_api(report.nodeid)
        memory_current = getattr(report, "memory_current", None)
        memory_delta = getattr(report, "memory_delta", None)

        memory_current_str = format_memory(memory_current)
        memory_delta_str = format_memory_delta(memory_delta)

        if memory_current_str and memory_delta_str:
            memory_str = f"{memory_current_str} ({memory_delta_str})"
        elif memory_current_str:
            memory_str = memory_current_str
        else:
            memory_str = ""

        cells.insert(2, f"<td>{category}</td>")
        cells.insert(3, f"<td>{description}</td>")
        cells.insert(4, f"<td>{api}</td>")
        cells.insert(6, f"<td>{memory_str}</td>")

    result = cells[0]
    test = cells[1]
    category = cells[2]
    description = cells[3]
    api = cells[4]
    duration = cells[5]
    memory = cells[6]

    cells.clear()
    cells.append(result)
    cells.append(category)
    cells.append(description)
    cells.append(api)
    cells.append(duration)
    cells.append(memory)
    cells.append(test)


@pytest.hookimpl(optionalhook=True)
def pytest_html_report_title(report):
    report.title = "Business Data Platform API測試報告"


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_summary(prefix, summary, postfix):
    prefix.extend(
        [
            """
    <p><strong>Business Data Platform Version:</strong> 0.2.9</p>
    """
        ]
    )
    prefix.extend(
        [
            """
    <style>
        /* 隱藏時長描述 */
        .run-count {
            display: none !important;
        }

        /* 設定列寬度 */
        #results-table th:nth-child(1),
        #results-table td:nth-child(1) {
            width: 60px !important;
        }

        #results-table th:nth-child(2),
        #results-table td:nth-child(2) {
            width: 120px !important;
        }

        #results-table th:nth-child(3),
        #results-table td:nth-child(3) {
            width: 250px !important;
        }

        #results-table th:nth-child(4),
        #results-table td:nth-child(4) {
            width: 200px !important;
            font-family: monospace !important;
            font-size: 12px !important;
        }

        #results-table th:nth-child(5),
        #results-table td:nth-child(5) {
            width: 80px !important;
        }

        #results-table th:nth-child(6),
        #results-table td:nth-child(6) {
            width: 100px !important;
            text-align: right !important;
        }

        #results-table th:nth-child(7),
        #results-table td:nth-child(7) {
            width: 180px !important;
            max-width: 180px !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
        }
    </style>
    <script>
        function sortFailedFirst() {
            var table = document.getElementById('results-table');
            if (table) {
                var tbodies = table.querySelectorAll('tbody');
                tbodies.forEach(function(tbody) {
                    var rows = Array.from(tbody.querySelectorAll('tr.collapsible'));
                    if (rows.length > 0) {
                        var sortedRows = rows.sort(function(a, b) {
                            var aFailed = a.querySelector('.failed, .error') !== null ||
                                          (a.querySelector('.col-result') &&
                                           (a.querySelector('.col-result').textContent.includes('Failed') ||
                                            a.querySelector('.col-result').textContent.includes('Error')));
                            var bFailed = b.querySelector('.failed, .error') !== null ||
                                          (b.querySelector('.col-result') &&
                                           (b.querySelector('.col-result').textContent.includes('Failed') ||
                                            b.querySelector('.col-result').textContent.includes('Error')));
                            if (aFailed && !bFailed) return -1;
                            if (!aFailed && bFailed) return 1;
                            return 0;
                        });
                        sortedRows.forEach(function(row) {
                            tbody.insertBefore(row, tbody.firstChild);
                            if (row.nextElementSibling && row.nextElementSibling.classList.contains('extras-row')) {
                                tbody.insertBefore(row.nextElementSibling, tbody.firstChild.nextSibling);
                            }
                        });
                    }
                });
            }
        }

        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(sortFailedFirst, 100);
            setTimeout(sortFailedFirst, 500);
            setTimeout(sortFailedFirst, 1000);
        });
    </script>
    """
        ]
    )

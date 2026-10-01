"""
OpenViking FUSE 會話整合

提供與會話管理器的整合，自動在配置的 workspace/{session}/ 掛載 OpenViking
每個session直接在自己的workspace下管理內容
"""

from __future__ import annotations

import sys
import asyncio
import shutil
from pathlib import Path
from typing import Dict, Optional, Any

from loguru import logger

from vikingbot.utils.helpers import get_workspace_path

# 相對匯入同一包內的模組
from .mount import OpenVikingMount, MountConfig, MountScope
from .viking_fuse import mount_fuse, FUSEMountManager, FUSE_AVAILABLE


class SessionOpenVikingManager:
    """
    會話 OpenViking 管理器

    管理每個會話的 OpenViking 掛載，每個session直接在自己的workspace下管理
    """

    def __init__(self, base_workspace: Optional[Path] = None):
        """
        初始化管理器

        Args:
            base_workspace: 基礎工作區路徑
        """
        if base_workspace is None:
            base_workspace = get_workspace_path()

        self.base_workspace = base_workspace
        self.base_workspace.mkdir(parents=True, exist_ok=True)

        # 跟蹤每個會話的掛載
        self._session_mounts: Dict[str, Dict[str, Any]] = {}

        # FUSE 掛載管理器（如果可用）
        self._fuse_manager = FUSEMountManager() if FUSE_AVAILABLE else None

        logger.info(f"SessionOpenVikingManager initialized")
        logger.info(f"  Base workspace: {self.base_workspace}")
        logger.info(f"  FUSE available: {FUSE_AVAILABLE}")

    def get_session_workspace(self, session_key: str) -> Path:
        """
        獲取會話的工作區路徑

        Args:
            session_key: 會話鍵

        Returns:
            工作區路徑: {workspace}/.vikingbot/workspace/{session}/
        """
        safe_session_key = session_key.replace(":", "__")
        return self.base_workspace / safe_session_key

    def get_session_ov_data_path(self, session_key: str) -> Path:
        """
        獲取會話的 OpenViking 資料儲存路徑（在workspace內部）

        Args:
            session_key: 會話鍵

        Returns:
            資料儲存路徑: {workspace}/{session}/.ov_data/
        """
        return self.get_session_workspace(session_key) / ".ov_data"

    def mount_for_session(
        self, session_key: str, use_fuse: bool = True, background: bool = True
    ) -> bool:
        """
        為會話掛載 OpenViking

        Args:
            session_key: 會話鍵
            use_fuse: 是否使用 FUSE（如果可用）
            background: FUSE 是否在後臺執行

        Returns:
            是否成功
        """
        if session_key in self._session_mounts:
            logger.debug(f"Session {session_key} already mounted")
            return True

        session_workspace = self.get_session_workspace(session_key)
        ov_data_path = self.get_session_ov_data_path(session_key)

        # 確保目錄存在 - workspace本身就是掛載點
        session_workspace.mkdir(parents=True, exist_ok=True)
        ov_data_path.mkdir(parents=True, exist_ok=True)

        mount_info = {
            "session_key": session_key,
            "session_workspace": session_workspace,
            "ov_data_path": ov_data_path,
            "use_fuse": use_fuse and FUSE_AVAILABLE,
            "fuse_mount_id": None,
            "api_mount": None,
        }

        try:
            if use_fuse and FUSE_AVAILABLE and self._fuse_manager:
                # 使用 FUSE 掛載
                logger.info(f"Mounting OpenViking via FUSE for session {session_key}")
                logger.info(f"  Mount path: {session_workspace}")

                config = MountConfig(
                    mount_point=session_workspace,
                    openviking_data_path=ov_data_path,
                    session_id=session_key,
                    scope=MountScope.SESSION,
                    auto_init=True,
                    read_only=False,
                )

                # 為 FUSE 生成唯一的掛載 ID
                fuse_mount_id = f"session_{session_key.replace(':', '_')}"
                mount_info["fuse_mount_id"] = fuse_mount_id

                if background:
                    self._fuse_manager.mount(fuse_mount_id, config, background=True)
                else:
                    # 前臺模式需要單獨處理
                    mount_fuse(config, foreground=True)

                logger.info(f"✓ FUSE mounted for session {session_key}")

            else:
                # 使用 API 層掛載 - mount_point就是workspace本身
                logger.info(f"Mounting OpenViking via API for session {session_key}")
                logger.info(f"  Session workspace: {session_workspace}")

                config = MountConfig(
                    mount_point=session_workspace,
                    openviking_data_path=ov_data_path,
                    session_id=session_key,
                    scope=MountScope.SESSION,
                    auto_init=True,
                    read_only=False,
                )

                api_mount = OpenVikingMount(config)
                api_mount.initialize()
                mount_info["api_mount"] = api_mount

                logger.info(f"✓ API mounted for session {session_key}")

            self._session_mounts[session_key] = mount_info
            return True

        except Exception as e:
            logger.error(f"Failed to mount for session {session_key}: {e}")
            import traceback

            traceback.print_exc()
            return False

    def delete_session_workspace(self, session_key: str) -> bool:
        """
        刪除會話的workspace，同時清理掛載

        Args:
            session_key: 會話鍵

        Returns:
            是否成功
        """
        logger.info(f"Deleting session workspace and cleaning up mount: {session_key}")

        # 先解除安裝掛載
        unmount_success = self.unmount_for_session(session_key)

        # 刪除workspace目錄
        session_workspace = self.get_session_workspace(session_key)
        if session_workspace.exists():
            try:
                shutil.rmtree(session_workspace)
                logger.info(f"✓ Deleted session workspace: {session_workspace}")
                return unmount_success
            except Exception as e:
                logger.error(f"Failed to delete session workspace: {e}")
                return False

        return unmount_success

    def unmount_for_session(self, session_key: str) -> bool:
        """
        為會話解除安裝 OpenViking

        Args:
            session_key: 會話鍵

        Returns:
            是否成功
        """
        if session_key not in self._session_mounts:
            return True

        mount_info = self._session_mounts.pop(session_key)

        try:
            if mount_info.get("fuse_mount_id") and self._fuse_manager:
                logger.info(f"Unmounting FUSE for session {session_key}")
                self._fuse_manager.unmount(mount_info["fuse_mount_id"])

            if mount_info.get("api_mount"):
                logger.info(f"Closing API mount for session {session_key}")
                mount_info["api_mount"].close()

            logger.info(f"✓ Unmounted for session {session_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to unmount for session {session_key}: {e}")
            return False

    def is_mounted(self, session_key: str) -> bool:
        """檢查會話是否已掛載"""
        return session_key in self._session_mounts

    def is_workspace_exists(self, session_key: str) -> bool:
        """
        檢查會話的workspace是否還存在（防止系統外手動刪除）

        Args:
            session_key: 會話鍵

        Returns:
            workspace是否存在
        """
        workspace = self.get_session_workspace(session_key)
        return workspace.exists()

    def cleanup_orphaned_mounts(self) -> int:
        """
        清理孤立的掛載（workspace已被系統外刪除，但掛載還在記憶體中）

        Returns:
            清理的掛載數量
        """
        cleaned_count = 0
        session_keys = list(self._session_mounts.keys())

        for session_key in session_keys:
            if not self.is_workspace_exists(session_key):
                logger.warning(
                    f"Found orphaned mount for {session_key} - workspace deleted externally"
                )
                self.unmount_for_session(session_key)
                cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} orphaned mounts")

        return cleaned_count

    def get_api_mount(self, session_key: str) -> Optional[OpenVikingMount]:
        """
        獲取會話的 API 掛載物件（帶workspace存在性檢查）

        Args:
            session_key: 會話鍵

        Returns:
            OpenVikingMount 例項
        """
        if session_key not in self._session_mounts:
            return None

        # 檢查workspace是否還存在，不存在則清理
        if not self.is_workspace_exists(session_key):
            logger.warning(f"Workspace for {session_key} not found, cleaning up mount")
            self.unmount_for_session(session_key)
            return None

        mount_info = self._session_mounts[session_key]

        if mount_info.get("api_mount"):
            return mount_info["api_mount"]

        # 如果只有 FUSE，建立一個臨時的 API 掛載
        session_workspace = mount_info["session_workspace"]
        ov_data_path = mount_info["ov_data_path"]

        config = MountConfig(
            mount_point=session_workspace,
            openviking_data_path=ov_data_path,
            session_id=session_key,
            scope=MountScope.SESSION,
            auto_init=True,
            read_only=False,
        )

        api_mount = OpenVikingMount(config)
        api_mount.initialize()
        mount_info["api_mount"] = api_mount

        return api_mount

    def unmount_all(self) -> None:
        """解除安裝所有會話"""
        session_keys = list(self._session_mounts.keys())
        for session_key in session_keys:
            self.unmount_for_session(session_key)

    async def cleanup(self) -> None:
        """清理資源（包括孤立掛載）"""
        self.cleanup_orphaned_mounts()
        self.unmount_all()


# 全域單例
_global_ov_session_manager: Optional[SessionOpenVikingManager] = None


def get_session_ov_manager(base_workspace: Optional[Path] = None) -> SessionOpenVikingManager:
    """
    獲取全域會話 OpenViking 管理器

    Args:
        base_workspace: 基礎工作區路徑（僅首次呼叫有效）

    Returns:
        SessionOpenVikingManager 單例
    """
    global _global_ov_session_manager
    if _global_ov_session_manager is None:
        _global_ov_session_manager = SessionOpenVikingManager(base_workspace=base_workspace)
    return _global_ov_session_manager

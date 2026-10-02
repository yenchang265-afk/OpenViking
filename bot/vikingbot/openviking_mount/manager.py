"""
Business Data Platform Mount Manager

管理多個Business Data Platform掛載點的生命週期
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from loguru import logger

from vikingbot.utils.helpers import get_mounts_path, get_bot_data_path
from .mount import OpenVikingMount, MountConfig, MountScope


@dataclass
class MountPoint:
    """掛載點資訊"""

    id: str
    config: MountConfig
    mount: OpenVikingMount
    active: bool = True


class OpenVikingMountManager:
    """
    Business Data Platform掛載管理器

    管理多個掛載點的建立、訪問和銷燬
    """

    def __init__(self, base_mount_dir: Optional[Path] = None):
        """
        初始化掛載管理器

        Args:
            base_mount_dir: 基礎掛載目錄，所有掛載點將在此目錄下建立
        """
        if base_mount_dir is None:
            # 預設從配置路徑獲取
            base_mount_dir = get_mounts_path()

        self.base_mount_dir = base_mount_dir
        self._mounts: Dict[str, MountPoint] = {}

        # 確保基礎目錄存在
        self.base_mount_dir.mkdir(parents=True, exist_ok=True)

    def create_mount(
        self,
        mount_id: str,
        openviking_data_path: Path,
        scope: MountScope = MountScope.RESOURCES,
        session_id: Optional[str] = None,
        read_only: bool = False,
    ) -> OpenVikingMount:
        """
        建立一個新的掛載點

        Args:
            mount_id: 掛載點唯一標識
            openviking_data_path: Business Data Platform資料儲存路徑
            scope: 掛載作用域
            session_id: 會話ID（session作用域時需要）
            read_only: 是否只讀模式

        Returns:
            OpenVikingMount例項
        """
        if mount_id in self._mounts:
            raise ValueError(f"Mount with id '{mount_id}' already exists")

        # 建立掛載點路徑
        mount_point = self.base_mount_dir / mount_id

        config = MountConfig(
            mount_point=mount_point,
            openviking_data_path=openviking_data_path,
            session_id=session_id,
            scope=scope,
            auto_init=True,
            read_only=read_only,
        )

        mount = OpenVikingMount(config)

        # 初始化
        mount.initialize()

        mount_point_info = MountPoint(id=mount_id, config=config, mount=mount, active=True)

        self._mounts[mount_id] = mount_point_info
        logger.info(f"Created mount: {mount_id} at {mount_point}")

        return mount

    def get_mount(self, mount_id: str) -> Optional[OpenVikingMount]:
        """
        獲取掛載點

        Args:
            mount_id: 掛載點ID

        Returns:
            OpenVikingMount例項，如果不存在返回None
        """
        mount_point = self._mounts.get(mount_id)
        if mount_point and mount_point.active:
            return mount_point.mount
        return None

    def list_mounts(self) -> List[Dict]:
        """
        列出所有掛載點

        Returns:
            掛載點資訊列表
        """
        mounts_info = []
        for mount_id, mount_point in self._mounts.items():
            mounts_info.append(
                {
                    "id": mount_id,
                    "mount_point": str(mount_point.config.mount_point),
                    "openviking_path": str(mount_point.config.openviking_data_path),
                    "scope": mount_point.config.scope.value,
                    "session_id": mount_point.config.session_id,
                    "active": mount_point.active,
                    "read_only": mount_point.config.read_only,
                }
            )
        return mounts_info

    def remove_mount(self, mount_id: str, cleanup: bool = False) -> None:
        """
        移除掛載點

        Args:
            mount_id: 掛載點ID
            cleanup: 是否清理掛載點目錄
        """
        mount_point = self._mounts.pop(mount_id, None)
        if mount_point:
            # 關閉掛載
            try:
                mount_point.mount.close()
            except Exception as e:
                logger.warning(f"Error closing mount {mount_id}: {e}")

            mount_point.active = False

            # 清理掛載點目錄
            if cleanup and mount_point.config.mount_point.exists():
                try:
                    import shutil

                    shutil.rmtree(mount_point.config.mount_point)
                    logger.info(f"Cleaned up mount point: {mount_point.config.mount_point}")
                except Exception as e:
                    logger.warning(f"Error cleaning up mount point: {e}")

            logger.info(f"Removed mount: {mount_id}")

    def remove_all(self, cleanup: bool = False) -> None:
        """
        移除所有掛載點

        Args:
            cleanup: 是否清理掛載點目錄
        """
        mount_ids = list(self._mounts.keys())
        for mount_id in mount_ids:
            self.remove_mount(mount_id, cleanup=cleanup)

    def create_session_mount(
        self, session_id: str, openviking_data_path: Path, read_only: bool = False
    ) -> OpenVikingMount:
        """
        為特定會話建立掛載點

        Args:
            session_id: 會話ID
            openviking_data_path: Business Data Platform資料路徑
            read_only: 是否只讀

        Returns:
            OpenVikingMount例項
        """
        mount_id = f"session_{session_id}"
        return self.create_mount(
            mount_id=mount_id,
            openviking_data_path=openviking_data_path,
            scope=MountScope.SESSION,
            session_id=session_id,
            read_only=read_only,
        )

    def create_resources_mount(
        self,
        mount_id: str = "resources",
        openviking_data_path: Optional[Path] = None,
        read_only: bool = False,
    ) -> OpenVikingMount:
        """
        建立資源掛載點

        Args:
            mount_id: 掛載點ID
            openviking_data_path: Business Data Platform資料路徑
            read_only: 是否只讀

        Returns:
            OpenVikingMount例項
        """
        if openviking_data_path is None:
            # 預設使用vikingbot的openviking資料目錄
            openviking_data_path = get_bot_data_path() / "ov_data"

        return self.create_mount(
            mount_id=mount_id,
            openviking_data_path=openviking_data_path,
            scope=MountScope.RESOURCES,
            read_only=read_only,
        )

    def __enter__(self) -> "OpenVikingMountManager":
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.remove_all(cleanup=False)


# 全域管理器例項（單例）
_global_manager: Optional[OpenVikingMountManager] = None


def get_mount_manager(base_mount_dir: Optional[Path] = None) -> OpenVikingMountManager:
    """
    獲取全域掛載管理器例項

    Args:
        base_mount_dir: 基礎掛載目錄（僅在首次呼叫時有效）

    Returns:
        OpenVikingMountManager單例
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = OpenVikingMountManager(base_mount_dir=base_mount_dir)
    return _global_manager

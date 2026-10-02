"""
OpenViking Filesystem Mount Module

這個模組將OpenViking的虛擬檔案系統掛載到本地檔案系統路徑，
讓使用者可以像操作普通檔案一樣操作OpenViking上的資料。
"""

from typing import TYPE_CHECKING

from .mount import OpenVikingMount, MountScope, MountConfig, FileInfo
from .manager import OpenVikingMountManager, MountPoint, get_mount_manager
from .session_integration import SessionOpenVikingManager, get_session_ov_manager

__all__ = [
    "OpenVikingMount",
    "MountScope",
    "MountConfig",
    "FileInfo",
    "OpenVikingMountManager",
    "MountPoint",
    "get_mount_manager",
    "OpenVikingFUSE",
    "mount_fuse",
    "FUSEMountManager",
    "FUSE_AVAILABLE",
    "SessionOpenVikingManager",
    "get_session_ov_manager",
]

if TYPE_CHECKING:
    from .viking_fuse import OpenVikingFUSE, mount_fuse, FUSEMountManager, FUSE_AVAILABLE


def __getattr__(name: str):
    if name in ("OpenVikingFUSE", "mount_fuse", "FUSEMountManager", "FUSE_AVAILABLE"):
        from .viking_fuse import OpenVikingFUSE, mount_fuse, FUSEMountManager, FUSE_AVAILABLE

        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

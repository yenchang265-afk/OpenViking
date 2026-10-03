"""
OpenViking FUSE 檔案系統

實現真正的 FUSE 檔案系統掛載，允許使用標準檔案系統 API（os、pathlib 等）
直接操作 OpenViking 資料。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# 新增OpenViking專案到路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .mount import MountConfig, OpenVikingMount

# 嘗試匯入fusepy
try:
    from fuse import FUSE, FuseOSError, Operations

    FUSE_AVAILABLE = True
except (ImportError, OSError):
    FUSE_AVAILABLE = False
    # 建立佔位符
    Operations = object
    FUSE = None
    FuseOSError = Exception


# 只有當 FUSE 可用時才定義完整的實現
if FUSE_AVAILABLE:
    import errno
    import os
    import stat
    from datetime import datetime

    class OpenVikingFUSE(Operations):
        """
        OpenViking FUSE 操作類

        實現 FUSE 檔案系統操作，將 OpenViking 的虛擬檔案系統
        暴露為標準的 POSIX 檔案系統。
        """

        def __init__(self, mount: OpenVikingMount):
            """
            初始化 FUSE 操作

            Args:
                mount: OpenVikingMount 例項
            """
            self.mount = mount
            self._fd = 0
            self._file_handles: Dict[int, str] = {}  # fd -> uri
            self._file_contents: Dict[str, str] = {}  # uri -> content (for write cache)

            if not mount._initialized and mount.config.auto_init:
                mount.initialize()

        def _path_to_uri(self, path: str) -> str:
            """
            將 FUSE 路徑轉換為 OpenViking URI

            Args:
                path: FUSE 路徑 (如 /resources/foo)

            Returns:
                OpenViking URI
            """
            if path == "/":
                path = ""

            path = path.lstrip("/")

            if not path:
                return self.mount._get_scope_root_uri()

            return f"viking://{path}"

        def getattr(self, path: str, fh: int = None) -> Dict[str, Any]:
            """
            獲取檔案/目錄屬性

            Args:
                path: 檔案路徑
                fh: 文件描述符

            Returns:
                屬性字典
            """
            logger.debug(f"getattr: {path}")

            now = datetime.now().timestamp()

            if path == "/":
                return {
                    "st_mode": stat.S_IFDIR | 0o755,
                    "st_nlink": 2,
                    "st_uid": os.getuid(),
                    "st_gid": os.getgid(),
                    "st_size": 4096,
                    "st_atime": now,
                    "st_mtime": now,
                    "st_ctime": now,
                }

            try:
                parent_path = str(Path(path).parent) if Path(path).parent != Path(".") else "/"
                parent_uri = self._path_to_uri(parent_path)
                name = Path(path).name

                items = self.mount._client.ls(parent_uri)

                for item in items:
                    if isinstance(item, dict):
                        item_name = item.get("name", "")
                        is_dir = item.get("isDir", False)
                        size = item.get("size", 0)
                    else:
                        item_name = str(item)
                        is_dir = False
                        size = 0

                    if item_name == name:
                        mode = stat.S_IFDIR | 0o755 if is_dir else stat.S_IFREG | 0o644
                        return {
                            "st_mode": mode,
                            "st_nlink": 1,
                            "st_uid": os.getuid(),
                            "st_gid": os.getgid(),
                            "st_size": size,
                            "st_atime": now,
                            "st_mtime": now,
                            "st_ctime": now,
                        }
            except Exception:
                pass

            return {
                "st_mode": stat.S_IFDIR | 0o755,
                "st_nlink": 2,
                "st_uid": os.getuid(),
                "st_gid": os.getgid(),
                "st_size": 4096,
                "st_atime": now,
                "st_mtime": now,
                "st_ctime": now,
            }

        def readdir(self, path: str, fh: int) -> list:
            """
            讀取目錄內容

            Args:
                path: 目錄路徑
                fh: 文件描述符

            Returns:
                目錄項列表
            """
            logger.debug(f"readdir: {path}")

            try:
                uri = self._path_to_uri(path)
                logger.debug(f"Listing directory URI: {uri}")

                items = self.mount._client.ls(uri)
                entries = [".", ".."]

                for item in items:
                    if isinstance(item, dict):
                        name = item.get("name", "")
                    else:
                        name = str(item)

                    if name:
                        entries.append(name)

                return entries
            except Exception as e:
                logger.warning(f"readdir error: {e}")
                return [".", ".."]

        def open(self, path: str, flags: int) -> int:
            """
            開啟檔案

            Args:
                path: 檔案路徑
                flags: 開啟標誌

            Returns:
                文件描述符
            """
            logger.debug(f"open: {path} (flags={flags})")

            if (flags & os.O_WRONLY or flags & os.O_RDWR) and self.mount.config.read_only:
                raise FuseOSError(errno.EROFS)

            uri = self._path_to_uri(path)

            self._fd += 1
            fd = self._fd
            self._file_handles[fd] = uri

            if not (flags & os.O_WRONLY):
                try:
                    logger.debug(f"Reading file URI: {uri}")
                    content = self.mount._client.read(uri)
                    self._file_contents[uri] = content
                except Exception as e:
                    logger.warning(f"Failed to pre-read {path}: {e}")

            return fd

        def read(self, path: str, size: int, offset: int, fh: int) -> bytes:
            """
            讀取檔案內容

            Args:
                path: 檔案路徑
                size: 讀取大小
                offset: 偏移量
                fh: 文件描述符

            Returns:
                讀取的位元組
            """
            logger.debug(f"read: {path} (size={size}, offset={offset})")

            uri = self._file_handles.get(fh)
            if not uri:
                raise FuseOSError(errno.EBADF)

            if uri in self._file_contents:
                content = self._file_contents[uri]
            else:
                try:
                    logger.debug(f"Reading file URI: {uri}")
                    content = self.mount._client.read(uri)
                    self._file_contents[uri] = content
                except Exception as e:
                    logger.error(f"read error: {e}")
                    raise FuseOSError(errno.EIO)

            content_bytes = content.encode("utf-8")
            return content_bytes[offset : offset + size]

        def write(self, path: str, data: bytes, offset: int, fh: int) -> int:
            """
            寫入檔案內容

            Args:
                path: 檔案路徑
                data: 要寫入的資料
                offset: 偏移量
                fh: 文件描述符

            Returns:
                寫入的位元組數
            """
            logger.debug(f"write: {path} (size={len(data)}, offset={offset})")

            if self.mount.config.read_only:
                raise FuseOSError(errno.EROFS)

            uri = self._file_handles.get(fh)
            if not uri:
                raise FuseOSError(errno.EBADF)

            if uri not in self._file_contents:
                self._file_contents[uri] = ""

            current_content = self._file_contents[uri]
            current_bytes = current_content.encode("utf-8")

            new_bytes = current_bytes[:offset] + data + current_bytes[offset + len(data) :]
            self._file_contents[uri] = new_bytes.decode("utf-8")

            return len(data)

        def release(self, path: str, fh: int) -> None:
            """
            關閉檔案

            Args:
                path: 檔案路徑
                fh: 文件描述符
            """
            logger.debug(f"release: {path}")

            uri = self._file_handles.pop(fh, None)

            if uri and uri in self._file_contents:
                logger.warning(f"File {path} was modified but Business Data Platform direct write is limited")

        def mkdir(self, path: str, mode: int) -> None:
            """
            建立目錄

            Args:
                path: 目錄路徑
                mode: 許可權模式
            """
            logger.debug(f"mkdir: {path}")

            if self.mount.config.read_only:
                raise FuseOSError(errno.EROFS)

            try:
                self.mount.mkdir(path)
            except Exception as e:
                logger.error(f"mkdir error: {e}")
                raise FuseOSError(errno.EIO)

        def rmdir(self, path: str) -> None:
            """
            刪除目錄

            Args:
                path: 目錄路徑
            """
            logger.debug(f"rmdir: {path}")

            if self.mount.config.read_only:
                raise FuseOSError(errno.EROFS)

            try:
                self.mount.delete(path, recursive=False)
            except Exception as e:
                logger.error(f"rmdir error: {e}")
                raise FuseOSError(errno.EIO)

        def unlink(self, path: str) -> None:
            """
            刪除檔案

            Args:
                path: 檔案路徑
            """
            logger.debug(f"unlink: {path}")

            if self.mount.config.read_only:
                raise FuseOSError(errno.EROFS)

            try:
                self.mount.delete(path, recursive=False)
            except Exception as e:
                logger.error(f"unlink error: {e}")
                raise FuseOSError(errno.EIO)

        def truncate(self, path: str, length: int, fh: int = None) -> None:
            """
            截斷檔案

            Args:
                path: 檔案路徑
                length: 截斷長度
                fh: 文件描述符
            """
            logger.debug(f"truncate: {path} (length={length})")

            if self.mount.config.read_only:
                raise FuseOSError(errno.EROFS)

            uri = self._path_to_uri(path)

            if uri in self._file_contents:
                content = self._file_contents[uri]
                content_bytes = content.encode("utf-8")[:length]
                self._file_contents[uri] = content_bytes.decode("utf-8")

        def utimens(self, path: str, times: tuple = None) -> None:
            """
            更新檔案時間戳

            Args:
                path: 檔案路徑
                times: (atime, mtime) 元組
            """
            logger.debug(f"utimens: {path}")

    def mount_fuse(
        config: MountConfig, foreground: bool = False, allow_other: bool = False
    ) -> None:
        """
        掛載 OpenViking FUSE 檔案系統

        Args:
            config: 掛載配置
            foreground: 是否在前臺執行
            allow_other: 是否允許其他使用者訪問
        """
        mount = OpenVikingMount(config)
        operations = OpenVikingFUSE(mount)

        fuse_opts = {}
        if allow_other:
            fuse_opts["allow_other"] = True

        logger.info(f"Mounting Business Data Platform FUSE at: {config.mount_point}")
        logger.info(f"  Scope: {config.scope.value}")
        logger.info(f"  Read-only: {config.read_only}")
        logger.info("  Press Ctrl+C to unmount")

        try:
            FUSE(
                operations,
                str(config.mount_point),
                foreground=foreground,
                nothreads=True,
                **fuse_opts,
            )
        except KeyboardInterrupt:
            logger.info("Unmounting...")
        finally:
            mount.close()
            logger.info("Unmounted")

    class FUSEMountManager:
        """
        FUSE 掛載管理器

        管理 FUSE 掛載程序的生命週期
        """

        def __init__(self):
            self._mounts: Dict[str, Any] = {}

        def mount(self, mount_id: str, config: MountConfig, background: bool = True) -> None:
            """
            掛載 FUSE 檔案系統

            Args:
                mount_id: 掛載 ID
                config: 掛載配置
                background: 是否在後臺執行
            """
            if background:
                import multiprocessing

                def _mount_worker():
                    mount_fuse(config, foreground=True)

                process = multiprocessing.Process(target=_mount_worker, daemon=True)
                process.start()
                self._mounts[mount_id] = process
                logger.info(f"Started FUSE mount {mount_id} in background (PID: {process.pid})")
            else:
                mount_fuse(config, foreground=True)

        def unmount(self, mount_id: str) -> None:
            """
            解除安裝 FUSE 檔案系統

            Args:
                mount_id: 掛載 ID
            """
            if mount_id in self._mounts:
                process = self._mounts.pop(mount_id)
                process.terminate()
                process.join(timeout=5)
                logger.info(f"Unmounted {mount_id}")

        def unmount_all(self) -> None:
            """解除安裝所有 FUSE 檔案系統"""
            for mount_id in list(self._mounts.keys()):
                self.unmount(mount_id)

else:
    # FUSE 不可用時的佔位符
    OpenVikingFUSE = None

    def mount_fuse(*args, **kwargs):
        raise ImportError(
            "fusepy and libfuse are required. Install with: uv pip install fusepy>=3.0.1 and install libfuse system package"
        )

    class FUSEMountManager:
        """FUSE 掛載管理器（佔位符）"""

        def __init__(self):
            self._mounts: Dict[str, Any] = {}

        def mount(self, *args, **kwargs):
            raise ImportError("fusepy and libfuse are required")

        def unmount(self, *args, **kwargs):
            pass

        def unmount_all(self):
            pass

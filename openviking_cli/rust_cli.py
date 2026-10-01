"""ov 命令的極簡 Python 包裝器

設計原則：
1. 職責單一：僅負責查詢二進位制並 execv
2. 無網路依賴：不實現下載功能
3. 極簡程式碼：儘可能減少啟動開銷
4. 快速失敗：找不到立即提示使用者

效能說明：
- Python 虛擬機器啟動 + 匯入基礎模組：約 30-50ms
- 一旦 execv 執行，後續為純 Rust 二進位制，零開銷

Rust CLI 獨立釋出能力完全保留，使用者可通過以下方式獲取：
- 官方安裝指令碼（零開銷）
- GitHub Releases 手動下載（零開銷）
- cargo install（零開銷）
- 包管理器（未來）
"""

import os
import subprocess
import sys
from pathlib import Path
from shutil import which


def _exec_binary(binary: str, argv: list[str]) -> None:
    """Execute a binary, replacing the current process on Unix.

    On Windows, ``os.execv`` does not truly replace the process — CPython's
    MSVC implementation spawns a child process instead.  This breaks console
    handle inheritance and prevents the Rust TUI from receiving keyboard
    input (see #587).  We use ``subprocess.call`` on Windows to work around
    this.
    """
    if sys.platform == "win32":
        sys.exit(subprocess.call([binary] + argv))
    else:
        os.execv(binary, [binary] + argv)


def main():
    """
    極簡入口點：查詢 ov 二進位制並執行

    按優先順序查詢：
    0. Python-native 子命令（doctor）
    1. ./target/release/ov（開發環境）
    2. Wheel 自帶：{package_dir}/openviking/bin/ov
    3. PATH 查詢：系統全域安裝的 ov
    """
    # 0. Python-native subcommands (no Rust binary needed)
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        from openviking_cli.doctor import main as doctor_main

        sys.exit(doctor_main())
    # 1. 檢查開發環境（僅在直接執行指令碼時有效）
    try:
        # __file__ is openviking_cli/rust_cli.py, so parent is openviking_cli directory
        dev_binary = Path(__file__).parent.parent / "target" / "release" / "ov"
        if dev_binary.exists() and os.access(dev_binary, os.X_OK):
            _exec_binary(str(dev_binary), sys.argv[1:])
    except Exception:
        pass

    # 2. 檢查 Wheel 自帶（不匯入 openviking，避免額外開銷）
    try:
        # __file__ is openviking_cli/rust_cli.py, so parent is openviking_cli directory
        package_dir = Path(__file__).parent.parent / "openviking"
        package_bin = package_dir / "bin"
        for binary_name in ["ov", "ov.exe"]:
            binary = package_bin / binary_name
            if binary.exists() and os.access(binary, os.X_OK):
                _exec_binary(str(binary), sys.argv[1:])
    except Exception:
        pass

    # 3. 檢查 PATH，但跳過當前 Python 入口點
    path_binary = which("ov")
    if path_binary:
        try:
            candidate_path = Path(path_binary).resolve()
            current_path = Path(sys.argv[0])
            if not current_path.is_absolute():
                current_path = Path(which(sys.argv[0]) or current_path)
            current_path = current_path.resolve()
        except OSError:
            pass
        else:
            if candidate_path != current_path:
                _exec_binary(path_binary, sys.argv[1:])

    # 都找不到，提示使用者
    print(
        """錯誤: 未找到 ov 二進位制檔案。

        請選擇以下方式之一安裝：

        1. 使用預構建 wheel（推薦）：
   pip install openviking --upgrade --force-reinstall

        2. 使用 npm 安裝原生 CLI 包（零 Python 開銷）：
   npm i -g @openviking/cli

        3. 從 GitHub Releases 下載（零 Python 開銷）：
   https://github.com/volcengine/OpenViking/releases

        4. 從原始碼構建（零 Python 開銷）：
   cargo install --git https://github.com/volcengine/OpenViking ov_cli""",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

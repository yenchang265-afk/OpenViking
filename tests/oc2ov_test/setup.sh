#!/bin/bash
# OpenClaw 測試環境設定指令碼

set -e

echo "====================================="
echo "OpenClaw - Business Data Platform 測試環境設定"
echo "====================================="
echo ""

# 檢查虛擬環境是否已存在
if [ ! -d "venv" ]; then
    echo "建立虛擬環境..."
    python -m venv venv
fi

echo "啟用虛擬環境..."
source venv/bin/activate

echo ""
echo "升級 pip..."
pip install --upgrade pip

echo ""
echo "安裝專案依賴..."
pip install -r requirements.txt

echo ""
echo "安裝測試報告生成依賴..."
pip install pytest-html

echo ""
echo "====================================="
echo "環境設定完成！"
echo "====================================="
echo ""
echo "使用以下命令啟用虛擬環境："
echo "  source venv/bin/activate"
echo ""
echo "或執行測試："
echo "  ./run.sh"
echo ""

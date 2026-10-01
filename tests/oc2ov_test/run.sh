#!/bin/bash
# 執行測試指令碼

set -e

# 檢查是否在虛擬環境中
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "啟用虛擬環境..."
    source venv/bin/activate
fi

echo "====================================="
echo "執行 OpenClaw 自動化測試"
echo "====================================="
echo ""

# 檢查引數
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "用法: $0 [選項]"
    echo ""
    echo "選項:"
    echo "  -h, --help          顯示幫助資訊"
    echo "  -a, --all           執行全部測試（預設）"
    echo "  -p, --p0            僅執行 P0 級測試"
    echo "  -c, --crud          僅執行 CRUD 操作測試"
    echo "  -x, --complex       僅運行復雜場景測試"
    echo "  -v, --verbose       詳細輸出模式"
    echo "  -r, --report        生成 HTML 測試報告"
    echo ""
    exit 0
fi

# 預設選項
VERBOSE=""
REPORT=""
TEST_TYPE=""

# 解析引數
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -r|--report)
            REPORT="--html=reports/test_report.html --self-contained-html"
            shift
            ;;
        -a|--all)
            TEST_TYPE=""
            shift
            ;;
        -p|--p0)
            TEST_TYPE="tests/p0/"
            shift
            ;;
        -c|--crud)
            TEST_TYPE="tests/crud/"
            shift
            ;;
        -x|--complex)
            TEST_TYPE="tests/complex/"
            shift
            ;;
        *)
            echo "未知選項: $1"
            echo "使用 -h 檢視幫助"
            exit 1
            ;;
    esac
done

# 確保報告目錄存在
mkdir -p reports logs

# 執行測試
if [ -n "$TEST_TYPE" ]; then
    echo "執行 $TEST_TYPE 目錄下的測試..."
    pytest $TEST_TYPE $VERBOSE $REPORT
else
    echo "執行 pytest 測試檔案..."
    pytest test_pytest.py $VERBOSE $REPORT
fi

echo ""
echo "====================================="
echo "測試完成"
echo "====================================="
if [ -n "$REPORT" ]; then
    echo "測試報告已生成: reports/test_report.html"
    echo "使用 'open reports/test_report.html' 檢視報告"
fi
echo ""

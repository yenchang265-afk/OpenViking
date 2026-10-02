#!/bin/bash

set -e

: '
OpenClaw 完整評估流程指令碼

用法:
  ./run_full_eval.sh                      # 只匯入 Business Data Platform (所有 samples)
  ./run_full_eval.sh --with-claw-import   # 同時匯入 Business Data Platform 和 OpenClaw (所有 samples)
  ./run_full_eval.sh --skip-import        # 跳過匯入步驟 (所有 samples)
  ./run_full_eval.sh --sample 0           # 只處理第 0 個 sample
  ./run_full_eval.sh --sample 1 --with-claw-import  # 只處理第 1 個 sample，同時匯入 OpenClaw
  ./run_full_eval.sh --force-ingest       # 強制重新匯入所有資料
'

# 基於指令碼所在目錄計算資料檔案路徑
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT_FILE="$SCRIPT_DIR/../data/locomo10.json"
RESULT_DIR="$SCRIPT_DIR/result"
OUTPUT_CSV="$RESULT_DIR/qa_results.csv"
GATEWAY_TOKEN="90f2d2dc2f7b4d50cb943d3d3345e667bb3e9bcb7ec3a1fb"


# 解析引數
SKIP_IMPORT=false
WITH_CLAW_IMPORT=false
FORCE_INGEST=false
SAMPLE_IDX=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-import)
            SKIP_IMPORT=true
            shift
            ;;
        --with-claw-import)
            WITH_CLAW_IMPORT=true
            shift
            ;;
        --force-ingest)
            FORCE_INGEST=true
            shift
            ;;
        --sample)
            if [ -z "$2" ] || [[ "$2" == --* ]]; then
                echo "錯誤: --sample 需要一個引數 (sample index, 0-based)"
                exit 1
            fi
            SAMPLE_IDX="$2"
            shift 2
            ;;
        *)
            echo "警告: 未知引數 $1"
            shift
            ;;
    esac
done

# 構建 sample 引數
SAMPLE_ARG=""
if [ -n "$SAMPLE_IDX" ]; then
    SAMPLE_ARG="--sample $SAMPLE_IDX"
    # 如果指定了 sample，修改輸出檔名以避免覆蓋
    OUTPUT_CSV="$RESULT_DIR/qa_results_sample${SAMPLE_IDX}.csv"
fi

# 構建 force-ingest 引數
FORCE_INGEST_ARG=""
if [ "$FORCE_INGEST" = true ]; then
    FORCE_INGEST_ARG="--force-ingest"
fi

# 確保結果目錄存在
mkdir -p "$RESULT_DIR"

# Step 1: 匯入資料
if [ "$SKIP_IMPORT" = false ]; then
    if [ "$WITH_CLAW_IMPORT" = true ]; then
        echo "[1/5] 匯入資料到 Business Data Platform 和 OpenClaw..."

        # 後臺執行 Business Data Platform 匯入
        python "$SCRIPT_DIR/import_to_ov.py" --no-user-id --input "$INPUT_FILE" $FORCE_INGEST_ARG $SAMPLE_ARG > "$RESULT_DIR/import_ov.log" 2>&1 &
        PID_OV=$!

        # 後臺執行 OpenClaw 匯入
        python "$SCRIPT_DIR/eval.py" ingest "$INPUT_FILE" $FORCE_INGEST_ARG --token "$GATEWAY_TOKEN" $SAMPLE_ARG > "$RESULT_DIR/import_claw.log" 2>&1 &
        PID_CLAW=$!

        # 等待兩個匯入任務完成
        wait $PID_OV $PID_CLAW
    else
        echo "[1/5] 匯入資料到 Business Data Platform..."
        python "$SCRIPT_DIR/import_to_ov.py" --no-user-id --input "$INPUT_FILE" $FORCE_INGEST_ARG $SAMPLE_ARG
    fi

else
    echo "[1/5] 跳過匯入資料..."
fi

# Step 2: 執行 QA 模型（預設輸出到 result/qa_results.csv）
echo "[2/5] 執行 QA 評估..."
python "$SCRIPT_DIR/eval.py" qa "$INPUT_FILE" --token "$GATEWAY_TOKEN" $SAMPLE_ARG --parallel 15 --output "${OUTPUT_CSV%.csv}"

# Step 3: 裁判打分
echo "[3/5] 裁判打分..."
python "$SCRIPT_DIR/judge.py" --input "$OUTPUT_CSV" --parallel 40

# Step 4: 計算結果
echo "[4/5] 計算結果..."
python "$SCRIPT_DIR/stat_judge_result.py" --input "$OUTPUT_CSV"

echo "[5/5] 完成!"
echo "結果檔案: $OUTPUT_CSV"

#!/bin/bash
#
# 從舊版 memory-openviking 外掛升級到新版 openviking 的前置清理指令碼
#
# 用法：
#   bash cleanup-legacy-openviking.sh
#   bash cleanup-legacy-openviking.sh --workdir ~/.openclaw-second  # 指定 OpenClaw 目錄
#
set -euo pipefail

# --- 引數解析 ---
OPENCLAW_DIR="${HOME}/.openclaw"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workdir) OPENCLAW_DIR="$2"; shift 2 ;;
        -h|--help)
            echo "用法：$0 [--workdir <openclaw目錄>]"
            exit 0 ;;
        *) echo "未知引數：$1"; exit 1 ;;
    esac
done

CONFIG_FILE="${OPENCLAW_DIR}/openclaw.json"
LEGACY_PLUGIN_ID="memory-openviking"
BAK_SUFFIX=".pre-openviking-upgrade.bak"

# --- 顏色輸出 ---
info()  { printf '\033[0;32m[INFO] \033[0m%s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN] \033[0m%s\n' "$*"; }
error() { printf '\033[0;31m[ERROR]\033[0m%s\n' "$*"; }

# --- 前置檢查 ---
if ! command -v openclaw &>/dev/null; then
    error "未找到 openclaw 命令，請先安裝 OpenClaw"
    exit 1
fi

if [ ! -d "${OPENCLAW_DIR}" ]; then
    error "未找到 OpenClaw 目錄：${OPENCLAW_DIR}"
    error "如果使用了非預設安裝路徑，請通過 --workdir 引數指定："
    error "  bash $0 --workdir /your/openclaw/dir"
    exit 1
fi

if [ ! -f "${CONFIG_FILE}" ]; then
    error "未找到 OpenClaw 配置文件：${CONFIG_FILE}"
    if [ "${OPENCLAW_DIR}" = "${HOME}/.openclaw" ]; then
        error "請確認 OpenClaw 已安裝並初始化（openclaw onboard）"
        error "如果使用了非預設安裝路徑，請通過 --workdir 引數指定："
        error "  bash $0 --workdir /your/openclaw/dir"
    else
        error "請確認該目錄下存在有效的 OpenClaw 配置"
    fi
    exit 1
fi

info "OpenClaw 目錄：${OPENCLAW_DIR}"
info "配置文件：${CONFIG_FILE}"
echo ""

# ============================================================
# Step 1: 停止 OpenClaw gateway
# ============================================================
info "Step 1: 停止 OpenClaw gateway..."
if openclaw gateway stop 2>/dev/null; then
    info "gateway 已停止"
else
    warn "gateway 可能未在執行，繼續..."
fi
echo ""

# ============================================================
# Step 2: 備份配置檔案和舊版外掛目錄
# ============================================================
info "Step 2: 備份舊版配置..."

cp "${CONFIG_FILE}" "${CONFIG_FILE}${BAK_SUFFIX}"
info "配置已備份至 ${CONFIG_FILE}${BAK_SUFFIX}"

LEGACY_PLUGIN_DIR="${OPENCLAW_DIR}/extensions/${LEGACY_PLUGIN_ID}"
if [ -d "${LEGACY_PLUGIN_DIR}" ]; then
    DISABLED_DIR="${OPENCLAW_DIR}/disabled-extensions"
    mkdir -p "${DISABLED_DIR}"
    mv "${LEGACY_PLUGIN_DIR}" "${DISABLED_DIR}/${LEGACY_PLUGIN_ID}-upgrade-backup"
    info "外掛目錄已移至 ${DISABLED_DIR}/${LEGACY_PLUGIN_ID}-upgrade-backup"
else
    warn "未找到舊版外掛目錄 ${LEGACY_PLUGIN_DIR}，跳過"
fi
echo ""

# ============================================================
# Step 3: 清理 openclaw.json 中的舊版外掛配置
#
# 注意：openclaw config 命令無法處理帶連字元的 key（如 memory-openviking），
# 也不支援按值刪除陣列元素，因此全部改用 Node.js 直接操作 JSON 檔案，
# 確保解析正確、不破壞 JSON 結構。Node.js 為 OpenClaw 執行時依賴，必定可用。
# ============================================================
info "Step 3: 清理 openclaw.json 中的舊版外掛配置..."

if ! command -v node &>/dev/null; then
    error "未找到 node 命令，無法自動清理配置"
    error "請手動編輯 ${CONFIG_FILE}，完成以下操作："
    error "  1. 從 plugins.allow 中刪除 \"${LEGACY_PLUGIN_ID}\""
    error "  2. 從 plugins.load.paths 中刪除包含 ${LEGACY_PLUGIN_ID} 的路徑"
    error "  3. 刪除 plugins.entries.${LEGACY_PLUGIN_ID} 整個物件"
    error "  4. 將 plugins.slots.memory 改為 \"none\""
    exit 1
fi

node -e "
const fs = require('fs');
const file = process.argv[1];
const pluginId = process.argv[2];

let cfg;
try {
  cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
} catch (e) {
  console.error('JSON 解析失敗：' + e.message);
  process.exit(1);
}

const plugins = cfg.plugins;
if (!plugins) {
  console.log('未找到 plugins 欄位，跳過');
  process.exit(0);
}

// 從 allow 陣列移除舊外掛 ID
if (Array.isArray(plugins.allow)) {
  plugins.allow = plugins.allow.filter(x => x !== pluginId);
}

// 從 load.paths 移除包含舊外掛 ID 的路徑
if (Array.isArray(plugins.load?.paths)) {
  plugins.load.paths = plugins.load.paths.filter(x => !x.includes(pluginId));
}

// 刪除 entries[pluginId]（整個物件）
if (plugins.entries && pluginId in plugins.entries) {
  delete plugins.entries[pluginId];
}

// 將 slots.memory 改為 'none'（僅當其值為舊外掛 ID 時）
if (plugins.slots?.memory === pluginId) {
  plugins.slots.memory = 'none';
}

fs.writeFileSync(file, JSON.stringify(cfg, null, 2) + '\n');
" "${CONFIG_FILE}" "${LEGACY_PLUGIN_ID}"

info "已從 plugins.allow 中移除 \"${LEGACY_PLUGIN_ID}\""
info "已從 plugins.load.paths 中移除舊版路徑"
info "已刪除 plugins.entries.${LEGACY_PLUGIN_ID}"
info "已將 plugins.slots.memory 設為 none"
echo ""

# ============================================================
# 完成
# ============================================================
info "✓ 前置清理完成"
info ""
info "下一步：安裝新版 openviking 外掛"
info "  npm install -g openclaw-openviking-setup-helper && ov-install"
info ""
info "如需回滾，恢復備份："
info "  openclaw gateway stop"
info "  cp ${CONFIG_FILE}${BAK_SUFFIX} ${CONFIG_FILE}"
info "  mv ${OPENCLAW_DIR}/disabled-extensions/${LEGACY_PLUGIN_ID}-upgrade-backup \\"
info "     ${OPENCLAW_DIR}/extensions/${LEGACY_PLUGIN_ID}"

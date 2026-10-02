#!/bin/bash
set -e

# 使用環境變數替換配置模板
envsubst < /etc/openviking/ov.conf.template > /etc/openviking/ov.conf

echo "Generated configuration:"
cat /etc/openviking/ov.conf

# 啟動OpenViking服務
exec openviking server start

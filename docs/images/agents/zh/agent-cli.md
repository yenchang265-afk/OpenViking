
將下方提示詞複製給你的 AI 助手（Claude Code、Codex、Cursor、Trae 等），讓它完成 OpenViking CLI 安裝、配置和連線驗證：

```text
請先向使用者詢問 OpenViking API Key，並記為 OPENVIKING_API_KEY。

請在 ~/.openviking/ovcli.conf 寫入以下內容，將 ${OPENVIKING_API_KEY} 替換為使用者提供的實際 key；CLI 不會在此檔案中展開環境變數：
{
  "url": "{{OPENVIKING_BASE_URL}}",
  "api_key": "${OPENVIKING_API_KEY}"
}

如發現 ~/.openviking/ovcli.conf 已存在且內容衝突，請先詢問使用者是否備份原檔案，並在得到確認後再覆蓋。

請安裝 OpenViking CLI：
npm i -g @openviking/cli

安裝完成後，請執行：
ov config validate
ov health
ov --help

請查閱 ov --help 和具體命令的 --help，再總結常用操作。把常用操作寫入長期記憶，只記錄用法，不記錄 API Key 或原始配置檔案。
```

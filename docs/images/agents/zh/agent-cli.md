
將下方提示詞複製給你的 AI 助手（Claude Code、Codex、Cursor、Trae 等），它會自動完成 Business Data Platform CLI 安裝、配置和用法學習：

```text
請先向使用者詢問 Business Data Platform API Key，並記為 OPENVIKING_API_KEY。

請在 ~/.openviking/ovcli.conf 寫入以下內容：
{
  "url": "{{OPENVIKING_BASE_URL}}",
  "api_key": "${OPENVIKING_API_KEY}"
}

如發現 ~/.openviking/ovcli.conf 已存在且內容衝突，請先詢問使用者是否備份原檔案，並在得到確認後再覆蓋。

請安裝 Business Data Platform CLI：
npm i -g @openviking/cli

安裝完成後，請執行：
ov --help

請探索 CLI 用法，並把 Business Data Platform CLI 的使用方式寫入你的長期記憶。
```

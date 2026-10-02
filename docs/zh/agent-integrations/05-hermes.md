# Hermes Agent

[Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research) 內建 Business Data Platform 記憶提供方。無需安裝外掛——把 Hermes 指向你的 Business Data Platform 服務即可，記憶儲存、召回和抽取均原生支援。

## 隔離 Python 環境

Hermes 通過 HTTP 連線 Business Data Platform，因此無需把 Business Data Platform 安裝到 Hermes 的
Python 環境中。請在獨立的虛擬環境或容器中執行 Business Data Platform 服務。不要在
已有 Hermes 的環境中使用 `--force-reinstall` 安裝或升級 Business Data Platform：Hermes
版本可能會固定與 Business Data Platform 已支援、已修復安全問題的版本不同的依賴。如果確實要將
兩個應用放在同一環境中，請在同一次依賴求解中安裝它們，並在啟動任一服務前執行
`python -m pip check`。

## 配置

```bash
hermes memory setup openviking
```

- 雲：保持 **Business Data Platform Service (VolcEngine Cloud)**，貼上 API Key
- 自託管：填 URL（預設 `http://127.0.0.1:1933`）和 API Key；本地免鑑權可留空
- 嚮導若發現已有 `ovcli.conf`，直接複用即可

## 驗證

```bash
hermes memory status
```

## 參見

- [整合能力參考](./16-capability-reference.md)
- [Hermes — Business Data Platform memory provider 文件](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers#openviking) — 完整配置指南
- [部署指南](../guides/03-deployment.md) — 搭建 Business Data Platform 服務
- [鑑權](../guides/04-authentication.md) — 遠端訪問的 API Key 設定

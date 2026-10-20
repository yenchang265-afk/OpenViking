const connect = {
  description:
    '把模型客戶端的請求地址換成閘道器，再用閘道器金鑰認證。選擇你使用的客戶端，檢視它的具體配置。',
  fullGuide: '完整指南',
  address: {
    title: '閘道器地址',
    description:
      '客戶端把模型請求發到這裡，而不是直接發給服務商。Anthropic 客戶端直接使用這個地址，OpenAI 相容客戶端要在末尾加上 `/v1`。',
    anthropic: 'Claude Code 和 Anthropic SDK',
    openai: 'OpenAI 相容的客戶端和 SDK',
    loopback: {
      title: '只有閘道器所在的機器能使用這個地址',
      embedded:
        '其他機器上的客戶端連不上它。請在 `ov.conf` 中把 `gateway.public_url` 設為它們能訪問的地址（不帶 `/gateway`），然後重啟服務。',
      standalone:
        '其他機器上的客戶端連不上它。請把 `gateway.conf` 中的 `public_url` 或環境變數 `OPENVIKING_GATEWAY_PUBLIC_URL` 設為它們能訪問的地址（不帶 `/gateway`），然後重啟閘道器。',
    },
    notPublic: {
      title: '客戶端可能連不上這個地址',
      embedded:
        '這是瀏覽器開啟 Studio 時使用的地址。請在 `ov.conf` 中把 `gateway.public_url` 設為客戶端應該使用的地址（不帶 `/gateway`），然後重啟服務。',
      standalone:
        '這是瀏覽器開啟 Studio 時使用的地址。請把 `gateway.conf` 中的 `public_url` 或環境變數 `OPENVIKING_GATEWAY_PUBLIC_URL` 設為客戶端應該使用的地址（不帶 `/gateway`），然後重啟閘道器。',
    },
    keys: '客戶端用閘道器金鑰（`ovgw_…`）認證，代替服務商的 API Key。',
    manageKeys: '管理金鑰',
  },
  guide: {
    title: '配置客戶端',
    description: '選擇你使用的客戶端。示例中已經填好了這個閘道器的地址。',
    clients: '客戶端',
    protocol: '使用的協議',
    upstreams: '可用上游：{{names}}',
    upstreamsMore: '可用上游：{{names}}，另有 {{count}} 個',
    separator: '、',
    noUpstream: {
      title: '請先新增 {{protocols}} 上游',
      description:
        '已啟用的上游都不支援 {{protocols}}。閘道器只會把請求轉發給協議相同的上游。',
      descriptionPicked:
        '已啟用的上游都不支援 {{protocols}}。閘道器只會把請求轉發給協議相同的上游。請新增一個，或者換一種協議配置客戶端。',
      action: '新增上游',
      hint: '還沒有適用於這個客戶端的已啟用上游',
      protocolHint: '還沒有使用這種協議的已啟用上游',
    },
    placeholders: '替換佔位符',
    goodToKnow: '注意事項',
  },
  placeholders: {
    key: '閘道器金鑰，可在“金鑰”標籤頁簽發',
    model: '上游接受的模型名',
    session: '在同一段對話內保持不變的 ID，例如聊天 ID',
  },
  snippets: {
    env: '環境變數',
    config: '配置',
    key: '終端',
    settings: '客戶端設定',
    python: 'Python',
    curl: '終端',
    connection: '連線',
    headers: '請求頭',
    endpoints: '地址',
  },
  clients: {
    'claude-code': {
      name: 'Claude Code',
      intro: 'Anthropic 推出的命令列程式設計 Agent。',
      steps: {
        env: '在啟動 Claude Code 的終端裡設定這些環境變數，也可以把它們寫進 shell 配置檔案。',
        start: '照常啟動 `claude`。',
      },
      identity:
        'Claude Code 會發送自己的會話 ID，閘道器能自動識別每段對話，`--resume` 之後也一樣。',
      notes: {
        address: '地址不要帶 `/v1`，Claude Code 會自己補全路徑。',
        hints:
          '`CLAUDE_CODE_GATEWAY_HINT_HEADERS=1` 讓 Claude Code 給子 Agent、上下文壓縮和後臺請求加上標記，閘道器就不會為這些請求搜尋記憶，也不會把它們當成對話輪次儲存。',
        models:
          '上游必須接受 Claude Code 請求的模型名：把上游的模型列表留空、列出這些名稱，或者用模型別名對映到服務商的模型。',
        subscription:
          'Claude 訂閱登入無法通過閘道器使用，請為上游配置服務商的 API Key。',
      },
    },
    codex: {
      name: 'Codex CLI',
      intro:
        'OpenAI 推出的命令列程式設計 Agent。它的每個請求都帶完整歷史，正好滿足閘道器對 Responses 的要求。',
      steps: {
        config:
          '在 `~/.codex/config.toml` 中把閘道器新增為服務商。開頭兩行頂層設定必須寫在所有 `[section]` 之前。',
        key: '在執行 Codex 的環境裡設定閘道器金鑰。',
        start: '照常啟動 `codex`。',
      },
      identity:
        'Codex 會發送自己的會話 ID，閘道器能自動識別每段對話，`codex resume` 之後也一樣。',
      notes: {
        websocket:
          'Codex 會先嚐試 WebSocket 連線，閘道器拒絕後它會自動改用 HTTP。',
        metadata:
          '遇到不認識的模型名，Codex 可能提示缺少模型後設資料，這個提示不影響請求。',
        login:
          'Codex 不能用 ChatGPT 帳號登入閘道器。想用 ChatGPT 訂閱，可以把 CLIProxyAPI 新增為上游（OpenAI Codex 團隊認可這種用法）；否則請為上游配置服務商的 API Key。',
      },
    },
    chat: {
      name: '聊天客戶端和 SDK',
      intro: '支援 OpenAI Chat Completions API 的客戶端和 SDK 都能接入。',
      steps: {
        settings: '在客戶端填寫 OpenAI 相容服務商的地方填入這些值。',
        python: '在程式碼中把 OpenAI SDK 指向閘道器。',
        curl: '也可以在終端裡發一個測試請求。',
      },
      identity:
        '傳送 `X-OpenViking-Session` 請求頭，取值在同一段對話內保持不變，例如聊天 ID。不傳送時，閘道器根據歷史匹配對話，重試或內容相同的對話可能被當成新對話。',
      notes: {
        streaming:
          '流式呼叫時，用 `stream_options.include_usage` 請求返回用量。否則流式回覆不帶 Token 數，請求日誌無法顯示用量，閘道器也無法判斷長對話是否快要撐滿上下文視窗。',
        otherApis:
          '另外兩種 API 的 SDK 用法相同：Anthropic SDK 使用不帶 `/v1` 的地址；Responses API 的每個請求都要帶完整歷史並設定 `store: false`。上游使用的 API 必須和 SDK 一致。',
        models:
          '客戶端獲取模型列表時，閘道器返回金鑰所繫結上游上配置的模型和別名。',
      },
    },
    'open-webui': {
      name: 'Open WebUI',
      intro: '可自託管的聊天介面。把閘道器新增為一個 OpenAI 相容連線即可。',
      steps: {
        connection:
          '在 Admin Panel → Settings → Connections 中新增一個 OpenAI 相容連線，填入這個地址和金鑰。',
        headers:
          '給這個連線新增以下自定義請求頭，這樣每個聊天都是一段獨立的對話，後臺任務也能被識別出來。',
        env: '在 Open WebUI 的環境變數中設定這一項。這樣從附件中檢索到的內容會放進 system 訊息，而不是臨時改寫你的訊息，對話歷史在請求之間就能保持穩定。',
      },
      identity: '`X-OpenViking-Session` 請求頭讓每個聊天各自成為一段對話。',
      notes: {
        sharedMemory:
          '一個連線金鑰只對應一位記憶歸屬者：通過這個連線聊天的所有 Open WebUI 使用者，讀寫的都是金鑰背後那位 Business Data Platform 使用者的記憶。',
        tasks:
          '閘道器能識別生成標題和摘要的請求。如果請求日誌把其他後臺任務（標籤、追問建議）標成“{{kind}}”，就把 Open WebUI 的任務模型改成不經過閘道器的連線。',
      },
    },
    opencode: {
      name: 'OpenCode',
      intro:
        '開源的命令列程式設計 Agent。把閘道器新增為一個自定義服務商，協議選你的上游使用的那種。',
      steps: {
        config:
          '在 `~/.config/opencode/opencode.json` 中新增這個服務商，與已有的設定合併。',
        key: '在執行 OpenCode 的環境裡設定閘道器金鑰。',
        start: '啟動 OpenCode，選擇 `openviking/<model>`。',
      },
      identity: 'OpenCode 會發送自己的會話 ID，閘道器能自動識別每段對話。',
      notes: {
        plugin:
          '如果同時安裝了 OpenViking 的 OpenCode 外掛，閘道器會讓出這些對話。',
      },
    },
    pi: {
      name: 'pi',
      intro:
        '命令列程式設計 Agent。把閘道器新增為一個自定義服務商，協議選你的上游使用的那種。',
      steps: {
        config:
          '在 pi 的模型配置 `~/.pi/agent/models.json` 中新增這個服務商。`apiKey` 從環境變數讀取閘道器金鑰，開頭的 `$` 不能省，否則 pi 會把變數名本身當作金鑰發出去。',
        key: '啟動 pi 前先匯出這個環境變數。',
      },
      identity:
        '除非 pi 傳送了“{{section}}”中列出的某個請求頭，否則閘道器會根據歷史匹配它的對話。',
      notes: {
        extension:
          '如果 pi 自己的 OpenViking 擴充處於啟用狀態，閘道器會讓出這些對話，兩者選一個使用即可。',
      },
    },
    dsh: {
      name: 'DSH',
      intro:
        'DeepSeek 推出的開源 Agent 框架 DeepSeek Harness。把閘道器新增為一個自定義模型服務商，協議選你的上游使用的那種。',
      steps: {
        config:
          '在 profile 配置中新增這個服務商，`dsh web` 使用的 profile 是 `web`。如果檔案裡已經有 `llm-pi-ai` 條目，就把 `openviking` 加到它的 `providers` 下，不要再寫第二個條目。',
        key: '在執行 DSH 的環境裡設定閘道器金鑰。`apiKeyEnv` 填的就是這個環境變數名。',
        start:
          '啟動 `dsh web`，在模型選擇器中選擇 `openviking` 服務商下的 `<model>`。',
      },
      identity:
        '除非 DSH 傳送了“{{section}}”中列出的某個請求頭，否則閘道器會根據歷史匹配它的對話。',
      notes: {
        webUi:
          '也可以在 Web UI 的 Settings → Models → Add model provider → Custom model API 中新增，它寫入的是同一個檔案。',
        oneProtocol:
          'DSH 的一個服務商只使用一種協議。要通過多種協議使用閘道器，就為每種協議各宣告一個服務商。',
        plugin:
          '如果同一個 profile 裡裝了 OpenViking 的 DSH 外掛，閘道器會讓出這些對話。',
      },
    },
    ark: {
      name: '火山方舟與 BytePlus 方舟 SDK',
      intro:
        '已經配置好火山方舟或 BytePlus 方舟的客戶端和 SDK，只需換掉地址和金鑰。閘道器既接受方舟自己的路徑，也接受標準的 `/v1` 路徑。',
      steps: {
        endpoints:
          '把方舟地址換成對應的閘道器地址，把方舟 API Key 換成閘道器金鑰。',
        python: '使用火山方舟 Python SDK：',
      },
      identity:
        '和其他聊天客戶端一樣，為每段對話傳送 `X-OpenViking-Session` 請求頭。',
      notes: {
        routing:
          '路徑只決定客戶端使用哪種 API。請求仍然發往金鑰繫結的、使用這種 API 並提供該模型的上游，通常是服務商選為“火山方舟”或“BytePlus 方舟（海外站）”的上游。',
      },
    },
  },
  identity: {
    title: '閘道器如何識別對話',
    description:
      '記憶按對話召回和儲存。閘道器按以下順序，取第一個出現的請求頭作為對話 ID：',
    fallback:
      '這些請求頭都沒有時，閘道器檢視歷史中最近一條助手回覆。如果恰好有一段之前的對話產生過這條回覆，請求就併入那段對話；否則開始一段新對話。重試、重新生成的回答和內容相同的對話存在歧義，所以只要客戶端允許設定請求頭，就傳送 `X-OpenViking-Session`。',
    scope:
      '對話歸屬於金鑰背後的 Business Data Platform 使用者，並且按 API 分開。同一使用者的兩個閘道器金鑰如果傳送相同的 ID，會共享同一段對話。',
  },
  passthrough: {
    title: '客戶端自帶服務商 API Key',
    description:
      '如果上游的憑證方式是“{{mode}}”，每個請求還要在這個請求頭裡帶上客戶端自己的服務商 API Key。閘道器金鑰仍然填在客戶端原本填寫 API Key 的位置。',
    note: '閘道器把這個金鑰轉交給服務商，不會記錄它。',
    upstreams: '需要它的上游：{{names}}',
    none: '目前沒有上游需要它。',
  },
  plugin: {
    title: '同時在用 OpenViking 外掛？',
    description:
      '如果某段對話已經通過 OpenViking 外掛獲得記憶，閘道器會讓出這段對話：不召回、不儲存，也不提供 Business Data Platform 工具，避免重複補充記憶。其他對話不受影響。',
    detection:
      '閘道器根據外掛注入訊息的記憶塊識別外掛。整合方也可以通過這個請求頭主動宣告。',
    mcp: '只接入 Business Data Platform MCP 工具不算外掛：閘道器照常召回和儲存記憶，只是不再提供自己的 Business Data Platform 工具。',
    restart:
      '這個狀態會持續到對話結束。要重新使用閘道器的記憶，請在不啟用外掛的情況下開始一段新對話。',
  },
}

export default connect

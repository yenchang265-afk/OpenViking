const upstreams = {
  import: {
    action: '從 Business Data Platform 匯入',
    useSettings: '使用 Business Data Platform 的模型配置',
    hint: '即服務端的 VLM 配置',
    running: '匯入中…',
    summary_one: '已匯入或更新 {{count}} 個上游。',
    summary_other: '已匯入或更新 {{count}} 個上游。',
    nothing: 'Business Data Platform 的模型配置裡沒有可匯入的憑證。',
    needsConfirmation:
      '以下 Coding Plan 上游會攔截所有請求，確認套餐允許通過閘道器使用後才能啟用：',
    skipped_one: '{{count}} 個憑證未匯入：',
    skipped_other: '{{count}} 個憑證未匯入：',
    confirm: '去確認',
    dismiss: '關閉',
    repeat:
      '再次匯入會按 Business Data Platform 的配置更新地址和憑證，不會重複建立；你改過的啟用狀態、優先順序和模型設定會保留。',
    reasons: {
      invalid_configuration: '模型配置無效，請檢查服務端配置後重新匯入。',
      openai_codex:
        'Codex 的 OAuth 憑證會定期重新整理，閘道器無法長期使用。請手動新增上游。',
      azure:
        'Azure OpenAI 需要 api-version 引數，閘道器暫不支援。請手動新增上游。',
      litellm_no_api_base:
        '這個 LiteLLM 憑證沒有填寫 api_base，閘道器無法確定地址。請在服務端配置裡補上 api_base 後重新匯入。',
      litellm_unsupported_route:
        '這個 LiteLLM 路由不是 OpenAI 相容協議，閘道器無法直接轉發。請手動新增上游。',
      unknown: '無法匯入這個憑證，請檢查服務端模型配置。',
    },
  },
  readOnly: {
    empty: '等待閘道器管理員新增上游。',
    managedKey: 'API Key 由閘道器管理員保管。',
    clientKey: 'API Key 由每個客戶端自帶。',
    codingAllowed: 'Coding Plan，閘道器管理員已允許',
    codingBlocked: 'Coding Plan，請求已攔截',
  },
  description:
    '閘道器把請求轉發給這些模型服務商。每個上游只支援一種協議，閘道器不做協議轉換。',
  add: '新增上游',
  loadFailed: '無法載入上游',
  empty: {
    title: '還沒有上游',
    description:
      '新增客戶端要訪問的模型服務商，例如 OpenAI、Anthropic、DeepSeek 或火山方舟。簽發閘道器金鑰時，再為每個金鑰選擇可以使用的上游。',
  },
  columns: {
    name: '名稱',
    protocol: '協議',
    provider: '服務商',
    models: '模型',
    credentials: '憑證',
    priority: '優先順序',
    usedBy: '使用情況',
    enabled: '啟用',
    actions: '操作',
  },
  models: {
    any: '不限模型',
    more: '+{{count}}',
    aliases_one: '{{count}} 個別名',
    aliases_other: '{{count}} 個別名',
  },
  credentials: {
    keyMissing: '缺少 API Key',
    keyMissingHint:
      '沒有儲存 API Key，發往這個上游的請求都會失敗。請在編輯頁填寫金鑰。',
    blocked: '請求被拒絕',
    blockedHint:
      '這個上游標記為使用 Coding Plan 或訂閱金鑰，閘道器會拒絕所有發往它的請求。',
  },
  usedBy_one: '{{count}} 個金鑰',
  usedBy_other: '{{count}} 個金鑰',
  notUsed: '未被使用',
  toggle: {
    enable: '啟用 {{name}}',
    disable: '停用 {{name}}',
  },
  test: {
    action: '測試',
    connection: '測試連線',
    running: '測試中…',
    hint: '用已儲存的金鑰和請求頭向服務商請求模型列表。它只驗證地址和金鑰是否可用，不檢查模型配置，也不傳送對話請求。',
    savedOnly: '測試的是已儲存的設定。要測試改動後的設定，請先儲存。',
    passthrough:
      '這個上游由客戶端自帶 API Key，閘道器沒有可用於測試的 API Key。',
    noKey: '請先填寫 API Key。',
    result: {
      unverified: '可達，金鑰未驗證 · {{status}}',
      ok: '可連通 · {{status}}',
      failed: '失敗 · {{status}}',
      unreachable: '無法連線',
      error: '無法測試',
    },
    explain: {
      ok: '服務商接受了金鑰，並返回了模型列表。',
      auth: '服務商拒絕了 API Key 或某個請求頭。',
      rateLimited: '地址可達，但服務商限制了請求頻率，金鑰尚未驗證。',
      notFound: '地址可達，但服務商不提供模型列表，API Key 尚未驗證。',
      status: '服務商返回了 HTTP {{status}}。',
      unreachable:
        '閘道器在 10 秒內沒有連上服務商。請檢查 Base URL，以及閘道器到服務商之間的網路。',
    },
  },
  delete: {
    disable: '停用',
    disableHint: '也可以先停用它，停用後這些金鑰會立即請求不到這個上游。',
    inUse_one: '仍有 {{count}} 個金鑰在使用它。',
    inUse_other: '仍有 {{count}} 個金鑰在使用它。',
    action: '刪除',
    blocked_one: '有 {{count}} 個金鑰在使用，請先吊銷',
    blocked_other: '有 {{count}} 個金鑰在使用，請先吊銷',
    title: '刪除“{{name}}”？',
    description:
      '上游會連同儲存的 API Key 和請求頭一起刪除。還有金鑰在使用它時無法刪除。',
    confirm: '刪除上游',
  },
  toast: {
    created: '已新增“{{name}}”',
    saved: '已儲存“{{name}}”',
    deleted: '已刪除“{{name}}”',
  },
  editor: {
    back: '上游',
    newTitle: '新建上游',
    newDescription:
      '接入一個模型服務商的介面。簽發閘道器金鑰時，再選擇每個金鑰可以使用哪些上游。',
    editDescription: '儲存後立即生效。優先順序隻影響之後新開始的對話。',
    notFound: {
      title: '這個上游已不存在',
      description: '它可能已被刪除。請返回列表檢視現有的上游。',
    },
    missing: '還需填寫或修正：{{fields}}',
    separator: '、',
    create: '新增上游',
  },
  sections: {
    endpoint: {
      title: '介面',
      description: '閘道器把請求發到哪裡，以及使用哪種協議。',
    },
    credentials: {
      title: '憑證',
      description: '閘道器用什麼憑證訪問服務商。',
    },
    models: {
      title: '模型',
      description: '這個上游提供哪些模型名，以及它們在服務商那邊叫什麼。',
    },
    routing: {
      title: '路由',
      description: '有多個上游可選時，閘道器如何選擇。',
    },
  },
  form: {
    name: {
      label: '名稱',
      placeholder: '例如：OpenAI 生產環境',
      description: '在 Studio 中和簽發閘道器金鑰時顯示。',
    },
    protocol: {
      label: '協議',
      description: '客戶端必須用同一種協議呼叫閘道器，閘道器不做協議轉換。',
      unsupported: '{{vendor}} 不提供這種介面',
      options: {
        anthropic: 'Claude Code 和 Anthropic SDK',
        chat: '大多數聊天客戶端和 SDK',
        responses: 'Codex CLI，只支援攜帶完整歷史的請求',
      },
    },
    vendor: {
      label: '服務商',
      description:
        '選定服務商後，下方只能選它提供的協議。列表裡沒有的服務商，以及 LiteLLM 這類相容代理，請選“通用”。',
      hints: {
        deepseek:
          '請求帶工具時，DeepSeek 要求回傳之前每條回覆的推理內容。閘道器會補回客戶端丟掉的部分，所以 Business Data Platform 工具可以正常使用；如果在下方關閉補全，只有請求關閉了思考模式才會提供這些工具。',
        ark: 'Chat 和 Responses 填寫 https://ark.cn-beijing.volces.com/api/v3，Anthropic 填寫 https://ark.cn-beijing.volces.com/api/compatible；Coding Plan 分別填寫 https://ark.cn-beijing.volces.com/api/coding/v3 和 https://ark.cn-beijing.volces.com/api/coding。閘道器會保持每段對話的 prompt_cache_key 不變，讓快取持續命中。',
        byteplus:
          'Chat 和 Responses 填寫 https://ark.ap-southeast.bytepluses.com/api/v3，Anthropic 填寫 https://ark.ap-southeast.bytepluses.com/api/compatible；Coding Plan 分別填寫 https://ark.ap-southeast.bytepluses.com/api/coding/v3 和 https://ark.ap-southeast.bytepluses.com/api/coding。閘道器會保持每段對話的 prompt_cache_key 不變，讓快取持續命中。',
      },
    },
    baseUrl: {
      label: 'Base URL',
      description:
        '照服務商 SDK 文件填寫 base_url，閘道器在後面拼接 /chat/completions、/responses 或 /v1/messages。同一服務商的不同協議地址不同時，請分別新增上游。',
      preview: '請求將發往',
      missingPath:
        '這個服務商的 base_url 需要帶路徑，只填域名會請求到錯誤地址。',
      anthropicVersion:
        'Anthropic 的 base_url 不需要 /v1，閘道器會自動拼接 /v1/messages。',
      removeVersion: '去掉 /v1',
      correctPath: '改用 {{url}}',
      useDefault: '使用預設地址',
    },
    authMode: {
      label: 'API Key 由誰提供',
      managed: {
        title: '由閘道器保管 API Key',
        description: '客戶端只需要閘道器金鑰。',
      },
      passthrough: {
        title: '每個客戶端自帶 API Key',
        description:
          '客戶端除了閘道器金鑰，還要在 {{header}} 請求頭裡帶上自己的服務商 API Key。',
      },
    },
    apiKey: {
      label: 'API Key',
      placeholder: '貼上服務商的 API Key',
      stored: '已儲存',
      description: '加密儲存，之後不再顯示。',
      addressChanged:
        '地址已修改，請重新填寫 API Key。原來儲存的 API Key 不會發往新地址。',
      storedDescription: '已加密儲存。留空則保留原金鑰，填寫新金鑰會替換它。',
    },
    headers: {
      label: '額外請求頭',
      description:
        '隨每個請求發給服務商。取值加密儲存，之後不再顯示：已儲存的取值留空即保持不變，刪除這一行則移除該請求頭。',
      name: '請求頭名稱',
      value: '取值',
      add: '新增請求頭',
      addressChanged:
        '地址已修改，請重新填寫請求頭的取值。原來儲存的取值不會發往新地址。',
    },
    codingPlan: {
      label: '這是 Coding Plan 或訂閱金鑰',
      description: '訂閱類金鑰通常只授權在服務商自己的工具裡使用。',
      warning:
        '閘道器預設拒絕所有發往這個上游的請求。請改用模型 API Key；如果套餐條款允許在服務商自己的工具之外使用，可以開啟下面的選項。',
      allow: '允許通過閘道器使用這個套餐',
      allowDescription:
        '部分 Coding Plan 只授權在服務商自己的工具裡使用。開啟前請確認套餐條款允許，否則帳號可能被服務商限制。',
    },
    models: {
      label: '模型',
      placeholder: '輸入模型名後按回車',
      description: '客戶端可以請求的模型名。留空則接受任意模型名。',
    },
    aliases: {
      label: '模型別名',
      description:
        '讓客戶端用另一個名字請求模型，閘道器轉發前會換成上游的模型名。',
      name: '客戶端使用的名稱',
      target: '發給上游的模型',
      add: '新增別名',
    },
    contextWindows: {
      label: '上下文視窗',
      description:
        '長對話在接近模型的上下文視窗時壓縮。沒有列在這裡的模型使用上下文配置裡的預設上下文視窗，那裡也沒有設定時按 1,000,000 Token 計算。請填寫發給上游的模型名，也就是別名轉換之後的名稱。',
      model: '上游模型',
      tokens: 'Token 數',
      add: '新增視窗',
    },
    priority: {
      label: '優先順序',
      description: '多個上游提供同一模型時，新對話使用優先順序最高的上游。',
    },
    enabled: {
      label: '啟用',
      description:
        '停用的上游不再接收請求。正在使用它的對話會轉到其他提供該模型的上游，前提是客戶端的金鑰允許使用。',
    },
    gatewayTools: {
      label: '允許 Business Data Platform 工具',
      description:
        '允許模型通過這個上游使用上下文配置中選定的 Business Data Platform 工具。關閉後，進行中的對話也會停用這些工具。',
    },
    replayReasoning: {
      label: '補全推理內容回傳',
      description:
        '客戶端回傳歷史時丟掉了模型的推理內容，閘道器會在後續請求中補回。DeepSeek 在帶工具的請求裡缺少推理內容會報錯，所以 DeepSeek、火山方舟和 BytePlus 方舟預設開啟。',
    },
    cacheMinTokens: {
      label: '最小可快取長度',
      description:
        '只用於在請求日誌裡標記請求能否命中快取。請設為該模型可快取提示詞的最小長度。',
    },
  },
}

export default upstreams

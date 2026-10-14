const profiles = {
  inUseHelp:
    '要刪除它，請先吊銷這些金鑰；如果還需要它們，先簽發使用其他上下文配置的新金鑰來替換。',
  description:
    '決定對話如何使用 Business Data Platform 的記憶和工具。儲存後的修改只對之後開始的對話生效。',
  defaultName: '預設',
  loadFailed: '無法載入上下文配置',
  actions: {
    new: '新建配置',
    createRecommended: '使用推薦設定建立',
    customize: '自定義',
    reset: '恢復推薦設定',
  },
  usedBy_one: '{{count}} 個金鑰在用',
  usedBy_other: '{{count}} 個金鑰在用',
  unused: '沒有金鑰在用',
  deleteBlocked_one: '有 {{count}} 個金鑰在使用，請先吊銷',
  deleteBlocked_other: '有 {{count}} 個金鑰在使用，請先吊銷',
  empty: {
    title: '還沒有上下文配置',
    description:
      '每個閘道器金鑰都需要一份上下文配置。推薦設定會為每條新訊息召回記憶、儲存對話、為長對話生成摘要，並讓模型使用只讀的 Business Data Platform 工具，之後可以隨時修改。',
    readOnly: '等待閘道器管理員新增上下文配置。',
  },
  summary: {
    recallOn: '開啟 · 每條訊息 {{tokens}} Token',
    compactionOn: '用到 {{percent}} 時壓縮',
    agentWindowsOn: 'Agent 自管視窗',
    toolsEnabled_one: '已啟用 {{count}} 個工具',
    toolsEnabled_other: '已啟用 {{count}} 個工具',
  },
  deleteDialog: {
    title: '刪除“{{name}}”？',
    description: '沒有閘道器金鑰在用這份配置。刪除後無法恢復。',
    confirm: '刪除配置',
  },
  toast: {
    created: '已建立上下文配置“{{name}}”',
    saved: '已儲存“{{name}}”，新對話會使用這些設定。',
    deleted: '已刪除“{{name}}”',
    reset: '已恢復推薦設定，儲存後生效。',
  },
  editor: {
    back: '上下文配置',
    newTitle: '新建上下文配置',
    create: '建立配置',
    banner: '儲存後的修改只對新對話生效，進行中的對話沿用開始時的設定。',
    copyName: '{{name}} 副本',
    sourceMissing: '要複製的配置已不存在，已改為從推薦設定開始。',
    notFound: {
      title: '這份上下文配置已不存在',
      description: '它可能已被刪除。請返回列表選擇其他配置。',
    },
    sections: '配置分組',
    unsaved: '有未儲存的修改',
    invalid: '請先修正標出的設定，再儲存。',
    needsName: '填寫名稱後即可儲存。',
    unitHint: '{{unit}}（{{value}}）',
  },
  name: {
    label: '名稱',
    placeholder: '例如：程式設計',
    description: '為閘道器金鑰選擇配置時顯示這個名稱。',
  },
  recall: {
    title: '召回記憶',
    description:
      '每收到一條新的使用者訊息，就用它檢索 Business Data Platform，並把相關內容附加到這條訊息上。',
    profile: {
      label: '會話開頭提供使用者畫像',
      description:
        '新對話開始時，向模型提供你的 Business Data Platform 使用者畫像。此設定獨立於記憶召回。',
    },
    profileMaxTokens: {
      label: '開頭內容預算',
      description:
        '限制開頭的畫像、記憶目錄和技能目錄總量。目錄需要啟用讀取工具。這份預算獨立於召回，設為 0 時三項都不提供。',
    },
    showRecall: {
      label: '顯示召回摘要',
      description:
        '在回覆開頭用一行說明 Business Data Platform 附加了什麼：幾條、屬於哪些類別、幾個條目名，召回失敗時說明原因。模型看不到這行摘要，它也不會儲存到 Business Data Platform。只對新對話生效。',
    },
    sources: {
      label: '檢索範圍',
      description: '召回時檢索哪些內容。',
      memory: '記憶',
      resource: '資源',
      skill: '技能',
    },
    maxTokens: {
      label: '單條訊息預算',
      description: '一條訊息最多附加多少記憶，按閘道器的估算計算。',
    },
    sessionMaxTokens: {
      label: '單個上下文視窗預算',
      description:
        '一個上下文視窗內累計最多附加多少記憶，對話每壓縮一次就重新計算。設為 0 相當於關閉召回。',
    },
    scoreThreshold: {
      label: '相關度閾值',
      description:
        '只附加相關度不低於該值的結果，取值 0 到 1。值越高，附加的內容越少、越貼切。',
    },
    recallTimeout: {
      label: '超時時間',
      description:
        'Business Data Platform 沒有及時返回時，這條訊息會不帶記憶直接發給模型。',
    },
    queryMaxChars: {
      label: '檢索文本長度',
      description:
        '召回用最新一條使用者訊息作為檢索文本，超出這個長度的部分會被截掉。',
    },
    quotas: {
      label: '按分類限量',
      description: '為每個分類設定最多附加的條數。只檢索數量大於 0 的分類。',
      categories: {
        events: '事件',
        entities: '實體',
        preferences: '偏好',
        experiences: '經驗',
        resources: '資源',
        skills: '技能',
      },
    },
  },
  capture: {
    title: '儲存對話',
    description:
      '把已完成的輪次寫入 Business Data Platform 會話，讓 Business Data Platform 從中提取記憶。',
    idleSeconds: {
      label: '最新回覆等待時長',
      description:
        '下一條訊息到達時，上一輪會立即儲存。最新一輪迴復會先等待這段時間，如果沒有後續訊息，就儲存下來，Business Data Platform 隨即開始提取記憶。',
    },
    commitTokens: {
      label: '提交閾值',
      description:
        '已儲存但未提交的對話達到這個量時提交一次。Business Data Platform 在提交時提取記憶。',
    },
    keepRecentMessages: {
      label: '保留最近訊息',
      description: '每次提交至少在會話中留下最近這麼多條訊息，按整輪計算。',
    },
  },
  longConversations: {
    title: '長對話',
    description: '讓長對話始終不超出模型的上下文視窗。',
    compaction: {
      label: '壓縮',
      description:
        '對話接近模型的上下文視窗時，由同一個模型為它寫一份摘要，用摘要替換之前的訊息。',
    },
    threshold: {
      label: '壓縮時機',
      description: '上下文視窗用到多大比例時壓縮，取值 0.5 到 0.98。',
    },
    summaryMaxTokens: {
      label: '摘要長度上限',
      description: '模型寫一份摘要最多能用多少 Token。',
    },
    contextWindow: {
      label: '預設上下文視窗',
      description:
        '上游沒有列出該模型的上下文視窗時使用。兩處都沒有設定時，閘道器按 1,000,000 Token 計算，所以視窗更小的模型需要設定這一項。',
    },
    agentWindows: {
      label: 'Agent 自管上下文視窗',
      experimental: '實驗性',
      description:
        '給模型兩個工具，讓它自己寫好交接筆記、開啟新的上下文視窗，並告訴它當前視窗用了多少。開啟壓縮時，壓縮仍作為兜底。只在能使用 Business Data Platform 工具的對話中生效。',
      needsTools:
        '這份配置沒有開啟 Business Data Platform 工具，此設定不會生效。',
    },
    softRatio: {
      label: '軟提醒時機',
      description:
        '上下文視窗用到這個比例時，提醒模型做完當前這一步就開啟新視窗。每個視窗只提醒一次。',
    },
    hardRatio: {
      label: '硬提醒時機',
      description:
        '上下文視窗用到這個比例時，要求模型立即開啟新視窗。模型開啟新視窗之前每一步都會提醒，須高於軟提醒。',
    },
  },
  tools: {
    title: 'Business Data Platform 工具',
    description:
      '讓模型在回答時使用 Business Data Platform 工具。支援 Chat Completions、Responses 和 Anthropic Messages；客戶端須回傳完整對話。',
    available: {
      label: '工具',
      description:
        '推薦設定勾選只讀工具，會修改資料的工具不勾選。以後新增的工具會自動啟用。上游也需要允許使用 Business Data Platform 工具。',
    },
    empty: '簽發閘道器金鑰後即可載入工具清單。',
    loadFailed: '無法載入 Business Data Platform 工具',
    readOnly: '只讀',
    modifiesData: '會修改資料',
    executionNotice:
      '閘道器執行所選工具時不經過客戶端的許可權確認，其中一些工具會修改或刪除資料。“顯示工具呼叫”只在回覆裡報告每次呼叫，不會事先徵求同意。',
    showCalls: {
      label: '顯示工具呼叫',
      description:
        '閘道器每執行一次 Business Data Platform 工具，就在回覆里加一行提示，讓使用者看到這次呼叫。模型看不到這些提示，它們也不會儲存到 Business Data Platform。',
    },
    maxRounds: {
      label: '每次請求的工具輪數',
      description:
        '達到這個輪數後，閘道器拒絕後續的 Business Data Platform 呼叫，模型用已有結果和客戶端自己的工具繼續。留空表示不限。',
    },
    timeoutSeconds: {
      label: '單次呼叫超時',
      description: '超時的呼叫會向模型返回錯誤。',
    },
    resultBytes: {
      label: '結果大小上限',
      description: '超出的部分會在交給模型前截掉。',
    },
    totalSeconds: {
      label: '總時長',
      description: '模型使用工具超過這個時長，請求就會失敗。留空表示不限。',
    },
    totalTokens: {
      label: 'Token 預算',
      description:
        '一次請求中，工具呼叫和結果最多增加的 Token 數（估算值）。用完後，閘道器拒絕後續的 Business Data Platform 呼叫，模型用已有結果和客戶端自己的工具繼續。留空表示不限。',
    },
  },
}

export default profiles

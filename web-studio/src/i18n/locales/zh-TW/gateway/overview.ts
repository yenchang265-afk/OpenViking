const overview = {
  description:
    '客戶端如何使用閘道器：請求量、提示詞快取和記憶召回，以及 Business Context Platform 的執行狀態。',
  loadFailed: '無法載入概覽',
  showIssues: '在請求日誌中檢視',
  sampleNote_one:
    '以上資料統計自請求日誌中最新的 {{limit}} 條記錄。日誌保留 {{count}} 天。',
  sampleNote_other:
    '以上資料統計自請求日誌中最新的 {{limit}} 條記錄。日誌保留 {{count}} 天。',
  setup: {
    providedUpstreams_one: '閘道器管理員已提供 {{count}} 個上游',
    providedUpstreams_other: '閘道器管理員已提供 {{count}} 個上游',
    importedUpstreams_one:
      '已有 {{count}} 個上游，來自 Business Context Platform 的模型配置',
    importedUpstreams_other:
      '已有 {{count}} 個上游，來自 Business Context Platform 的模型配置',
    someImportedUpstreams:
      '已有 {{count}} 個上游，其中 {{imported}} 個來自 Business Context Platform 的模型配置',
    waitUpstreams: '等待閘道器管理員新增上游',
    providedProfiles_one: '閘道器管理員已提供 {{count}} 個上下文配置',
    providedProfiles_other: '閘道器管理員已提供 {{count}} 個上下文配置',
    waitProfiles: '等待閘道器管理員新增上下文配置',
    codingPlan:
      '{{name}} 是 Coding Plan 上游，確認套餐允許之前，發往它的請求都會被攔截。',
    confirm: '去確認',

    title: '快速開始',
    progress: '已完成 {{done}}/{{total}}',
    done: '已完成',
    view: '檢視',
    upstream: {
      title: '新增上游',
      description: '閘道器轉發請求的模型服務，例如 OpenAI 或火山方舟。',
      done_one: '已新增 {{count}} 個上游',
      done_other: '已新增 {{count}} 個上游',
      action: '新增上游',
      manual: '手動新增',
    },
    profile: {
      title: '建立上下文配置',
      description: '決定如何給新訊息補充記憶、如何儲存對話。',
      done_one: '已有 {{count}} 個上下文配置',
      done_other: '已有 {{count}} 個上下文配置',
      action: '使用推薦設定',
    },
    key: {
      title: '簽發閘道器金鑰',
      description: '客戶端憑這個金鑰呼叫閘道器。',
      blocked: '完成前兩步後即可簽發。',
      name: '我的金鑰',
      waiting: '閘道器管理員新增上游和上下文配置後，才能簽發金鑰。',
      done_one: '已簽發 {{count}} 個金鑰',
      done_other: '已簽發 {{count}} 個金鑰',
      action: '簽發金鑰',
    },
    connect: {
      title: '接入客戶端',
      description: '把客戶端指向閘道器地址、填入金鑰，發一條訊息。',
      action: '檢視接入指南',
    },
  },
  quick: {
    title: '快速模式',
    description: '跳過下面的步驟，一鍵拿到可以直接使用的閘道器金鑰。',
    upstreamImport:
      '上游：匯入 Business Context Platform 服務端的模型配置，沿用它的 API Key 和額度',
    upstreamUse: '上游：使用 {{names}}（{{models}}，{{protocol}}）',
    profileCreate: '上下文配置：用推薦設定新建“{{name}}”',
    profileUse: '上下文配置：使用“{{name}}”',
    keySelf: '金鑰：為 {{user}} 簽發',
    keyPick: '金鑰：下一步選擇金鑰歸屬的 Business Context Platform 使用者',
    action: '一鍵生成金鑰',
    running: '生成中…',
    retry: '重試',
    locked: '建立上下文配置或匯入模型需要閘道器管理金鑰。',
    noUsable:
      'Business Context Platform 的模型配置裡沒有閘道器能直接轉發的模型。處理下面列出的問題，或者在第 1 步手動新增上游。',
    keyName: '快速模式',
    divider: '或者按步驟手動配置',
  },
  kpi: {
    requests: {
      label: '請求數',
      hint: '經過閘道器的模型請求，不含記憶同步事件。',
      last: '最近一次請求：{{time}}',
      outputTokens: '輸出 {{tokens}} Token',
      none: '還沒有請求',
    },
    firstCall: {
      label: '首次呼叫快取命中率',
      hint: '每條新使用者訊息第一次呼叫模型時，輸入 Token 中命中服務商提示詞快取的比例。閘道器工作正常時，這個值應接近不經過閘道器時服務商能達到的命中率；明顯下降通常說明之前訊息裡補充的記憶沒有原樣發回。',
      footnote_one: '{{number}} 條新訊息',
      footnote_other: '{{number}} 條新訊息',
    },
    continuation: {
      label: '輪內快取命中率',
      hint: '同一輪對話裡後續的模型呼叫（例如工具結果返回之後）命中提示詞快取的比例，包括模型使用 Business Context Platform 工具時產生的呼叫。',
      footnote_one: '{{number}} 個工具步驟',
      footnote_other: '{{number}} 個工具步驟',
    },
    recall: {
      label: '召回的記憶條數',
      hint: '閘道器為新訊息補充的記憶條數。平均耗時只統計實際檢索了 Business Context Platform 的訊息。',
      footnote_one: '檢索 {{number}} 次，平均 {{duration}}',
      footnote_other: '檢索 {{number}} 次，平均 {{duration}}',
      none: '還沒有召回',
    },
  },
  cacheMiss: {
    title_one: '有 {{count}} 段長對話連續沒有命中提示詞快取',
    title_other: '有 {{count}} 段長對話連續沒有命中提示詞快取',
    description_one:
      '最近連續 {{streak}} 次模型呼叫的輸入都不少於 {{tokens}} Token，快取命中率都是 0%。常見原因是請求開頭的內容（系統提示詞、工具定義）每次都在變，或者上游把請求分給了不同的帳號或渠道。',
    description_other:
      '最近連續 {{streak}} 次模型呼叫的輸入都不少於 {{tokens}} Token，快取命中率都是 0%。常見原因是請求開頭的內容（系統提示詞、工具定義）每次都在變，或者上游把請求分給了不同的帳號或渠道。',
    action:
      '對照服務商後臺的快取記錄：那邊有命中，說明上游沒有把快取用量傳回閘道器；那邊也沒有，檢查系統提示詞裡有沒有時間這類每次都變的內容，以及中轉服務是否在多個渠道之間輪換。',
    noWrites:
      '上游也沒有寫入快取，客戶端很可能沒有在請求裡設定 cache_control。對照服務商後臺的快取記錄：那邊有命中，說明上游沒有把快取用量傳回閘道器。',
    streak_one: '連續 {{count}} 次未命中',
    streak_other: '連續 {{count}} 次未命中',
  },
  cacheUnreported: {
    title_one: '上游 {{upstreams}} 最近沒有返回過快取命中',
    title_other: '上游 {{upstreams}} 最近沒有返回過快取命中',
    description_one:
      '相關長對話的快取命中率一直是 0%，統計時都按未命中計算。可能是服務商不支援提示詞快取、客戶端沒有開啟快取，或者中轉服務沒有把快取用量傳回閘道器。',
    description_other:
      '相關長對話的快取命中率一直是 0%，統計時都按未命中計算。可能是服務商不支援提示詞快取、客戶端沒有開啟快取，或者中轉服務沒有把快取用量傳回閘道器。',
    separator: '、',
  },
  openviking: {
    title: 'Business Context Platform',
    description: '為新訊息檢索記憶，並儲存對話。',
    version: '版本',
    unreachable:
      '連不上 Business Context Platform 期間，請求照常發給模型，只是不帶記憶；儲存對話會一直重試，直到 Business Context Platform 恢復。',
    starting:
      '閘道器還沒完成對 Business Context Platform 的首次檢查，請稍後重新整理。',
  },
  saving: {
    title: '儲存對話',
    ok: '最近的請求中沒有儲存失敗的對話。',
    retrying_one:
      '有 {{count}} 段對話儲存到 Business Context Platform 失敗，正在重試。',
    retrying_other:
      '有 {{count}} 段對話儲存到 Business Context Platform 失敗，正在重試。',
    paused_one:
      '有 {{count}} 段對話多次儲存失敗，已暫停儲存；閘道器每 5 分鐘重試一次。',
    paused_other:
      '有 {{count}} 段對話多次儲存失敗，已暫停儲存；閘道器每 5 分鐘重試一次。',
  },
  degraded: {
    title: '降級請求',
    description: '閘道器沒能按常規處理記憶的請求。',
    suggestion: '建議操作：',
    empty: {
      title: '沒有降級請求',
      description: '統計範圍內的請求都按常規處理了記憶。',
    },
  },
  recent: {
    title: '最近請求',
    columns: {
      time: '時間',
      type: '型別',
      model: '模型',
      status: '狀態',
      memory: '記憶',
    },
    empty: {
      title: '還沒有請求',
      description: '客戶端通過閘道器發出請求後，會顯示在這裡。',
    },
  },
}

export default overview

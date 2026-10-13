const common = {
  title: 'Business Data Platform 閘道器',
  description:
    '讓任何使用 API Key 的模型客戶端都能用上 Business Data Platform 記憶。把客戶端指向閘道器後，閘道器會為每條新訊息補充相關記憶，並把對話儲存回 Business Data Platform。',
  beta: {
    label: 'Beta',
    hint: '測試版：Business Data Platform 閘道器仍在完善，後續版本可能調整設定和介面。',
  },
  tabs: {
    label: 'Business Data Platform 閘道器分割槽',
    overview: '概覽',
    upstreams: '上游',
    profiles: '上下文配置',
    keys: '金鑰',
    requests: '請求日誌',
    connect: '接入',
  },
  address: {
    label: '閘道器地址',
    copy: '複製閘道器地址',
  },
  actions: {
    cancel: '取消',
    copy: '複製',
    delete: '刪除',
    duplicate: '複製一份',
    edit: '編輯',
    more: '更多操作',
    refresh: '重新整理',
    remove: '移除',
    retry: '重試',
    revoke: '吊銷',
    save: '儲存',
    viewAll: '檢視全部',
  },
  states: {
    loading: '載入中…',
    saving: '儲存中…',
    updatedAt: '更新於 {{time}}',
    any: '不限',
    on: '開啟',
    off: '關閉',
  },
  copy: {
    done: '已複製到剪貼簿',
    failed: '複製失敗，請選中文本後手動複製。',
  },
  access: {
    title: '需要帳號管理員許可權',
    description:
      '管理 Business Data Platform 閘道器需要本帳號的帳號管理員金鑰或 Root 金鑰。請先在連線設定中填寫。',
    action: '開啟連線設定',
  },
  unavailable: {
    notEnabled: {
      title: 'Business Data Platform 閘道器未開啟',
      description:
        '這臺伺服器沒有開啟 Business Data Platform 閘道器。請在 ov.conf 中開啟它，重啟 Business Data Platform，再啟動閘道器。',
    },
    tokenMissing: {
      title: '缺少管理令牌',
      description:
        'Business Data Platform 需要和閘道器使用同一個管理令牌才能管理閘道器。請為 Business Data Platform 和閘道器設定下面的環境變數（至少 32 個字元），然後重啟兩者。',
    },
    tokenMismatch: {
      title: '管理令牌不一致',
      description:
        'Business Data Platform 和閘道器啟動時用的管理令牌不同，所以閘道器拒絕了 Business Data Platform 的請求。請把下面的環境變數設成同一個值，然後重啟兩者。',
    },
    unsupported: {
      title:
        '這臺 Business Data Platform 伺服器無法管理 Business Data Platform 閘道器',
      description:
        'Studio 連線的 Business Data Platform 伺服器不支援 Business Data Platform 閘道器。請升級 Business Data Platform Server 並重啟，然後重試。',
    },
    devMode: {
      title: 'Business Data Platform 執行在開發模式',
      description:
        '開發模式下每個金鑰都以 Root 身份操作，而閘道器不接受 Root 金鑰，所以簽發不了閘道器金鑰。請把 Business Data Platform 切換到 API 金鑰模式並重啟，再到連線設定中填寫帳號管理員金鑰。',
    },
    unreachable: {
      title: 'Business Data Platform 連不上閘道器',
      description:
        '閘道器沒有執行，或者 ov.conf 裡的 gateway.url 指向了錯誤的地址。請啟動閘道器，並確認 Business Data Platform 能訪問這個地址。',
    },
    failed: {
      title: '無法載入 Business Data Platform 閘道器',
    },
    fixLabel: '需要修改的配置',
    terminal: '終端',
    environment: '環境變數',
    docs: '部署說明',
  },
  errors: {
    reasons: {
      not_enabled: '這臺伺服器沒有開啟 Business Data Platform 閘道器。',
      token_missing:
        '沒有設定管理令牌，Business Data Platform 無法管理閘道器。',
      token_mismatch:
        '閘道器拒絕了 Business Data Platform 的管理令牌，兩者必須使用同一個令牌。',
      unreachable: 'Business Data Platform 連不上閘道器。',
      unsupported:
        '這臺 Business Data Platform 伺服器不支援 Business Data Platform 閘道器。',
      conflict: '這項修改與現有配置衝突。',
      invalid: '閘道器拒絕了這些設定，請檢查填寫的值後重試。',
      forbidden: '沒有執行此操作的許可權。',
      not_found: '該項已不存在，請重新整理後重試。',
      unauthorized: '金鑰被拒絕，請檢查連線設定。',
      other: '操作失敗，請重試。',
    },
    inUse: '仍有金鑰在使用它，請先吊銷這些金鑰。',
    invalidSettings: '閘道器拒絕了這些設定，請檢查各項取值和範圍。',
    invalidKeyRequest: '閘道器拒絕了這個金鑰，請檢查填寫內容後重試。',
    unknownProfile: '所選的上下文配置已不存在。',
    unknownUpstream: '所選的上游中有一個已不存在。',
    keyNotFound: '這段對話使用的閘道器金鑰已被吊銷，無法再重新同步。',
    sessionNotFound: '閘道器中已沒有這段對話的記錄。',
    upstreamKeyMissing:
      '沒有可用於測試的已儲存 API Key：這個上游由客戶端自帶 API Key，或者還沒有填寫 API Key。',
    subscriptionKey: '不支援 Claude 訂閱登入，請使用模型 API Key。',
  },
  validation: {
    required: '必填',
    number: '請輸入數字',
    integer: '請輸入整數',
    min: '不能小於 {{min}}',
    max: '不能大於 {{max}}',
    range: '取值範圍為 {{min}} 到 {{max}}',
    rangeExclusive: '須大於 {{min}}，且不超過 {{max}}',
    greaterThan: '須大於 {{min}}',
    selectOneSource: '至少選擇一個來源',
    unknownCategory: '未知分類“{{name}}”',
    quotasAllZero: '至少把一個分類設為大於 0，或關閉分類限額',
    softBelowHard: '須低於硬提醒時機',
    baseUrl:
      '請輸入 http:// 或 https:// 地址，不能包含帳號密碼、查詢引數或片段',
    subscriptionKey:
      '不支援 Claude 訂閱令牌（sk-ant-oat…），請使用模型 API Key。',
    apiKeyRequired: '請填寫 API Key，或改為由每個客戶端自帶 API Key',
    headerInvalid: '請求頭“{{name}}”的名稱或取值無效',
    headerReserved: '“{{name}}”由閘道器設定，不能修改',
    headerValue: '請填寫“{{name}}”的取值',
    aliasTarget: '請填寫“{{name}}”對應的上游模型',
    contextWindow: '“{{name}}”的上下文視窗至少為 {{min}} Token',
    protocolUnsupported:
      '$t(enums.vendor.{{vendor}}) 不提供 $t(enums.protocol.{{protocol}}) 介面。請換一種協議，或者把服務商改成“$t(enums.vendor.generic)”。',
  },
  units: {
    bytes: '位元組',
    characters: '字元',
    entries: '條',
    messages: '條訊息',
    rounds: '輪',
    seconds: '秒',
    tokens: 'Token',
  },
  field: {
    default: '預設值：{{value}}',
    notSet: '未設定',
    noLimit: '不限',
    advanced: '進階設定',
    sectionInvalid: '這一部分有設定需要修改，改好後才能儲存。',
    storedSecret: '已儲存，留空則保持不變',
  },
  keyValue: {
    add: '新增',
    remove: '移除',
    duplicate: '名稱重複，只保留最後一項',
  },
  tags: {
    remove: '移除 {{value}}',
    suggestions: '建議',
  },
}

export default common

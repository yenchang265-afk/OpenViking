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
    view: '檢視',
    back: '返回',
    viewAll: '檢視全部',
    viewKeys: '檢視金鑰',
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
  docs: {
    link: '文件',
    learnMore: '瞭解更多',
    troubleshoot: '排查說明',
  },
  access: {
    title: '先連線 Business Data Platform',
    invalid: 'Business Data Platform API 金鑰無效',
    description:
      '閘道器用你的 Business Data Platform API 金鑰確認你是誰。請先在連線設定中填寫它。',
    invalidDescription:
      'Business Data Platform 拒絕了連線設定中的 API 金鑰，它可能已被重新生成或刪除。請換一個有效的金鑰。',
    action: '開啟連線設定',
  },
  management: {
    title: '輸入閘道器管理金鑰',
    label: '閘道器管理金鑰',
    description:
      '閘道器管理金鑰由部署這臺閘道器的人設定，用來修改上游和上下文配置。它不是 Business Data Platform API 金鑰，也不是客戶端用的閘道器金鑰。',
    where: '在哪裡找？',
    prefix:
      'openviking-server init、openviking-gateway init 和 Studio“開啟閘道器”生成的值都以 ovgm_ 開頭。',
    environment: '也可能設在環境變數裡，它優先於配置檔案：',
    studio: 'Root 可以在“設定 → 服務端配置 → 檔案編輯”中檢視 ov.conf。',
    reset: '實在找不到，就在原來的位置換一個至少 32 個字元的新金鑰，然後重啟。',
    resetDocs: '如何重置',
    keyPlaceholder: '<至少 32 個字元>',
    session: '只儲存在當前瀏覽器標籤頁，關閉後自動鎖定。',
    wrongKey: '這是閘道器金鑰（給客戶端用的），請輸入閘道器管理金鑰。',
    invalid:
      '閘道器管理金鑰不正確。如果金鑰被更換或遺失，請看上方的“在哪裡找？”。注意，這裡要填的不是 Business Data Platform 的管理員 API 金鑰。',
    unlock: '解鎖',
    unlocked: '已解鎖，現在可以修改上游和上下文配置',
    lock: '鎖定',
    editing: '可修改上游和上下文配置',
    expired: '閘道器管理金鑰已失效，上游和上下文配置恢復為只讀。',
    readOnly:
      '上游和上下文配置由閘道器管理員統一提供。你可以檢視，並在簽發金鑰時選用。',
    adminReadOnly:
      'Business Data Platform 的管理員和 Root 也需要閘道器管理金鑰才能修改。如果這臺服務是你部署的，金鑰在 ov.conf 的 gateway.management_key 裡。',
    shared:
      '你正在修改本帳號所有使用者共用的配置，儲存後立即對使用它的金鑰生效。',
    publicTitle: '這臺閘道器對所有 Business Data Platform 商業版使用者開放',
    publicDescription:
      '它連線的是公共 Business Data Platform 服務，又沒有設定閘道器管理金鑰，所以任何持有商業版 API 金鑰的人都能登入這臺閘道器、用它轉發模型請求，還能修改自己帳號下的上游。如果這臺閘道器只給你自己或團隊使用，請設定閘道器管理金鑰，然後重啟閘道器。',
    generate: '可以用這條命令生成金鑰：',
    dismiss: '關閉提示',
  },
  unavailable: {
    notEnabled: {
      title: '這臺 Business Data Platform 沒有開啟閘道器',
      description:
        '執行 openviking-server init 並選擇 Update gateway；也可以在 ov.conf 中加入下面的配置，然後重啟 Business Data Platform。',
    },
    contact: '請聯絡部署 Business Data Platform 的人開啟閘道器。',
    trusted: {
      title: '閘道器不支援 Trusted 模式',
      description:
        '閘道器要靠 API 金鑰識別每個使用者。請在 ov.conf 中把 server.auth_mode 改為 api_key，然後重啟 Business Data Platform。',
    },
    openvikingUnreachable: {
      title: '閘道器連不上 Business Data Platform（{{url}}）',
      description:
        '確認 Business Data Platform 正在執行，並檢查閘道器的 openviking_url（gateway.conf 或 OPENVIKING_GATEWAY_OPENVIKING_URL）是否指向它，然後重試。',
    },
    failed: {
      title: '無法載入 Business Data Platform 閘道器',
    },
    fixLabel: '需要修改的配置',
    terminal: '終端',
    environment: '環境變數',
    enable: {
      description: 'Studio 可以直接開啟：把設定寫入 ov.conf，然後重啟服務。',
      descriptionManualRestart:
        'Studio 可以把設定寫入 ov.conf。這臺服務不能從 Studio 重啟，儲存後請自行重啟。',
      action: '開啟閘道器',
      confirmTitle: '開啟閘道器？',
      confirmRestart:
        'Studio 會在 ov.conf 中寫入 gateway.enabled: true，然後重啟服務。重啟期間請求會中斷幾秒。',
      confirmManualRestart:
        'Studio 會在 ov.conf 中寫入 gateway.enabled: true。重啟服務後閘道器才會開啟。',
      protect: '只有持有閘道器管理金鑰的人才能修改上游和上下文配置',
      protectHint:
        'Studio 會生成金鑰，寫入 ov.conf 的 gateway.management_key，儲存後只顯示一次。',
      checking: '正在讀取 ov.conf…',
      saving: '正在儲存 ov.conf…',
      restarting: '正在儲存 ov.conf 並重啟服務…',
      savedRestart:
        '已儲存到 ov.conf。重啟服務後閘道器才會開啟，重啟完成後點“重試”。',
      readOnly:
        '這臺服務的 ov.conf 是隻讀的（例如由 Helm ConfigMap 掛載），Studio 改不了它。請在部署配置中開啟閘道器，然後重啟服務：',
      helm: 'Helm values',
      stillOff:
        '服務已重啟，但閘道器仍未開啟。請檢查 OPENVIKING_GATEWAY_ENABLED 是否設成了 false 之類的值，它會覆蓋 ov.conf。',
      rolledBack:
        '服務拒絕了新配置，繼續使用原來的配置，所以閘道器仍未開啟。原因請檢視服務日誌。',
      conflict: 'ov.conf 在頁面載入後被改過，請重新讀取後再試。',
      reload: '重新讀取 ov.conf',
      failed: '開啟閘道器失敗：{{message}}',
      restartFailed:
        'ov.conf 已儲存，但無法確認服務是否重啟成功：{{message}}。請檢查服務狀態，然後點“重試”。',
      keyTitle: '儲存閘道器管理金鑰',
      keyOnce:
        '金鑰已寫入 ov.conf 的 gateway.management_key，Root 之後可以在“設定 → 服務端配置”中檢視。修改上游和上下文配置時需要它；關閉這個瀏覽器標籤頁之前，當前頁面保持解鎖。',
      copyKey: '複製閘道器管理金鑰',
      copyFailed: '複製失敗，金鑰已選中，請按 Ctrl+C 或 ⌘C 複製。',
      keyOnceManual:
        '金鑰已寫入 ov.conf 的 gateway.management_key，Root 之後可以在“設定 → 服務端配置”中檢視。修改上游和上下文配置時需要它；重啟服務後，在閘道器頁面點“輸入閘道器管理金鑰”並貼上。',
      keySaved: '已儲存',
      continue: '已儲存，開啟閘道器',
    },
  },
  errors: {
    reasons: {
      management_key_required:
        '上游和上下文配置由閘道器管理員統一提供，輸入閘道器管理金鑰後才能修改。',
      management_key_invalid:
        '閘道器管理金鑰不正確，請用當前的金鑰重新解鎖。解鎖對話方塊的“在哪裡找？”列出了它的存放位置。',
      vlm_import_forbidden:
        '你沒有匯入 Business Data Platform 模型配置的許可權。',
      vlm_import_unavailable:
        '這臺閘道器不在 Business Data Platform 服務內執行，讀不到服務端的模型配置，請手動新增上游。',
      in_use_one: '仍有 {{count}} 個金鑰在使用它。',
      in_use_other: '仍有 {{count}} 個金鑰在使用它。',
      upstream_key_missing:
        '這個上游沒有儲存 API Key，或者由客戶端自帶 API Key，閘道器無法發起測試。',
      trusted_mode_unsupported: '閘道器不支援 Trusted 模式。',

      not_enabled: '這臺 Business Data Platform 沒有開啟閘道器。',
      conflict: '這項修改與現有配置衝突。',
      invalid: '閘道器拒絕了這些設定，請檢查填寫的值後重試。',
      forbidden: '沒有執行此操作的許可權。',
      not_found: '該項已不存在，請重新整理後重試。',
      unauthorized: 'Business Data Platform API 金鑰被拒絕，請檢查連線設定。',
      other: '操作失敗，請重試。',
    },
    inUse: '仍有金鑰在使用它，請先吊銷這些金鑰。',
    invalidSettings: '閘道器拒絕了這些設定，請檢查各項取值和範圍。',
    invalidKeyRequest: '閘道器拒絕了這個金鑰，請檢查填寫內容後重試。',
    unknownProfile: '所選的上下文配置已不存在。',
    unknownUpstream: '所選的上游中有一個已不存在。',
    keyNotFound: '這段對話使用的閘道器金鑰已被吊銷，無法再重新同步。',
    sessionNotFound: '閘道器中已沒有這段對話的記錄。',
    subscriptionKey: '不支援 Claude 訂閱登入，請使用模型 API Key。',
  },
  validation: {
    anthropicBaseUrl: '去掉末尾的 /v1 才能儲存',
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
    baseUrl: '請輸入 http:// 或 https:// 地址，不能包含帳號密碼或 # 片段',
    baseUrlPlaceholder: '地址裡只能使用 {api_key} 佔位符，且不能放在域名裡',
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
    none: '未設定',
    duplicate: '名稱重複，只保留最後一項',
  },
  tags: {
    remove: '移除 {{value}}',
    suggestions: '建議',
  },
}

export default common

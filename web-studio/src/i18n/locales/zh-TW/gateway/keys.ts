const keys = {
  description:
    '每個金鑰屬於一個 Business Data Platform 使用者，使用一份上下文配置和一組上游。金鑰不能修改，需要調整時請簽發新金鑰並吊銷舊金鑰。',
  issue: '簽發金鑰',
  loadFailed: '無法載入閘道器金鑰',
  prerequisites: {
    upstream: '簽發金鑰前，請先新增上游。',
    profile: '簽發金鑰前，請先建立上下文配置。',
    both: '簽發金鑰前，請先新增上游並建立上下文配置。',
    addUpstream: '新增上游',
    createProfile: '建立上下文配置',
  },
  empty: {
    title: '還沒有閘道器金鑰',
    description:
      '客戶端用閘道器金鑰代替模型 API Key。用它發出的請求會轉發到已配置的上游，並讀取和儲存某個 Business Data Platform 使用者的記憶。建議每個人、每個客戶端各用一個金鑰，便於單獨吊銷。',
  },
  table: {
    name: '名稱',
    key: '金鑰',
    user: 'Business Data Platform 使用者',
    profile: '上下文配置',
    upstreams: '上游',
    models: '模型',
    created: '建立時間',
    actions: '操作',
  },
  missing: '已刪除',
  missingProfile: '這個上下文配置已不存在',
  missingUpstream: '這個上游已不存在',
  extra: '+{{count}}',
  actions: {
    revokeKey: '吊銷“{{name}}”',
    more: '“{{name}}”的更多操作',
    deleteUserData: '刪除該使用者的閘道器資料…',
  },
  revoke: {
    title: '吊銷“{{name}}”？',
    description:
      '使用這個金鑰的客戶端會立即失去訪問許可權。對話和記憶都會保留，為同一使用者簽發新金鑰後可以接著使用。尚未儲存到 Business Data Platform 的內容（例如最新一條回覆）只有在用新金鑰繼續這段對話時才會儲存。',
    confirm: '吊銷金鑰',
    done: '已吊銷“{{name}}”',
  },
  deleteUser: {
    title: '刪除 {{user}} 的閘道器資料？',
    description_one:
      '這會弔銷 {{user}} 的閘道器金鑰，並刪除閘道器為該使用者儲存的對話狀態，其中包括尚未儲存到 Business Data Platform 的對話內容。該使用者的客戶端會立即失去訪問許可權。已經存入 Business Data Platform 的記憶不受影響。',
    description_other:
      '這會弔銷 {{user}} 的全部 {{count}} 個閘道器金鑰，並刪除閘道器為該使用者儲存的對話狀態，其中包括尚未儲存到 Business Data Platform 的對話內容。該使用者的客戶端會立即失去訪問許可權。已經存入 Business Data Platform 的記憶不受影響。',
    confirm: '刪除閘道器資料',
    done: '已刪除 {{user}} 的閘道器資料',
  },
  form: {
    title: '簽發閘道器金鑰',
    description: '金鑰簽發後立即可用。完整金鑰只在簽發成功後顯示一次。',
    name: {
      label: '名稱',
      placeholder: '例如：Alice · Claude Code',
      description: '用來區分不同的金鑰，寫上使用者和客戶端最清楚。',
    },
    user: {
      label: 'Business Data Platform 使用者',
      placeholder: '選擇 Business Data Platform 使用者',
      loading: '正在載入使用者…',
      description:
        '閘道器會以這個使用者的身份召回和儲存記憶。該使用者的 Business Data Platform 金鑰在服務端讀取，由閘道器加密儲存，不會顯示。',
      roles: {
        admin: '管理員',
        user: '使用者',
      },
      unavailable: '服務端讀不到這個使用者的金鑰，請改為貼上',
      loadFailed: '無法載入本帳號的使用者，請直接貼上金鑰。',
      none: '服務端讀不到本帳號使用者的金鑰，請直接貼上。',
      root: '使用 Root 金鑰時無法在這裡選擇使用者，請直接貼上金鑰。',
      choose: '選擇使用者',
    },
    openvikingKey: {
      label: 'Business Data Platform 金鑰',
      description:
        '本帳號中某個 Business Data Platform 使用者的金鑰。閘道器會以這個使用者的身份召回和儲存記憶。不接受 Root 金鑰。金鑰加密儲存，之後不再顯示。',
      gatewayKey:
        '這是閘道器金鑰，請填寫 Business Data Platform 使用者自己的金鑰。',
      paste: '貼上 Business Data Platform 金鑰',
    },
    profile: {
      label: '上下文配置',
      placeholder: '選擇上下文配置',
      description: '決定使用這個金鑰的對話如何召回和儲存記憶。',
      empty: '還沒有上下文配置。',
      create: '去建立',
    },
    upstreams: {
      label: '上游',
      description:
        '每個請求到達時，閘道器會從所選上游中挑一個協議與客戶端一致、並且提供所請求模型的上游。',
      required: '至少選擇一個上游',
      empty: '還沒有上游。',
      create: '去新增',
      off: '已停用',
    },
    models: {
      label: '允許的模型',
      optional: '可選',
      placeholder: '輸入模型名稱後按回車',
      description: '留空則允許這些上游提供的全部模型。',
    },
    submit: '簽發金鑰',
  },
  errors: {
    title: '無法簽發金鑰',
    rootKey:
      '這是 Root 金鑰。請改用本帳號中某個 Business Data Platform 使用者的金鑰。',
    otherAccount:
      '這個 Business Data Platform 金鑰屬於其他帳號，請使用本帳號的使用者金鑰。',
    invalidKey:
      'Business Data Platform 拒絕了這個金鑰。請檢查金鑰是否完整，以及是否已被重新生成。',
    unavailable:
      '閘道器連不上 Business Data Platform，無法校驗這個金鑰。請稍後重試。',
    versionMismatch:
      'Business Data Platform 版本低於閘道器的要求。請升級 Business Data Platform 後重試。',
    unknownUser: '這個使用者已不在本帳號中，請重新選擇。',
    userKeyUnreadable:
      '服務端讀不到這個使用者的 Business Data Platform 金鑰，請改為貼上。',
  },
  secret: {
    title: '複製閘道器金鑰',
    once: '完整金鑰只顯示這一次。',
    copyKey: '複製閘道器金鑰',
    user: 'Business Data Platform 使用者',
    profile: '上下文配置',
    connectTitle: '接入客戶端',
    clients: {
      'claude-code': {
        intro: '在啟動 Claude Code 的終端裡設定這些環境變數。',
      },
      codex: {
        intro: '在 Codex 配置檔案中把閘道器新增為服務商，再在終端裡匯出金鑰。',
      },
      chat: {
        intro:
          '在任意相容 OpenAI 的客戶端或 SDK 中使用這些設定。同一段對話的每條訊息都帶上相同的 X-OpenViking-Session。',
      },
    },
    noProtocol: '這個金鑰沒有已啟用的 {{protocol}} 上游，{{client}} 無法使用。',
    moreClients: '其他客戶端和詳細說明',
    done: '我已複製',
  },
}

export default keys

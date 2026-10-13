const enums = {
  protocol: {
    anthropic: 'Anthropic Messages',
    chat: 'Chat Completions',
    responses: 'Responses',
  },
  vendor: {
    generic: '通用',
    anthropic: 'Anthropic',
    openai: 'OpenAI',
    deepseek: 'DeepSeek',
    ark: '火山方舟',
    byteplus: 'BytePlus 方舟（海外站）',
  },
  authMode: {
    managed: '閘道器保管 API Key',
    passthrough: '客戶端自帶 API Key',
  },
  kind: {
    user: '新訊息',
    continuation: '工具步驟',
    auxiliary: '輔助請求',
    subagent: '子 Agent',
    count: 'Token 計數',
    passthrough: '直接轉發',
    capture: '記憶同步',
  },
  health: {
    ok: '已連線',
    degraded: '異常',
    starting: '啟動中',
  },
  captureStatus: {
    active: '正常',
    disabled: '已關閉',
    retrying: '重試中',
    paused: '已暫停',
  },
  captureReason: {
    history_changed: '對話歷史有改動，後續內容改存到新的 OpenViking 會話',
    continued_after_idle:
      '已儲存的一輪對話在停頓後又繼續了，後續內容改存到新的 OpenViking 會話',
    history_changed_during_delivery:
      '儲存過程中對話歷史有改動，後續內容改存到新的 OpenViking 會話',
    manual_reset: '管理員已手動重新同步',
    delivery_recovered: '儲存已恢復正常',
    delivery_failed: '儲存到 OpenViking 失敗',
    invalid_archive_id: 'OpenViking 返回了無法識別的歸檔',
  },
  recallReason: {
    recalled: '已補充記憶',
    empty: '沒有找到相關內容',
    disabled: '召回已關閉或預算已用完',
    recall_timeout: '召回超時',
  },
  toolSkipReason: {
    tools_require_full_history:
      'Responses 請求需回傳完整對話，並設定 store: false',
    upstream_tools_disabled: '這個上游關閉了 OpenViking 工具',
    tools_multiple_choices: '請求要求返回多個候選結果（n > 1）',
    tools_structured_output: '請求要求結構化輸出',
    tools_non_function: '客戶端傳入了非函式型別的工具',
    tools_forced_choice: '客戶端指定了必須呼叫的工具',
    deepseek_reasoning_history_required:
      'DeepSeek 開啟了思考模式，但之前回復的推理內容補不回來',
    tool_name_collision: '客戶端已接入 OpenViking 工具',
    tools_unavailable: '這段對話首次需要工具時無法載入 OpenViking 工具清單',
    tools_not_selected_at_session_start: '這段對話沒有 OpenViking 工具',
  },
  toolStopReason: {
    token_budget: '工具 Token 預算已用完',
  },
  windowReminder: {
    soft: '已提醒模型儘快開啟新視窗',
    hard: '已要求模型立即開啟新視窗',
  },
  openviking: {
    unavailable: 'OpenViking 無法訪問或響應超時',
    unauthorized: 'OpenViking 拒絕了這個金鑰，它可能填錯了或已被吊銷。',
    httpStatus: 'OpenViking 返回了 HTTP {{status}}',
    errorCode: 'OpenViking 報告了錯誤 {{code}}',
    versionMismatch: 'OpenViking 版本低於閘道器的要求',
    identityMissing: 'OpenViking 無法識別這個金鑰所屬的使用者',
    rootKey: '不接受 Root 金鑰，請使用本帳號下的使用者金鑰。',
    otherAccount: '這個 OpenViking 金鑰屬於其他帳號。',
  },
  degradation: {
    memory_store_failure: {
      label: '記憶不可用',
      explanation: '閘道器沒能準備記憶，這次請求沒有帶記憶就發給了模型。',
      action:
        '檢查閘道器所在機器的磁碟和日誌。如果剛刪除過該使用者的閘道器資料，出現這一項是正常的。',
    },
    unsafe_json: {
      label: '原樣轉發',
      explanation:
        '請求裡有重複的鍵，或有無法精確重新編碼的數字，閘道器原樣轉發了它，沒有補充記憶。',
      action: '通常由客戶端造成，閘道器這邊無需調整。',
    },
    upstream_changed: {
      label: '上游已切換',
      explanation:
        '這段對話最初使用的上游已不可用，改由其他上游回答，模型服務商的快取也隨之重新開始。',
      action:
        '重新啟用原來的上游，或讓客戶端改用包含該上游的金鑰；新開的對話會固定使用當前的上游。',
    },
    missing_injection_record: {
      label: '記憶記錄缺失',
      explanation:
        '這段對話早先補充的記憶已不在儲存中，歷史訊息只能不帶它發出。',
      action:
        '通常發生在儲存資料丟失後或很久以前的對話裡。如果反覆出現，請開始新對話。',
    },
    plugin_present: {
      label: '檢測到 OpenViking 外掛',
      explanation:
        '客戶端已經在使用 OpenViking 外掛，閘道器因此不再為這段對話補充和儲存記憶。',
      action:
        '使用外掛時出現這一項是正常的。如果想改用閘道器的記憶，請移除外掛後開始新對話。',
    },
    ark_cache_parameters_changed: {
      label: '快取引數有變化',
      explanation:
        '模型、思考模式、取樣引數、系統提示詞或工具與對話的第一次請求不同，方舟的提示詞快取很可能沒有命中。',
      action: '在同一段對話裡保持這些引數不變。',
    },
    hidden_reply_without_anchor: {
      label: '模型未返回回答',
      explanation:
        '模型使用 OpenViking 工具後沒有返回可用於繼續對話的內容，下一輪無法沿用這次工具呼叫的結果。',
      action: '重試本次提問，或開始一段新對話。',
    },
    hidden_tool_history_unavailable: {
      label: '工具歷史無法繼續使用',
      explanation:
        '這段 Claude 對話用過 OpenViking 工具，但當前請求無法使用這些工具。閘道器已去掉之前的思考內容，繼續傳送對話文本。',
      action: '檢視本次請求的工具停用原因，恢復原設定，或開始一段新對話。',
    },
    hidden_tool_loop_failed: {
      label: 'OpenViking 工具呼叫失敗',
      explanation:
        '模型使用 OpenViking 工具的過程中有一次模型呼叫失敗，客戶端收到了錯誤。',
      action: '確認這個上游支援工具呼叫，或為它關閉 OpenViking 工具。',
    },
    capture_parse_failure: {
      label: '回覆未儲存',
      explanation:
        '流式回覆無法解析，這條回覆沒有儲存到 OpenViking。客戶端不受影響。',
      action: '偶爾出現無需處理；頻繁出現時再排查。',
    },
  },
}

export default enums

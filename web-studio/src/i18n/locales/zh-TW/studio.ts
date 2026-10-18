const studio = {
  profiles: {
    connectionChanged: '連線已切換，請在當前連線上重新選擇身份。',
    identityPending: '身份待確認',
    title: '連線配置',
    hint: '啟用一份配置，使用對應服務和憑證。刪除當前配置前，請先啟用另一份配置。',
    add: '新增配置',
    edit: '編輯配置',
    delete: '刪除',
    activate: '啟用',
    active: '已啟用',
    name: '配置名稱',
    save: '儲存',
    cancel: '取消',
    saveHint: '新增配置儲存後需手動啟用。編輯已啟用配置後，儲存會重新連線。',
    invalidUrl:
      '請輸入有效的 HTTP 或 HTTPS 服務地址，地址中不能包含帳號或密碼。',
    deleteConfirm: '刪除“{{name}}”？已儲存的憑證也會被移除。',
    fields: {
      baseUrl: '服務地址',
      apiKey: '使用者 API Key',
      adminApiKey: '管理 API Key（選填）',
      accountId: '帳號 ID',
      userId: '使用者 ID',
    },
  },

  selectSessionRecord: '從左側選擇一個會話，檢視其歷史訊息。',
  noSessionRecords: '當前身份沒有可檢視的會話記錄。',
  sessionRecords: '會話記錄',
  processingTasks: '處理任務',
  backToFiles: '返回檔案列表',
  showOverview: '展開統計與佇列',
  hideOverview: '收起統計與佇列',

  watchesReadDescription: '檢視已配置的定時同步任務及執行狀態。',
  watchesReadEmpty: '當前沒有可訪問的定時同步任務。',
  statistics: '統計分析',
  listingLimit: '當前檢視最多展示 500 項。',
  directory: '我的目錄',
  memories: '記憶',
  domainsLabel: 'Studio 功能域',
  domains: { workspace: '工作區', extensions: '高階功能', management: '管理' },
  providers: {
    opensource: '開源服務',
    volcengine: '火山託管',
    unknown: '服務型別待確認',
    checking: '正在檢測連線…',
  },
  cloudManagement:
    '火山管理功能需要連線獨立管理服務。資料 API Key 不會自動開放管理許可權。',
  connectionSettings: '連線設定',
  retry: '重試',
  loading: '正在載入…',
  empty: '當前目錄為空。',
  selectFile: '選擇檔案以預覽內容。',
  spaces: '目錄範圍',
  personal: '我的空間',
  shared: '共享資源',
  back: '返回',
  readOnly: '當前工作區為只讀。共享資源與個人空間分開展示。',
  directoryDescription: '瀏覽自己的上下文，以及獲得授權的共享資源。',
  directoryError: '無法開啟目錄：目錄可能不存在，或當前身份沒有訪問許可權。',
  states: {
    gatewayAuthMode: {
      title: 'Gateway 需要 API Key 認證模式',
      description:
        '請使用已驗證的管理憑證連線採用 API Key 模式的開源服務。Gateway 使用者繫結暫不支援 trusted 模式。',
    },
    checking: {
      title: '正在驗證可用性',
      description: '正在驗證當前連線及讀取能力。',
    },
    connectionFailed: {
      title: '連線尚未驗證成功',
      description: '請檢查服務地址和 API Key，再到連線設定中重試。',
    },
    managementRequired: {
      title: '需要獨立管理授權',
      description:
        '開源管理功能需要管理連線與對應許可權。火山管理功能需要獨立管理後端。',
    },
    unknownProvider: {
      title: '請確認服務型別',
      description:
        '該自定義地址沒有明確的服務標識，請在連線設定中指定服務型別後繼續使用。',
    },
    unavailable: {
      title: '當前服務未開放此功能',
      description: '你仍可瀏覽自己的目錄並使用其他可用功能。',
    },
    forbidden: {
      title: '當前身份沒有訪問許可權',
      description: '當前連線沒有授予此功能需要的讀取許可權。',
    },
    unknown: {
      title: '此功能的可用性尚未確認',
      description: '當前連線的擴充套件介面契約尚未驗證，不影響公共工作區。',
    },
  },
} as const
export default studio

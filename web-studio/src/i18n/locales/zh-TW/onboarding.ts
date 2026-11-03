export default {
  directoryOptions: '選擇其他資料身份（進階）',
  rootSetupTitle: '開始使用工作臺',
  rootSetupDescription:
    'Root Key 用於管理服務，不能直接訪問使用者資料。當前 Account：{{account}}。建立使用身份後，可在憑據結果中進入工作臺；團隊成員的身份不會自動替換你的工作臺身份。',
  rootSetupCreate: '建立使用身份',
  rootSetupExisting: '配置已有 User Key',
  verifyDirectoryHint:
    '可選。需要額外的管理許可權時填寫。Account Admin 管理本 Account，Root 管理服務與所有 Account。',
  loadDirectory: '載入 Account 和 User',
  directoryHint: '使用 Root 或 Admin API Key 瀏覽可選身份。',
  directoryControlRequired:
    '請輸入有效的 Root 或 Admin API Key 後加載帳號和使用者。',
  directoryLoadFailed: '載入身份失敗，請檢查管理金鑰和服務地址後重試。',
  directoryAccount: '選擇 Account',
  directoryUser: '選擇 User',
  directoryAdminHint:
    'Admin Key 僅可選擇所屬 Account 中的使用者。訪問資料還需填寫該使用者的 API Key。',
  directoryKeyHint:
    '選擇身份不會自動授予資料許可權。請填寫對應的 User API Key；留空則僅進入帳號管理。',
  directoryIdentityMismatch:
    '此 User API Key 屬於其他帳號或使用者，請輸入所選身份對應的金鑰。',

  openSourceConnection: 'OpenSource',
  cancel: '取消',
  exit: '退出 Studio',
  connectionTitle: '連線 Business Context Platform 服務。',
  preferencesHint: '選擇你熟悉的語言與外觀。',
  connectionHint: '連線並驗證你的 Business Context Platform 服務。',

  verifiedManagement:
    '管理許可權驗證成功。進入使用者管理後可建立使用者 API 金鑰。',
  brand: 'Business Context Platform',
  invalidService: '這個地址未返回有效的 Business Context Platform 服務資訊。',
  keyRequired: '此服務需要 API Key，請填寫後重試。',

  savedWorkspaces: '已有連線',
  newAddressHint: '輸入有效的 HTTP 或 HTTPS 地址後可繼續。',
  preferences: '基礎偏好',
  connection: '連線服務',
  welcome: '歡迎使用\nBusiness Context Platform',
  connectionDescription: '配置服務連線。驗證成功後，將顯示對應的工作區和功能。',
  verify: '驗證連線',
  verifying: '正在驗證…',
  verified: '連線驗證成功',
  verifyFailed: '連線驗證失敗：',
  healthRequestFailed: '檢查服務健康狀態時失敗：',
  dataRequestFailed: '檢查記憶訪問許可權時失敗：',
  enter: '進入 Studio',
  keyLabel: 'API Key',
  keyHelp:
    '可填寫 User、Account Admin 或 Root Key，驗證後自動識別權限和身份。開發模式無需填寫。',
  advanced: '開源進階連線配置（選填）',
  loadUsers: '讀取此帳號的使用者',
  loadingUsers: '正在讀取使用者…',
  chooseUser: '選擇使用者',
  noUsers: '該帳號下沒有可選使用者，請檢查帳號 ID 或手動填寫使用者 ID。',
  usersDevMode:
    '當前服務為開發模式，不提供使用者列表。請手動填寫帳號和使用者 ID；服務會按這兩個值訪問對應空間。',
  usersNeedKey:
    '此服務需要 Root 或管理員 API 金鑰才能列出使用者。填入金鑰後再試。',
  usersUnavailable:
    '無法讀取使用者列表，請檢查管理金鑰和帳號，或手動填寫使用者 ID。',
  userSelectionHint:
    '填寫管理金鑰後可讀取使用者列表；開發模式或無管理許可權時，請手動填寫帳號和使用者 ID。API Key 模式下還需要對應使用者的金鑰。',
  storageError: '無法儲存配置，請允許此站點使用瀏覽器本地儲存後重試。',
}

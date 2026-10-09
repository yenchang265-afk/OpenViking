const activity = {
  sessions: {
    page: {
      placeholder: '會話和 VikingBot 工作區功能正在開發中。',
    },
    threadList: {
      title: '會話',
      newSession: '新建會話',
      count: '{{count}} 個會話',
      count_other: '{{count}} 個會話',
      loading: '正在載入會話...',
      emptyTitle: '還沒有會話',
      emptyDescription: '點選右上角的加號開始一段新對話。',
      deleteSession: '刪除“{{title}}”',
      deleteConfirmTitle: '刪除會話？',
      deleteConfirmDescription:
        '“{{title}}”及其對話記錄將被永久刪除，此操作無法撤銷。',
      cancel: '取消',
      confirmDelete: '刪除',
      deleting: '正在刪除...',
      deleteSuccess: '會話已刪除',
      deleteFailed: '會話刪除失敗：{{error}}',
      shortcut: '⌘ N 新建會話',
    },
    chat: {
      historyLoadFailed: '會話記錄載入失敗：{{error}}',
      sendFailed: '訊息傳送失敗：{{error}}',
      copy: '複製',
      emptyDescription: '探索你的知識庫，開始一段對話。',
      placeholder: '輸入訊息...',
      emptyState: '選擇或建立一個會話開始聊天。',
      thinking: '思考中...',
      reasoning: '思考過程',
      iteration: '第 {{count}} 輪',
      toolCall: '工具呼叫',
      toolInput: '輸入',
      toolResult: '結果',
      loadMoreRefs: '載入更多 {{count}} 條（剩餘 {{remaining}} 條）',
      relativeTime: {
        justNow: '剛剛',
        minutesAgo: '{{count}} 分鐘前',
        minutesAgo_other: '{{count}} 分鐘前',
        hoursAgo: '{{count}} 小時前',
        hoursAgo_other: '{{count}} 小時前',
        daysAgo: '{{count}} 天前',
        daysAgo_other: '{{count}} 天前',
      },
      toolStatus: {
        completed: '完成',
        failed: '失敗',
        running: '執行中...',
      },
      send: '傳送',
      cancel: '停止',
      // Streamdown control labels; keys match StreamdownTranslations.
      markdown: {
        close: '關閉',
        copied: '已複製',
        copyCode: '複製程式碼',
        copyLink: '複製連結',
        copyTable: '複製表格',
        copyTableAsCsv: '以 CSV 複製表格',
        copyTableAsMarkdown: '以 Markdown 複製表格',
        copyTableAsTsv: '以 TSV 複製表格',
        downloadDiagram: '下載圖表',
        downloadDiagramAsMmd: '以 MMD 下載圖表',
        downloadDiagramAsPng: '以 PNG 下載圖表',
        downloadDiagramAsSvg: '以 SVG 下載圖表',
        downloadFile: '下載檔案',
        downloadImage: '下載圖片',
        downloadTable: '下載表格',
        downloadTableAsCsv: '以 CSV 下載表格',
        downloadTableAsMarkdown: '以 Markdown 下載表格',
        exitFullscreen: '結束全螢幕',
        externalLinkWarning: '即將前往外部網站。',
        imageNotAvailable: '圖片無法使用',
        openExternalLink: '要開啟外部連結嗎？',
        openLink: '開啟連結',
        resetView: '重設縮放與平移',
        viewFullscreen: '全螢幕檢視',
        zoomIn: '放大',
        zoomOut: '縮小',
      },
    },
    impact: {
      title: '記憶影響',
      open: '檢視本次會話造成的記憶影響',
      description: '由 {{commits}} 次提交產生 {{changes}} 項記憶變更',
      kinds: {
        add: '新增',
        update: '更新',
        delete: '刪除',
      },
      allTypes: '全部',
      filterByType: '按記憶分類篩選',
      before: '變更前',
      after: '變更後',
      addedContent: '新增內容',
      deletedContent: '刪除內容',
      emptyContent: '沒有可展示的內容',
      loading: '正在載入記憶變更...',
      loadFailed: '記憶變更載入失敗',
      retry: '重試',
      empty: '本次會話提交沒有產生記憶變更。',
      viewExperienceImpact: '檢視該經驗的應用效果',
    },
    empty: {
      description: '從左側選擇一個會話，或建立新會話。',
      title: '未選擇會話',
    },
  },
  oauth: {
    identityPicker: {
      useCurrent: '以當前身份授權',
      noCurrent:
        '尚未配置身份。請先在“連線設定”中配置身份憑證，或在下方臨時貼上一個 API 金鑰。',
      useSelect: '授權指定的帳號 / 使用者',
      selectAccountLabel: '帳號',
      selectUserLabel: '使用者',
      selectNoKey:
        '該使用者沒有 API 金鑰，請選擇其他使用者，或在“連線設定”中重新生成 API 金鑰。',
      selectAccountAdminHint: '你只能為本帳號下的使用者授權。',
      useCustom: '使用其他 API 金鑰',
      customKeyLabel: 'API 金鑰',
      customKeyPlaceholder: '貼上一個 API 金鑰（不會持久化）',
    },
    consent: {
      title: '授權 {{clientName}}',
      loading: '正在載入授權請求…',
      expired: '此次授權已過期或不再有效，請從 MCP 客戶端重新發起。',
      missingPending: '缺少授權 ID，請開啟 MCP 客戶端給出的連結。',
      requestSummary:
        '{{clientName}} 請求訪問你的 Business Data Platform 工作區。',
      redirectLabel: '回跳地址',
      scopesLabel: '許可權範圍',
      scopesNone: '（無）',
      signInRequired:
        '請先在“連線設定”中配置 Business Data Platform 身份憑證，或在下方臨時貼上 API 金鑰完成授權。',
      openConnectionSettings: '開啟連線設定',
      authorize: '授權',
      deny: '拒絕',
      useAnotherDevice: '在另一臺裝置上授權 →',
      waitingRedirect: '已授權——正在回跳到客戶端…',
      verifying: '正在驗證…',
      denying: '正在拒絕…',
      denied: '已拒絕，可以關閉此頁。',
      verifyError: '授權失敗：{{message}}',
      noApiKey: '沒有可用的 API 金鑰。請選擇一個身份或貼上金鑰。',
    },
    verify: {
      title: '跨裝置驗證',
      description: '請輸入發起 MCP 客戶端登入的那臺裝置上顯示的 6 位驗證碼。',
      codeLabel: '驗證碼',
      codePlaceholder: '6 位驗證碼',
      submit: '授權',
      success: '已為 {{clientName}} 授權，可以關閉此頁並回到原裝置。',
      successUnknownClient: '已授權，可以關閉此頁並回到原裝置。',
      verifyError: '授權失敗：{{message}}',
      noApiKey: '沒有可用的 API 金鑰。請選擇一個身份或貼上金鑰。',
      signInRequired:
        '請先在“連線設定”中配置 Business Data Platform 身份憑證，或在下方臨時貼上 API 金鑰完成驗證。',
    },
  },
  playground: {
    copyUri: '複製當前 URI',
    uploadedBy: '上傳者：{{user}}',
    updatedBy: '最後更新者：{{user}}',
    copied: '已複製 URI',
    copyFailed: '複製失敗',
    resizeContext: '調整上下文樹寬度',
    resizeAction: '調整終端和 Agent 面板寬度',
    readFailed: '無法讀取 {{uri}}',
    deleteResource: {
      label: '刪除資源',
      title: '確定要刪除此資源？',
      fileDescription: '{{uri}} 將被永久刪除，此操作無法復原。',
      directoryDescription:
        '{{uri}} 及其中所有內容將被永久刪除，此操作無法復原。',
      cancel: '取消',
      confirm: '刪除',
      deleting: '正在刪除…',
      deleted: '資源已刪除',
      failed: '刪除失敗：{{error}}',
    },
    reindex: {
      title: '確定要重建此資源的索引？',
      fileDescription: '重建 {{uri}} 的搜尋索引。',
      directoryDescription: '重建 {{uri}} 及其中所有內容的搜尋索引。',
      modeLabel: '重建模式',
      modes: {
        vectors_only: {
          title: '僅向量',
          description: '以現有內容與摘要重新產生向量。適用於更換嵌入模型後。',
        },
        semantic_and_vectors: {
          title: '摘要與向量',
          description:
            '先以 VLM 重新產生 L0/L1 摘要，再重新產生向量。較慢且會呼叫模型。',
        },
      },
      cancel: '取消',
      confirm: '開始重建',
      starting: '正在啟動…',
      started: '已開始重建索引',
      viewTasks: '檢視任務',
      failed: '重建索引失敗：{{error}}',
    },
    tabs: {
      terminal: '終端',
      agent: 'Agent',
    },
    actionPanel: {
      collapse: '收起面板',
      expand: '展開面板',
    },
    addResource: {
      title: '新增資源',
      description:
        '新增完成後左側上下文樹會重新整理，右側終端可繼續定位新資源。',
      submitted: '資源新增任務已提交',
    },
    explorer: {
      title: '上下文樹',
      addResource: '新增資源',
      abstractLevel: 'L0',
      collapseDirectory: '收起 {{name}}',
      empty: '空',
      expandDirectory: '展開 {{name}}',
      loading: '載入中',
      overviewLevel: 'L1',
      search: '搜尋上下文',
      refresh: '重新整理上下文樹',
      namespaces: {
        agent: 'Agent 的能力、工具和經驗',
        user: '使用者個性化記憶',
        resources: 'Agent 可引用的外部資源',
      },
      menu: {
        label: '{{name}} 的操作',
        open: '開啟',
        newFile: '新增檔案…',
        newFolder: '新增資料夾…',
        rename: '重新命名…',
        copyUri: '複製 URI',
        refresh: '重新整理',
        reindex: '重建索引…',
        delete: '刪除…',
      },
      nameDialog: {
        newFileTitle: '新增檔案',
        newFolderTitle: '新增資料夾',
        renameTitle: '重新命名',
        createIn: '建立於 {{uri}}',
        renameFrom: '重新命名 {{uri}}',
        nameLabel: '名稱',
        filePlaceholder: 'notes.md',
        fileHint: '允許的副檔名：{{extensions}}',
        cancel: '取消',
        create: '建立',
        creating: '正在建立…',
        rename: '重新命名',
        renaming: '正在重新命名…',
        created: '已建立 {{name}}',
        renamed: '已重新命名為 {{name}}',
        failed: '失敗：{{error}}',
        errors: {
          required: '請輸入名稱。',
          invalidChars: '名稱不可包含斜線或控制字元。',
          reserved: '「.」和「..」為保留名稱。',
          tooLong: '名稱最多 255 個字元。',
          extension: '請使用下列副檔名之一：{{extensions}}',
          exists: '此處已存在 {{name}}。',
        },
      },
    },
    agent: {
      history: '歷史會話',
      newSession: '新建會話',
      creating: '正在建立工作臺會話...',
      detectingBot: '正在檢查 VikingBot 是否可用...',
      createFailed: '建立會話失敗：{{error}}',
      retry: '重試',
      botDisabledFooter: '啟用 VikingBot 後即可與 Agent 對話',
      historyTitle: 'Agent 會話歷史',
      historyDescription:
        '工作臺與 VikingBot 共用對話記錄，也包含當前瀏覽器儲存的舊 Agent 會話。',
      loadingSessions: '正在載入會話...',
      noSessions: '暫無歷史會話',
      createTimeout: '建立工作臺會話超時，請檢查連線設定後重試。',
      newSessionTitle: '新建工作臺會話',
      botPrompt: {
        title: '請啟用 VikingBot',
        description:
          '當前服務未啟用 Agent 對話功能。請使用以下引數啟動服務後重試。',
        command: 'openviking-server --with-bot',
        retry: '重新檢測',
      },
      empty: {
        heading: 'Agent 操作會與左側目錄聯動',
        body: '傳送問題後，工具呼叫輸出裡的 `viking://` 檔案會變成可點選連結，點選即可在左側定位並在中間開啟。',
        prompts: [
          '總結當前目錄',
          '遞迴查詢相關文件',
          '解釋這個資源和專案的關係',
        ],
      },
    },
    terminal: {
      header: '終端',
      history: '命令歷史',
      historyTitle: '命令歷史',
      historyDescription: '檢視當前瀏覽器中執行過的命令。',
      clearHistory: '清空命令歷史',
      noHistory: '暫無命令歷史',
      welcomeTitle: '終端已連線上下文樹',
      welcomeBody:
        '可執行 /status、/ls、/search、/read、/add-resource。/search 預設全域檢索，可通過 --scope . 使用當前目錄，或通過 --scope viking://resources/... 指定目錄。',
      scopeLabel: '目錄：{{uri}}',
      globalScope: '全域',
      opened: '已開啟資源',
      onlineTitle: '服務線上',
      onlineBody:
        'Business Data Platform API 正常響應，根目錄下發現 {{count}} 個節點。',
      lsBody: '{{uri}} 下共展示 {{count}} 個節點。',
      fileEmpty: '檔案為空，已在中間預覽區開啟。',
      searchUsage: '用法：{{name}} 查詢詞 [--scope .|viking://resources/...]',
      searchScopeLine: '搜尋範圍：{{scope}}',
      helpParameters: '引數',
      helpExamples: '示例',
      helpSubcommands: '子命令',
      noParameters: '無引數',
      currentScopeAction: '使用當前目錄',
      readUsage: '用法：/read viking://resources/...',
      enterUri: '請輸入 viking:// URI',
      hits: '命中資源 {{resources}} 條、記憶 {{memories}} 條、技能 {{skills}} 條。',
      addResourceBody:
        '已開啟新增資源彈窗。提交後左側目錄會重新整理，也可以用 /ls 或 /search 繼續定位新內容。',
      addResourceTitle: '新增資源',
      sessionUsage:
        '用法：/session [current|list|create|switch|get|context|messages|archive|commit|extract|message|tool-results|tool-result|tool-search|delete] ...',
      sessionDeleteUsage: '用法：/session delete <session_id>',
      sessionMissing:
        '當前沒有會話，請先開啟 Agent 面板建立會話，或指定 session_id。',
      sessionCurrentBody: '當前會話：{{id}}',
      sessionListBody: '共有 {{count}} 個會話。',
      sessionCreatedBody: '已建立並切換到會話：{{id}}',
      sessionSwitchedBody: '已切換到會話：{{id}}',
      sessionDeletedBody: '已刪除會話：{{id}}',
      sessionMessageAddedBody: '已向會話 {{id}} 新增訊息。',
      unknownCommand:
        '未知命令。可用命令：/status、/ls、/search、/find、/read、/session、/add-resource。',
      commandFailed: '命令失敗',
      waitUsage: '用法：/wait [--timeout 秒數]',
      invalidFlag: '無效的 --{{flag}}：{{value}}',
      refMeta: {
        archive: '歸檔',
        dir: '目錄',
        session: '會話',
        toolResult: '工具結果',
        toolSearch: '工具搜尋',
      },
      running: '正在執行命令...',
      placeholder: '輸入 CLI 命令，例如 /status',
      suggestionsTitle: '命令建議',
      suggestionsHint: '↑↓ 選擇 · Tab 補全 · Enter 執行',
      quickStart: {
        title: '快速開始',
        addResource: {
          title: '新增資源',
          command: '/add-resource',
          code: '匯入文件或檔案到 viking://resources',
        },
        addMemory: {
          title: '新增記憶',
          command: '通過 Agent 會話提取記憶',
          code: '在 Agent 面板傳送訊息，然後提交會話',
        },
        find: {
          title: '查詢相關上下文',
          command: '/find openviking 價值',
          code: '在當前範圍內搜尋資源、記憶和技能',
        },
      },
      commandGroups: {
        core: '核心命令',
        filesystem: '檔案系統',
        search: '搜尋與摘要',
        status: '狀態',
        resource: '資源路徑',
        history: '歷史記錄',
      },
      commandParameters: {
        query: {
          name: '查詢詞',
          description: '要檢索的關鍵詞或語義問題。',
        },
        scope: {
          name: '--scope <.|uri>',
          description:
            '可選。不填則全域搜尋；傳入 . 使用當前目錄，傳入 URI 使用指定目錄。',
        },
        sessionAction: {
          name: '子命令',
          description:
            'current、list、create、switch、get、context、messages、archive、commit、extract、message、tool-results、tool-result、tool-search、delete。',
        },
        sessionId: {
          name: 'session_id',
          description:
            '可選。省略時，多數子命令使用當前 Agent 會話；delete 必須顯式指定。',
        },
        archiveId: {
          name: 'archive_id',
          description: '讀取會話歸檔時必填。',
        },
        messageRole: {
          name: 'role',
          description: '用於 message 子命令，角色值支援 user 或 assistant。',
        },
        messageContent: {
          name: 'content',
          description: '用於 message 子命令，指定要追加到會話的文本內容。',
        },
        keepRecent: {
          name: '--keep-recent 數量',
          description: '用於 commit 子命令，提交後保留最近 N 條未歸檔訊息。',
        },
        tokenBudget: {
          name: '--token-budget 數量',
          description: '用於 context 子命令，限制組裝上下文的 Token 預算。',
        },
        toolName: {
          name: '--tool-name 名稱',
          description: 'tool-results 子命令使用，按工具名過濾。',
        },
        toolResultId: {
          name: 'tool_result_id',
          description: '讀取或搜尋外部化工具結果時必填。',
        },
        limit: {
          name: '--limit 數量',
          description: '用於限制工具結果列表、讀取或搜尋的返回數量。',
        },
        offset: {
          name: '--offset 數量',
          description: 'tool-result 子命令使用，從指定字元偏移開始讀取。',
        },
        contextChars: {
          name: '--context-chars 數量',
          description: 'tool-search 子命令使用，控制命中上下文長度。',
        },
        timeout: {
          name: '--timeout 秒',
          description: '可選。等待服務就緒的最長時間。',
        },
        uri: {
          name: 'uri',
          description: '可選或必填的 viking:// 資源路徑，取決於命令用法。',
        },
      },
      commandExamples: {
        status: {
          default: {
            code: '/status',
            description: '檢查 Agent 和 API 的連通狀態',
          },
        },
        ls: {
          current: {
            code: '/ls',
            description: '列出當前目錄',
          },
          target: {
            code: '/ls viking://resources/',
            description: '列出指定目錄',
          },
        },
        search: {
          global: {
            code: '/search agent',
            description: '全域語義檢索',
          },
          current: {
            code: '/search agent --scope .',
            description: '使用當前高亮目錄',
          },
          scoped: {
            code: '/search agent --scope viking://resources/',
            description: '只在指定目錄檢索',
          },
        },
        find: {
          global: {
            code: '/find agent',
            description: '全域查詢相關資源',
          },
          current: {
            code: '/find agent --scope .',
            description: '使用當前高亮目錄',
          },
          scoped: {
            code: '/find agent --scope viking://resources/',
            description: '只在指定目錄查詢',
          },
        },
        read: {
          file: {
            code: '/read viking://resources/file.md',
            description: '讀取並開啟檔案',
          },
        },
        addResource: {
          default: {
            code: '/add-resource',
            description: '開啟新增資源表單',
          },
        },
        session: {
          current: {
            code: '/session',
            description: '檢視當前會話',
          },
          list: {
            code: '/session list',
            description: '列出所有會話',
          },
          create: {
            code: '/session create [session_id]',
            description: '建立並切換到新會話',
          },
          switch: {
            code: '/session switch <session_id>',
            description: '切換 Agent 面板會話',
          },
          get: {
            code: '/session get [session_id]',
            description: '檢視會話後設資料',
          },
          context: {
            code: '/session context [session_id] --token-budget 8000',
            description: '讀取組裝後的會話上下文',
          },
          messages: {
            code: '/session messages [session_id]',
            description: '讀取會話訊息列表',
          },
          archive: {
            code: '/session archive [session_id] <archive_id>',
            description: '讀取指定會話歸檔',
          },
          commit: {
            code: '/session commit [session_id] --keep-recent 10',
            description: '歸檔並觸發記憶提取',
          },
          extract: {
            code: '/session extract [session_id]',
            description: '從會話中提取記憶',
          },
          message: {
            code: '/session message [session_id] user hello',
            description: '向會話追加訊息',
          },
          toolResults: {
            code: '/session tool-results [session_id] --limit 20',
            description: '列出外部化工具結果',
          },
          toolResult: {
            code: '/session tool-result [session_id] <tool_result_id>',
            description: '讀取一項外部化工具結果',
          },
          toolSearch: {
            code: '/session tool-search [session_id] <tool_result_id> query',
            description: '在外部化工具結果中搜索',
          },
          delete: {
            code: '/session delete <session_id>',
            description: '刪除指定會話',
          },
        },
        tree: {
          current: {
            code: '/tree',
            description: '展示當前目錄樹',
          },
          target: {
            code: '/tree viking://resources/',
            description: '展示指定目錄樹',
          },
        },
        stat: {
          target: {
            code: '/stat viking://resources/file.md',
            description: '檢視資源元資訊',
          },
        },
        abstract: {
          target: {
            code: '/abstract viking://resources/',
            description: '讀取目錄摘要',
          },
        },
        overview: {
          target: {
            code: '/overview viking://resources/',
            description: '讀取目錄概覽',
          },
        },
        health: {
          default: {
            code: '/health',
            description: '檢視後端健康狀態',
          },
        },
        wait: {
          default: {
            code: '/wait',
            description: '等待服務就緒',
          },
          timeout: {
            code: '/wait --timeout 30',
            description: '指定等待秒數',
          },
        },
      },
      resourceSuggestion: '資源路徑',
      historySuggestion: '歷史記錄',
      groupLabels: {
        resources: '資源',
        memories: '記憶',
        skills: '技能',
      },
      commands: {
        status: {
          description: '檢查連通狀態',
          usage: '/status',
        },
        ls: {
          description: '檢視已有資源',
          usage: '/ls [viking://resources/...]',
        },
        search: {
          description: '語義檢索上下文',
          usage: '/search 查詢詞',
        },
        find: {
          description: '查詢相關資源',
          usage: '/find 查詢詞',
        },
        read: {
          description: '讀取資源檔案',
          usage: '/read viking://resources/.../file.md',
        },
        addResource: {
          description: '新增外部資源',
          usage: '/add-resource',
        },
        session: {
          description: '管理 Agent 會話',
          usage: '/session 子命令',
        },
        tree: {
          description: '展示目錄樹',
          usage: '/tree [viking://resources/...]',
        },
        stat: {
          description: '檢視資源元資訊',
          usage: '/stat viking://resources/...',
        },
        abstract: {
          description: '讀取目錄摘要',
          usage: '/abstract viking://resources/...',
        },
        overview: {
          description: '讀取目錄概覽',
          usage: '/overview viking://resources/...',
        },
        health: {
          description: '檢視後端健康狀態',
          usage: '/health',
        },
        wait: {
          description: '等待服務就緒',
          usage: '/wait [--timeout seconds]',
        },
      },
    },
  },
} as const

export default activity

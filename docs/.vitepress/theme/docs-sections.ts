// Editorial ownership is independent of file location. Existing URLs stay stable.
// This manifest owns grouping and order; article labels come from Markdown H1.
// Top navigation, sidebars, breadcrumbs, the homepage and llms.txt share this structure.
export type Locale = 'en' | 'zh'
export type DocPage = { path: string; reference?: boolean; en?: string; zh?: string }
export type DocGroup = { en: string; zh: string; pages: DocPage[] }
export type DocSection = {
  id: string; en: string; zh: string; enNote: string; zhNote: string
  entry: string; aliases: string[]; groups: DocGroup[]
  nextSteps?: DocGroup[]
}
const p = (path: string): DocPage => ({ path })
const reference = (path: string, en: string, zh: string): DocPage => ({ path, reference: true, en, zh })
const g = (en: string, zh: string, pages: DocPage[]): DocGroup => ({ en, zh, pages })

export const sections: DocSection[] = [
  {
    id: 'getting-started', en: 'Quickstart', zh: '開始使用',
    enNote: 'Get a first result, evaluate it on your tasks, and choose what to connect.', zhNote: '完成首次體驗，用自己的任務驗證效果，再選擇接入路徑。',
    entry: 'getting-started/02-quickstart', aliases: [],
    groups: [
      g('Start', '開始', [
        p('getting-started/02-quickstart'),
        p('getting-started/01-introduction'),
        p('getting-started/07-agent-onboarding'),
        p('getting-started/05-cli-setup'),
        p('getting-started/07-options')
      ]),
      g('Studio', 'Studio', [
        p('getting-started/23-studio')
      ]),
      g('Features', '功能', [
        p('getting-started/08-resources'),
        p('getting-started/09-memory'),
        p('getting-started/10-skills'),
        p('getting-started/16-rules'),
        p('getting-started/06-evaluate')
      ]),
      g('Integrations', '整合', [
        reference('agent-integrations/01-overview', 'Agent integration', 'Agent 接入'),
        reference('workflows/01-overview', 'Application development', '應用開發'),
        p('getting-started/11-vikingbot'),
        p('getting-started/12-gateway')
      ]),
      g('Data management', '資料管理', [
        p('getting-started/13-compile'),
        p('getting-started/14-versions'),
        p('getting-started/15-transfer')
      ]),
      g('Team management', '團隊管理', [
        p('getting-started/17-authentication'),
        p('getting-started/18-accounts'),
        p('getting-started/19-users'),
        p('getting-started/20-peers'),
        p('getting-started/21-access-control'),
        p('getting-started/22-sharing')
      ])
    ]
  },
  {
    id: 'concepts', en: 'Concepts', zh: '概念與原理',
    enNote: 'Learn the context model, processing flow, architecture and governance.', zhNote: '從上下文模型到處理機制、系統架構與治理。',
    entry: 'concepts/00-overview', aliases: [],
    groups: [
      g('Context model', '基礎模型', [
        p('concepts/00-overview'),
        p('concepts/02-context-types'),
        p('concepts/04-viking-uri'),
        p('concepts/03-context-layers')
      ]),
      g('Processing and memory', '處理與記憶', [
        p('concepts/06-extraction'),
        p('concepts/07-retrieval'),
        p('concepts/08-session'),
        p('concepts/17-rule-scenarios')
      ]),
      g('Architecture and reliability', '架構與可靠性', [
        p('concepts/01-architecture'),
        p('concepts/05-storage'),
        p('concepts/16-queue-lifecycle'),
        p('concepts/09-transaction'),
        p('concepts/14-multi-write-storage'),
        p('concepts/12-metrics')
      ]),
      g('Identity and governance', '身份與治理', [
        p('concepts/11-multi-tenant'),
        p('concepts/15-acl'),
        p('concepts/10-encryption'),
        p('concepts/13-privacy')
      ]),
      g('Application example', '應用示例', [
        p('concepts/15-vikingbot')
      ])
    ]
  },
  {
    id: 'agent-integrations', en: 'Agents', zh: '接入 Agent',
    enNote: 'Choose an integration, connect it, and verify memory behavior.', zhNote: '選擇整合，完成接入，驗證記憶行為。',
    entry: 'agent-integrations/01-overview', aliases: [],
    groups: [
      g('Choose an integration', '選擇接入方式', [
        p('agent-integrations/01-overview'),
        p('agent-integrations/16-capability-reference'),
        p('agent-integrations/14-openviking-helper')
      ]),
      g('Coding tools', '程式設計工具', [
        p('agent-integrations/02-claude-code'),
        p('agent-integrations/04-codex'),
        p('agent-integrations/12-cursor'),
        p('agent-integrations/13-trae'),
        p('agent-integrations/10-opencode'),
        p('agent-integrations/17-dsh')
      ]),
      g('Agents and frameworks', 'Agent 與框架', [
        p('agent-integrations/03-openclaw'),
        p('agent-integrations/05-hermes'),
        p('agent-integrations/11-pi'),
        p('agent-integrations/07-langchain-langgraph'),
        p('agent-integrations/08-community-plugins')
      ]),
      g('Shared setup and tuning', '通用接入與調優', [
        p('agent-integrations/06-mcp-clients'),
        p('agent-integrations/15-agent-plugins'),
        p('agent-integrations/09-log-ingestion'),
        p('agent-integrations/19-recall-tuning'),
        p('agent-integrations/18-plugin-development'),
        p('guides/working-memory-default-off')
      ]),
      g('VikingBot', 'VikingBot', [
        p('guides/17-vikingbot'),
        p('guides/12-vikingbot-metrics-validation')
      ])
    ],
    nextSteps: [
      g('Clients without a plugin', '沒有外掛的客戶端', [
        p('guides/15-gateway')
      ])
    ]
  },
  // The entry page and the deployment page keep their guides/ paths so released Studio builds,
  // the Helm README and openviking_gateway/config.py keep linking to them; every other gateway
  // page lives in gateway/. Ownership does not depend on file location (see the top of this file).
  {
    id: 'gateway', en: 'Gateway', zh: '閘道器',
    enNote: 'Give any API-key client memory through one proxy, then manage and run it.', zhNote: '用一個代理為 API Key 客戶端接入記憶，並管理與運維。',
    entry: 'guides/15-gateway', aliases: [],
    groups: [
      g('Understand the gateway', '瞭解閘道器', [
        p('guides/15-gateway'),
        p('gateway/01-how-it-works')
      ]),
      g('Get started', '上手與接入', [
        p('gateway/02-quickstart'),
        p('gateway/03-connect-clients')
      ]),
      g('Memory and tools', '記憶與工具', [
        p('gateway/04-openviking-tools'),
        p('gateway/05-long-conversations')
      ]),
      g('Manage in Studio', '在 Studio 中管理', [
        p('gateway/06-manage-in-studio'),
        p('gateway/07-upstreams'),
        p('gateway/08-context-profiles'),
        p('gateway/09-gateway-keys'),
        p('gateway/10-overview-and-requests')
      ]),
      g('Deploy and operate', '部署與運維', [
        p('guides/22-gateway-operations'),
        p('gateway/11-security-and-data')
      ]),
      g('Troubleshoot and look up', '排障與參考', [
        p('gateway/12-troubleshooting'),
        p('gateway/13-configuration')
      ])
    ],
    nextSteps: [
      g('Related docs', '相關文件', [
        p('api/25-gateway'),
        p('guides/04-authentication'),
        p('guides/12-public-access'),
        p('guides/06-mcp-integration'),
        p('agent-integrations/01-overview')
      ])
    ]
  },
  {
    id: 'build', en: 'Develop', zh: '開發應用',
    enNote: 'Turn resources and sessions into reusable context and outputs.', zhNote: '把資源和會話用於檢索、記憶與內容產出。',
    entry: 'workflows/01-overview', aliases: ['context-compilation'],
    groups: [
      g('Choose a workflow', '選擇開發任務', [
        p('workflows/01-overview')
      ]),
      g('Rule validation (Beta)', '規則校驗（Beta）', [
        p('workflows/02-rule-validation')
      ]),
      g('Manage context', '組織與維護上下文', [
        p('guides/23-data-organize'),
        p('guides/18-openviking-assets'),
        p('guides/09-ovpack'),
        p('guides/15-snapshot'),
        p('guides/10-prompt-guide')
      ]),
      g('Compile context into outputs', '編譯上下文', [
        p('context-compilation/01-overview'),
        p('context-compilation/02-llm-wiki'),
        p('context-compilation/03-knowledge-graph'),
        p('context-compilation/04-daily-report'),
        p('context-compilation/05-knowledge-distillation'),
        p('context-compilation/06-memory-consolidation')
      ])
    ]
  },
  {
    id: 'operate', en: 'Deploy', zh: '部署運維',
    enNote: 'Deploy a service, control access, monitor it, and upgrade it.', zhNote: '部署服務，配置訪問控制，監控與升級。',
    entry: 'guides/00-overview', aliases: ['guides', 'faq'],
    groups: [
      g('Deploy a service', '部署服務', [
        p('guides/00-overview'),
        p('guides/19-deployment-checklist'),
        p('guides/03-deployment'),
        p('getting-started/04-setup-for-agent'),
        p('guides/01-configuration'),
        p('guides/02-volcengine-purchase-guide')
      ]),
      g('Secure access', '訪問與安全', [
        p('guides/04-authentication'),
        p('guides/12-public-access'),
        p('guides/11-oauth'),
        p('guides/08-encryption')
      ]),
      g('Observe and troubleshoot', '觀測與排障', [
        p('guides/05-observability'),
        p('guides/07-operation-telemetry'),
        p('guides/11-grafana-prometheus'),
        p('faq/faq')
      ]),
      g('Storage and performance', '儲存與效能', [
        p('guides/13-multi-write-storage'),
        p('guides/14-ragfs-cache'),
        p('guides/16-cuvs')
      ])
    ]
  },
  {
    id: 'reference', en: 'Reference', zh: '參考',
    enNote: 'Look up API contracts, protocol details and configuration fields.', zhNote: '查介面約定、協議和配置欄位。',
    entry: 'reference/01-overview', aliases: ['api', 'configuration'],
    groups: [
      g('Reference and configuration', '參考入口與配置', [
        p('reference/01-overview'),
        p('api/01-overview'),
        p('configuration/01-server'),
        p('configuration/02-client'),
        p('guides/06-mcp-integration')
      ]),
      g('Resources and retrieval APIs', '資源與檢索 API', [
        p('api/02-resources'),
        p('api/12-content'),
        p('api/03-filesystem'),
        p('api/06-retrieval'),
        p('api/15-watches')
      ]),
      g('Sessions, memory and skills APIs', '會話、記憶與技能 API', [
        p('api/05-sessions'),
        p('api/16-memory'),
        p('api/04-skills'),
        p('api/19-agent-evolution')
      ]),
      g('Rules (Beta)', '規則（Beta）', [
        p('api/26-rules')
      ]),
      g('Data and extension APIs', '資料與擴充 API', [
        p('api/11-snapshot'),
        p('api/14-ovpack'),
        p('api/22-openviking-assets'),
        p('api/20-webdav'),
        p('api/23-agent-runtime'),
        p('api/24-vikingbot')
      ]),
      g('Administration and operations APIs', '管理與運維 API', [
        p('api/08-admin'),
        p('api/25-gateway'),
        p('api/12-acl'),
        p('api/10-privacy'),
        p('api/07-system'),
        p('api/17-tasks'),
        p('api/18-observer'),
        p('api/09-metrics')
      ])

    ]
  },
  {
    id: 'project', en: 'Community', zh: '社群',
    enNote: 'Follow releases and contribute to the project.', zhNote: '瞭解版本變化，參與專案與文件維護。',
    entry: 'about/01-about-us', aliases: ['about'],
    groups: [
      g('Community and releases', '社群與版本', [
        p('about/01-about-us'),
        p('about/02-changelog'),
        p('about/03-roadmap')
      ]),
      g('Contribute documentation', '參與文件維護', [
        p('api/99-api-doc-writing-guide')
      ])
    ]
  }
]

// This retired page is kept for inbound links, but is not a second tutorial.
export const legacyPages: Record<string, string> = {
  'getting-started/03-quickstart-server': 'getting-started'
}

export function sectionForPage(relativePath: string): DocSection | undefined {
  const path = relativePath.replace(/^(en|zh)\//, '').replace(/\.md$/, '')
  return sections.find(section => section.groups.some(group => group.pages.some(page => !page.reference && page.path === path)))
    || sections.find(section => section.id === legacyPages[path])
}

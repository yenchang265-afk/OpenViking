import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { DefaultTheme } from 'vitepress'
const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const sectionNames: Record<string, string> = {
  'getting-started': 'Getting Started',
  configuration: 'Configuration',
  concepts: 'Concepts',
  guides: 'Guides',
  'agent-integrations': 'Agent Integrations',
  'context-compilation': 'Context Compilation',
  migration: 'Migration',
  api: 'API Reference',
  faq: 'FAQ',
  about: 'About',
  design: 'Design Notes'
}

const zhSectionNames: Record<string, string> = {
  'getting-started': '開始使用',
  configuration: '配置',
  concepts: '核心概念',
  guides: '指南',
  'agent-integrations': 'Agent 集成',
  'context-compilation': '上下文編譯',
  migration: '遷移指南',
  api: 'API 參考',
  faq: '常見問題',
  about: '關於',
  design: '設計文件'
}

export function titleFromMarkdown(filePath: string): string {
  const content = fs.readFileSync(filePath, 'utf8')
  const heading = content.match(/^#\s+(.+)$/m)?.[1]
  const fallback = path.basename(filePath, '.md')
  return (heading || fallback).replace(/^\d+[-_]/, '').trim()
}

function linkFor(filePath: string): string {
  const relativePath = path.relative(docsRoot, filePath).replaceAll(path.sep, '/')
  return `/${relativePath.replace(/\.md$/, '')}`
}

export function sidebarSection(dir: string, title: string, collapsed = true): DefaultTheme.SidebarItem {
  const absoluteDir = path.join(docsRoot, dir)
  const items = fs
    .readdirSync(absoluteDir)
    .filter((file) => file.endsWith('.md'))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    .map((file) => {
      const filePath = path.join(absoluteDir, file)
      return {
        text: titleFromMarkdown(filePath),
        link: linkFor(filePath)
      }
    })

  return { text: title, collapsed, items }
}

const gettingStartedSidebar = {
  en: [
    ['01-introduction.md', 'Introduction'],
    ['02-quickstart.md', 'Quick Start'],
    ['04-setup-for-agent.md', 'Server Setup for Agent'],
    ['05-cli-setup.md', 'Business Data Platform CLI']
  ],
  zh: [
    ['01-introduction.md', '簡介'],
    ['02-quickstart.md', '快速開始'],
    ['04-setup-for-agent.md', '服務端安裝（Agent 版）'],
    ['05-cli-setup.md', 'Business Data Platform CLI']
  ]
} as const

const agentIntegrationSidebar = {
  en: {
    overview: 'Integration Overview',
    topItems: [
      ['16-capability-reference.md', 'Capability Reference'],
      ['18-plugin-development.md', 'Plugin Development']
    ],
    groups: [
      {
        text: 'Developer Tools',
        items: [
          ['02-claude-code.md', 'Claude Code'],
          ['04-codex.md', 'Codex'],
          ['10-opencode.md', 'OpenCode'],
          ['12-cursor.md', 'Cursor'],
          ['13-trae.md', 'TRAE / TRAE CN'],
          ['17-dsh.md', 'DeepSeek Harness']
        ]
      },
      {
        text: 'Agents & Frameworks',
        items: [
          ['03-openclaw.md', 'OpenClaw'],
          ['05-hermes.md', 'Hermes'],
          ['07-langchain-langgraph.md', 'LangChain / LangGraph'],
          ['11-pi.md', 'pi']
        ]
      },
      {
        text: 'General Integration',
        items: [
          ['14-openviking-helper.md', 'Business Data Platform Helper'],
          ['15-agent-plugins.md', 'Agent Plugins 1.0'],
          ['06-mcp-clients.md', 'MCP Clients'],
          ['09-log-ingestion.md', 'Local Log Import'],
          ['08-community-plugins.md', 'Community Integrations']
        ]
      }
    ]
  },
  zh: {
    overview: '整合概覽',
    topItems: [
      ['16-capability-reference.md', '整合能力參考'],
      ['18-plugin-development.md', '外掛開發與維護']
    ],
    groups: [
      {
        text: '開發工具',
        items: [
          ['02-claude-code.md', 'Claude Code'],
          ['04-codex.md', 'Codex'],
          ['10-opencode.md', 'OpenCode'],
          ['12-cursor.md', 'Cursor'],
          ['13-trae.md', 'TRAE / TRAE CN'],
          ['17-dsh.md', 'DeepSeek Harness']
        ]
      },
      {
        text: 'Agent 與框架',
        items: [
          ['03-openclaw.md', 'OpenClaw'],
          ['05-hermes.md', 'Hermes'],
          ['07-langchain-langgraph.md', 'LangChain / LangGraph'],
          ['11-pi.md', 'pi']
        ]
      },
      {
        text: '通用接入',
        items: [
          ['14-openviking-helper.md', 'Business Data Platform Helper'],
          ['15-agent-plugins.md', 'Agent Plugins 1.0'],
          ['06-mcp-clients.md', 'MCP 客戶端'],
          ['09-log-ingestion.md', '本地日誌匯入'],
          ['08-community-plugins.md', '社群整合']
        ]
      }
    ]
  }
} as const

const apiReferenceSidebar = {
  en: {
    overview: 'Overview',
    groups: [
      {
        text: 'Core Data',
        items: [
          ['02-resources.md', 'Resources'],
          ['12-content.md', 'Content'],
          ['03-filesystem.md', 'File System'],
          ['04-skills.md', 'Skills'],
          ['05-sessions.md', 'Sessions'],
          ['16-memory.md', 'Memory'],
          ['19-agent-evolution.md', 'Agent Evolution']
        ]
      },
      {
        text: 'Retrieval',
        items: [['06-retrieval.md', 'Retrieval']]
      },
      {
        text: 'Data Lifecycle',
        items: [
          ['15-watches.md', 'Resource Watches'],
          ['11-snapshot.md', 'Snapshots'],
          ['14-ovpack.md', 'OVPack']
        ]
      },
      {
        text: 'Operations & Observability',
        items: [
          ['07-system.md', 'System Status'],
          ['17-tasks.md', 'Background Tasks'],
          ['18-observer.md', 'Runtime Observability'],
          ['09-metrics.md', 'Metrics']
        ]
      },
      {
        text: 'Identity & Governance',
        items: [
          ['08-admin.md', 'Multi-Tenancy'],
          ['10-privacy.md', 'Privacy']
        ]
      },
      {
        text: 'Protocols & Extensions',
        items: [
          ['22-openviking-assets.md', 'Business Data Platform Assets'],
          ['20-webdav.md', 'WebDAV'],
          ['23-agent-runtime.md', 'Agent Runtime API'],
          ['24-vikingbot.md', 'VikingBot API']
        ]
      },
      {
        text: 'Documentation Maintenance',
        items: [['99-api-doc-writing-guide.md', 'API Docs Guide']]
      }
    ]
  },
  zh: {
    overview: '概覽',
    groups: [
      {
        text: '核心資料',
        items: [
          ['02-resources.md', '資源'],
          ['12-content.md', '內容'],
          ['03-filesystem.md', '檔案系統'],
          ['04-skills.md', '技能'],
          ['05-sessions.md', '會話'],
          ['16-memory.md', '記憶'],
          ['19-agent-evolution.md', 'Agent 進化']
        ]
      },
      {
        text: '檢索',
        items: [['06-retrieval.md', '檢索']]
      },
      {
        text: '資料生命週期',
        items: [
          ['15-watches.md', '資源 Watch'],
          ['11-snapshot.md', '快照'],
          ['14-ovpack.md', 'OVPack']
        ]
      },
      {
        text: '運維與觀測',
        items: [
          ['07-system.md', '系統狀態'],
          ['17-tasks.md', '後臺任務'],
          ['18-observer.md', '執行觀測'],
          ['09-metrics.md', '監控指標']
        ]
      },
      {
        text: '身份與治理',
        items: [
          ['08-admin.md', '多租戶'],
          ['10-privacy.md', '隱私配置']
        ]
      },
      {
        text: '協議與擴充',
        items: [
          ['22-openviking-assets.md', 'Business Data Platform Assets'],
          ['20-webdav.md', 'WebDAV'],
          ['23-agent-runtime.md', 'Agent Runtime API'],
          ['24-vikingbot.md', 'VikingBot API']
        ]
      },
      {
        text: '文件維護',
        items: [['99-api-doc-writing-guide.md', 'API 文件規範']]
      }
    ]
  }
} as const

const conceptsSidebar = {
  en: {
    overview: 'Overview',
    groups: [
      {
        text: 'Core Model',
        items: [
          ['02-context-types.md', 'Context Types'],
          ['03-context-layers.md', 'Context Layers'],
          ['04-viking-uri.md', 'Viking URI']
        ]
      },
      {
        text: 'Storage & Processing',
        items: [
          ['05-storage.md', 'Storage'],
          ['06-extraction.md', 'Extraction'],
          ['07-retrieval.md', 'Retrieval'],
          ['08-session.md', 'Sessions']
        ]
      },
      {
        text: 'Reliability & Governance',
        items: [
          ['09-transaction.md', 'Transactions & Recovery'],
          ['10-encryption.md', 'Encryption'],
          ['11-multi-tenant.md', 'Multi-Tenancy'],
          ['12-metrics.md', 'Metrics'],
          ['13-privacy.md', 'Privacy'],
          ['14-multi-write-storage.md', 'Multi-Write Storage'],
          ['16-queue-lifecycle.md', 'Queue State and Completion']
        ]
      },
      {
        text: 'Example',
        items: [['15-vikingbot.md', 'VikingBot']]
      }
    ]
  },
  zh: {
    overview: '概覽',
    groups: [
      {
        text: '核心模型',
        items: [
          ['02-context-types.md', '上下文型別'],
          ['03-context-layers.md', '上下文層級'],
          ['04-viking-uri.md', 'Viking URI']
        ]
      },
      {
        text: '儲存與處理',
        items: [
          ['05-storage.md', '儲存架構'],
          ['06-extraction.md', '上下文提取'],
          ['07-retrieval.md', '檢索機制'],
          ['08-session.md', '會話管理']
        ]
      },
      {
        text: '可靠性與治理',
        items: [
          ['09-transaction.md', '事務與恢復'],
          ['10-encryption.md', '資料加密'],
          ['11-multi-tenant.md', '多租戶'],
          ['12-metrics.md', '監控指標'],
          ['13-privacy.md', '隱私配置'],
          ['14-multi-write-storage.md', '多寫儲存'],
          ['16-queue-lifecycle.md', '佇列狀態與完成語義']
        ]
      },
      {
        text: '應用案例',
        items: [['15-vikingbot.md', 'VikingBot']]
      }
    ]
  }
} as const

const guidesSidebar = {
  en: {
    groups: [
      {
        text: 'Configuration & Deployment',
        items: [
          ['01-configuration.md', 'Configuration'],
          ['02-volcengine-purchase-guide.md', 'Model Purchase'],
          ['03-deployment.md', 'Server Deployment'],
          ['04-authentication.md', 'Authentication'],
          ['08-encryption.md', 'Encryption'],
          ['11-oauth.md', 'OAuth 2.1'],
          ['12-public-access.md', 'Public Access']
        ]
      },
      {
        text: 'Integration & Extension',
        items: [
          ['06-mcp-integration.md', 'MCP Integration'],
          ['09-ovpack.md', 'OVPack'],
          ['18-openviking-assets.md', 'Business Data Platform Assets'],
          ['10-prompt-guide.md', 'Prompt Customization'],
          ['17-vikingbot.md', 'VikingBot']
        ]
      },
      {
        text: 'Observability',
        items: [
          ['05-observability.md', 'Observability & Diagnostics'],
          ['07-operation-telemetry.md', 'Operation Telemetry'],
          ['11-grafana-prometheus.md', 'Prometheus / Grafana'],
          ['12-vikingbot-metrics-validation.md', 'VikingBot Metrics Validation']
        ]
      },
      {
        text: 'Storage & Performance',
        items: [
          ['13-multi-write-storage.md', 'Multi-Write Storage'],
          ['14-ragfs-cache.md', 'RAGFS Cache'],
          ['15-snapshot.md', 'Snapshots'],
          ['16-cuvs.md', 'cuVS Vector Search']
        ]
      }
    ]
  },
  zh: {
    groups: [
      {
        text: '配置與部署',
        items: [
          ['01-configuration.md', '基礎配置'],
          ['02-volcengine-purchase-guide.md', '模型購買'],
          ['03-deployment.md', '服務端部署'],
          ['04-authentication.md', '身份認證'],
          ['08-encryption.md', '資料加密'],
          ['11-oauth.md', 'OAuth 2.1'],
          ['12-public-access.md', '公網訪問']
        ]
      },
      {
        text: '整合與擴充',
        items: [
          ['06-mcp-integration.md', 'MCP 集成'],
          ['09-ovpack.md', 'OVPack'],
          ['18-openviking-assets.md', 'Business Data Platform Assets'],
          ['10-prompt-guide.md', 'Prompt 自定義'],
          ['17-vikingbot.md', 'VikingBot']
        ]
      },
      {
        text: '可觀測性',
        items: [
          ['05-observability.md', '可觀測性與排障'],
          ['07-operation-telemetry.md', '操作遙測'],
          ['11-grafana-prometheus.md', 'Prometheus / Grafana'],
          ['12-vikingbot-metrics-validation.md', 'VikingBot 指標驗證']
        ]
      },
      {
        text: '儲存與效能',
        items: [
          ['13-multi-write-storage.md', '多寫儲存'],
          ['14-ragfs-cache.md', 'RAGFS 快取'],
          ['15-snapshot.md', '快照管理'],
          ['16-cuvs.md', 'cuVS 向量檢索']
        ]
      }
    ]
  }
} as const

type StructuredSidebarCopy = {
  readonly overview: string
  readonly topItems?: ReadonlyArray<readonly [string, string]>
  readonly groups: ReadonlyArray<{
    readonly text: string
    readonly items: ReadonlyArray<readonly [string, string]>
  }>
}

type GroupedSidebarCopy = Pick<StructuredSidebarCopy, 'groups'>

function configuredSidebarItem(
  locale: 'en' | 'zh',
  section: string,
  [file, text]: readonly [string, string]
): DefaultTheme.SidebarItem {
  return {
    text,
    link: linkFor(path.join(docsRoot, locale, section, file))
  }
}

function configuredSidebarGroups(
  locale: 'en' | 'zh',
  section: string,
  groups: GroupedSidebarCopy['groups']
): DefaultTheme.SidebarItem[] {
  return groups.map((group) => ({
    text: group.text,
    collapsed: false,
    items: group.items.map((item) => configuredSidebarItem(locale, section, item))
  }))
}

function groupedSidebarSection(
  locale: 'en' | 'zh',
  section: string,
  title: string,
  copy: GroupedSidebarCopy,
  collapsed = true
): DefaultTheme.SidebarItem {
  return {
    text: title,
    collapsed,
    items: configuredSidebarGroups(locale, section, copy.groups)
  }
}

function structuredSidebarSection(
  locale: 'en' | 'zh',
  section: string,
  title: string,
  copy: StructuredSidebarCopy,
  collapsed = true,
  overviewFile = '01-overview.md'
): DefaultTheme.SidebarItem {
  return {
    text: title,
    collapsed,
    items: [
      configuredSidebarItem(locale, section, [overviewFile, copy.overview]),
      ...(copy.topItems ?? []).map((item) => configuredSidebarItem(locale, section, item)),
      ...configuredSidebarGroups(locale, section, copy.groups)
    ]
  }
}

function agentIntegrationSection(
  locale: 'en' | 'zh',
  title: string,
  collapsed = true
): DefaultTheme.SidebarItem {
  return structuredSidebarSection(
    locale,
    'agent-integrations',
    title,
    agentIntegrationSidebar[locale],
    collapsed
  )
}

function gettingStartedSection(
  locale: 'en' | 'zh',
  title: string,
  collapsed = true
): DefaultTheme.SidebarItem {
  return {
    text: title,
    collapsed,
    items: gettingStartedSidebar[locale].map((item) =>
      configuredSidebarItem(locale, 'getting-started', item)
    )
  }
}

function apiReferenceSection(
  locale: 'en' | 'zh',
  title: string,
  collapsed = true
): DefaultTheme.SidebarItem {
  return structuredSidebarSection(locale, 'api', title, apiReferenceSidebar[locale], collapsed)
}

function conceptsSection(
  locale: 'en' | 'zh',
  title: string,
  collapsed = true
): DefaultTheme.SidebarItem {
  return structuredSidebarSection(
    locale,
    'concepts',
    title,
    conceptsSidebar[locale],
    collapsed,
    '01-architecture.md'
  )
}

function guidesSection(
  locale: 'en' | 'zh',
  title: string,
  collapsed = true
): DefaultTheme.SidebarItem {
  const section = groupedSidebarSection(locale, 'guides', title, guidesSidebar[locale], collapsed)
  // Nest the Context Compilation pages under the "Integration & Extension" group.
  const integrationGroupTitle = locale === 'zh' ? '整合與擴充' : 'Integration & Extension'
  const integrationGroup = section.items?.find((item) => item.text === integrationGroupTitle)
  if (integrationGroup?.items) {
    const labels = locale === 'zh' ? zhSectionNames : sectionNames
    integrationGroup.items.push(
      sidebarSection(`${locale}/context-compilation`, labels['context-compilation'], true)
    )
  }
  return section
}

function migrationSection(
  locale: 'en' | 'zh',
  title: string,
  collapsed = true
): DefaultTheme.SidebarItem {
  return {
    text: title,
    collapsed,
    items: [
      {
        text: '0.3.x → 0.4.0',
        link: linkFor(path.join(docsRoot, locale, 'migration', '01-user-peer-model.md'))
      }
    ]
  }
}

type LocalizedSidebarSection =
  | 'getting-started'
  | 'configuration'
  | 'concepts'
  | 'guides'
  | 'agent-integrations'
  | 'migration'

type LocalizedSidebarSectionBuilder = (
  locale: 'en' | 'zh',
  title: string,
  collapsed?: boolean
) => DefaultTheme.SidebarItem

const localizedSidebarSectionBuilders: Record<
  LocalizedSidebarSection,
  LocalizedSidebarSectionBuilder
> = {
  'getting-started': gettingStartedSection,
  configuration: (locale, title, collapsed = true) =>
    sidebarSection(`${locale}/configuration`, title, collapsed),
  concepts: conceptsSection,
  guides: guidesSection,
  'agent-integrations': agentIntegrationSection,
  migration: migrationSection
}

function localizedSidebarSection(
  locale: 'en' | 'zh',
  section: LocalizedSidebarSection,
  title: string,
  collapsed = true
): DefaultTheme.SidebarItem {
  return localizedSidebarSectionBuilders[section](locale, title, collapsed)
}

export function localizedSectionSidebarItems(
  locale: 'en' | 'zh',
  section: LocalizedSidebarSection
): DefaultTheme.SidebarItem[] {
  const labels = locale === 'zh' ? zhSectionNames : sectionNames
  return [localizedSidebarSection(locale, section, labels[section], false)]
}

export function localizedGroupedSidebarItems(
  locale: 'en' | 'zh',
  sections: ReadonlyArray<Exclude<LocalizedSidebarSection, 'concepts'>>
): DefaultTheme.SidebarItem[] {
  const labels = locale === 'zh' ? zhSectionNames : sectionNames

  return sections.map((section) =>
    localizedSidebarSection(locale, section, labels[section], false)
  )
}

export function localizedReferenceSidebarItems(locale: 'en' | 'zh'): DefaultTheme.SidebarItem[] {
  const labels = locale === 'zh' ? zhSectionNames : sectionNames
  return [apiReferenceSection(locale, labels.api, false)]
}

export function localizedAboutSidebarItems(locale: 'en' | 'zh'): DefaultTheme.SidebarItem[] {
  const labels = locale === 'zh' ? zhSectionNames : sectionNames
  return [sidebarSection(`${locale}/about`, labels.about, false)]
}

export const designSidebar: DefaultTheme.SidebarItem[] = [
  sidebarSection('design', sectionNames.design, false)
]


// The homepage map uses the same entries, labels and order as article sidebars.
export function documentationSections(locale: 'en' | 'zh') {
  const labels = locale === 'zh' ? zhSectionNames : sectionNames
  return [
    ...localizedGroupedSidebarItems(locale, ['getting-started', 'configuration', 'agent-integrations']),
    ...localizedSectionSidebarItems(locale, 'concepts'),
    ...localizedGroupedSidebarItems(locale, ['guides', 'migration']),
    ...localizedReferenceSidebarItems(locale),
    sidebarSection(`${locale}/faq`, labels.faq, false),
    ...localizedAboutSidebarItems(locale)
  ]
}

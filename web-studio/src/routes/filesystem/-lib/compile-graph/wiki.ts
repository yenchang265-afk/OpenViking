import {
  cleanLinkTarget,
  frontmatterText,
  markdownLinks,
  parseFrontmatter,
  plainLabel,
} from './markdown'
import type { Frontmatter } from './markdown'
import type { CompiledGraph, GraphLink, GraphNode, SourceFile } from './types'
import { baseName, normalizeVikingUri, parentDir, relativeTo } from './uri'

/** Page categories in legend order (examples/compile/graph-show/llm-wiki). */
export const WIKI_CATEGORIES = [
  'index',
  'entity',
  'concept',
  'method',
  'comparison',
  'analysis',
  'summary',
  'source',
  'audit',
  'other',
] as const

const CATEGORY_ALIASES: Record<string, string> = {
  index: 'index',
  entity: 'entity',
  entities: 'entity',
  concept: 'concept',
  concepts: 'concept',
  method: 'method',
  methods: 'method',
  comparison: 'comparison',
  comparisons: 'comparison',
  analysis: 'analysis',
  analyses: 'analysis',
  synthesis: 'analysis',
  summary: 'summary',
  summaries: 'summary',
  source: 'source',
  sources: 'source',
  audit: 'audit',
}

function decodedStem(uri: string): string {
  let name = baseName(uri)
  try {
    name = decodeURIComponent(name)
  } catch {
    /* keep the raw name */
  }
  return name.replace(/\.[^.]+$/, '')
}

function pageTitle(data: Frontmatter, body: string, uri: string): string {
  const title = frontmatterText(data, 'title')
  if (title) return title
  const heading = /^# +(.+)$/m.exec(body)?.[1]?.trim()
  return heading || decodedStem(uri)
}

function pageCategory(type: string, uri: string, relPath: string): string {
  const fromType = CATEGORY_ALIASES[type.toLowerCase()]
  if (fromType) return fromType
  if (baseName(uri).toLowerCase() === 'index.md') return 'index'
  return CATEGORY_ALIASES[relPath.split('/')[0].toLowerCase()] ?? 'other'
}

type Page = GraphNode & { dir: string }

/** Resolves a link to a loaded page: relative, root-absolute, then by unique basename. */
function resolveLink(
  target: string,
  page: Page,
  root: string,
  pages: Map<string, Page>,
): string | null {
  if (!target.toLowerCase().endsWith('.md')) return null
  const candidates = target.startsWith('viking://')
    ? [normalizeVikingUri(target)]
    : target.includes('://')
      ? []
      : [
          normalizeVikingUri(`${page.dir}/${target}`),
          normalizeVikingUri(`${root}/${target.replace(/^\/+/, '')}`),
        ]
  const direct = candidates.find((uri) => pages.has(uri))
  if (direct) return direct
  if (candidates.length === 0) return null
  const name = baseName(target)
  const sameName = [...pages.keys()].filter((uri) => baseName(uri) === name)
  return sameName.length === 1 ? sameName[0] : null
}

/** Builds the page graph for an llm-wiki output rooted at `root`. */
export function buildWikiGraph(
  root: string,
  files: readonly SourceFile[],
): CompiledGraph {
  const pages = new Map<string, Page>()
  for (const file of [...files].sort((a, b) => a.uri.localeCompare(b.uri))) {
    const uri = normalizeVikingUri(file.uri)
    const { data, body } = parseFrontmatter(file.content)
    const relPath = relativeTo(uri, root)
    pages.set(uri, {
      id: uri,
      uri,
      title: pageTitle(data, body, uri),
      group: pageCategory(frontmatterText(data, 'type'), uri, relPath),
      degree: 0,
      body,
      description: frontmatterText(data, 'description') || undefined,
      dir: parentDir(uri),
    })
  }

  const links = new Map<string, GraphLink>()
  for (const page of pages.values()) {
    for (const link of markdownLinks(page.body)) {
      const target = resolveLink(
        cleanLinkTarget(link.target),
        page,
        root,
        pages,
      )
      if (!target || target === page.id) continue
      const key = `${page.id}\u0000${target}`
      if (!links.has(key))
        links.set(key, {
          source: page.id,
          target,
          label: plainLabel(link.label),
        })
    }
  }
  for (const link of links.values()) {
    pages.get(link.source)!.degree += 1
    pages.get(link.target)!.degree += 1
  }

  const order = (group: string) =>
    WIKI_CATEGORIES.indexOf(group as (typeof WIKI_CATEGORIES)[number])
  const nodes: GraphNode[] = [...pages.values()]
    .map(({ dir: _dir, ...node }) => node)
    .sort(
      (a, b) =>
        order(a.group) - order(b.group) || a.title.localeCompare(b.title),
    )
  return { kind: 'llm-wiki', nodes, links: [...links.values()], warnings: [] }
}

/** Resolves links inside page bodies to node ids, for the side panel. */
export function createWikiLinkResolver(
  graph: CompiledGraph,
  root: string,
): (fromUri: string, href: string) => string | null {
  const pages = new Map(
    graph.nodes.map((node) => [node.id, { ...node, dir: parentDir(node.uri) }]),
  )
  return (fromUri, href) => {
    const page = pages.get(fromUri)
    return page ? resolveLink(cleanLinkTarget(href), page, root, pages) : null
  }
}

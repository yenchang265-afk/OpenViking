export type Frontmatter = Record<string, string | string[]>

const FRONTMATTER = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/

const unquote = (value: string) => value.trim().replace(/^(['"])(.*)\1$/, '$2')

/**
 * Flat YAML subset used by the compile Skills: `key: value`, inline
 * `[a, "b"]` lists and indented `- item` block lists. Keys are lowercased.
 */
export function parseFrontmatter(markdown: string): {
  data: Frontmatter
  body: string
  found: boolean
} {
  const match = FRONTMATTER.exec(markdown)
  if (!match) return { data: {}, body: markdown, found: false }
  const data: Frontmatter = {}
  let listKey: string | null = null
  for (const line of match[1].split(/\r?\n/)) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue
    const item = /^\s+-\s*(.*)$/.exec(line)
    if (item && listKey) {
      ;(data[listKey] as string[]).push(unquote(item[1]))
      continue
    }
    const colon = line.indexOf(':')
    if (colon < 0) {
      listKey = null
      continue
    }
    const key = line.slice(0, colon).trim().toLowerCase()
    const value = line.slice(colon + 1).trim()
    listKey = null
    if (!value) {
      data[key] = []
      listKey = key
    } else if (value.startsWith('[') && value.endsWith(']')) {
      data[key] = value.slice(1, -1).split(',').map(unquote).filter(Boolean)
    } else {
      data[key] = unquote(value)
    }
  }
  return { data, body: markdown.slice(match[0].length), found: true }
}

export function frontmatterText(data: Frontmatter, ...keys: string[]): string {
  for (const key of keys) {
    const value = data[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

export function frontmatterList(
  data: Frontmatter,
  ...keys: string[]
): string[] {
  for (const key of keys) {
    const value = data[key]
    if (Array.isArray(value)) return value.filter(Boolean)
    if (typeof value === 'string' && value.trim()) return [value.trim()]
  }
  return []
}

/** Markdown links, not images; the target may be `<wrapped>` and titled. */
const LINK =
  /(?<!!)\[([^\]\n]{1,500})\]\(\s*(<[^>\n]{1,2000}>|[^)\s]{1,2000})(?:\s+["'][^)\n]{0,500}["'])?\s*\)/g
const FENCE = /^(\s*)(`{3,}|~{3,})/
/** Longer lines are not scanned, so one huge line cannot stall the page. */
const MAX_LINK_LINE = 20_000

export type MarkdownLink = { label: string; target: string }

/** Links outside fenced code blocks, in document order. */
export function markdownLinks(body: string): MarkdownLink[] {
  const links: MarkdownLink[] = []
  let fence: string | null = null
  for (const line of body.split(/\r?\n/)) {
    const marker = FENCE.exec(line)?.[2]
    if (marker) {
      // A fence closes on the same character, at least as long as it opened.
      if (!fence) fence = marker
      else if (marker[0] === fence[0] && marker.length >= fence.length)
        fence = null
      continue
    }
    if (fence || line.length > MAX_LINK_LINE) continue
    for (const match of line.matchAll(LINK))
      links.push({ label: match[1], target: match[2] })
  }
  return links
}

const ENTITIES: Record<string, string> = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
}

/** Strips `<>`, entities, percent-encoding and any `#fragment` or `?query`. */
export function cleanLinkTarget(target: string): string {
  let clean = target
    .replace(/&(?:amp|lt|gt|quot|#39);/g, (m) => ENTITIES[m])
    .replace(/&#(\d+);/g, (_m, code: string) =>
      String.fromCodePoint(Number(code)),
    )
    .replace(/&#x([0-9a-f]+);/gi, (_m, code: string) =>
      String.fromCodePoint(parseInt(code, 16)),
    )
  clean = clean.replace(/^<(.*)>$/, '$1').trim()
  try {
    clean = decodeURIComponent(clean)
  } catch {
    /* keep the raw target */
  }
  return clean.split(/[#?]/)[0]
}

/** Inline markdown reduced to plain text for edge labels. */
export function plainLabel(label: string): string {
  return label.replace(/[`*_~]/g, '').trim()
}

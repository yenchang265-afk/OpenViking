import { parseFrontmatter } from './markdown'
import type { GraphKind } from './types'

type Entry = { name: string; isDir: boolean }

/**
 * Decides from a directory listing which compile output it holds.
 * A knowledge graph is checked first: its `type: entity` pages would
 * otherwise also look like wiki pages. `wiki-candidate` still needs
 * {@link isWikiIndex} on the root `index.md`.
 */
export function detectGraphKind(
  entries: readonly Entry[],
): GraphKind | 'wiki-candidate' | null {
  const has = (name: string, isDir: boolean) =>
    entries.some(
      (entry) =>
        entry.isDir === isDir && entry.name.replace(/\/$/, '') === name,
    )
  if (has('relations.jsonl', false) && has('entities', true))
    return 'knowledge-graph'
  if (has('index.md', false)) return 'wiki-candidate'
  return null
}

/** llm-wiki contract: the root `index.md` declares `type: index`. */
export function isWikiIndex(markdown: string): boolean {
  const type = parseFrontmatter(markdown).data.type
  return typeof type === 'string' && type.toLowerCase() === 'index'
}

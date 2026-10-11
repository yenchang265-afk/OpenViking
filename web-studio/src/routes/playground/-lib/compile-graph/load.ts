import { fetchFileContent, fetchFsList } from '#/routes/resources/-lib/api'

import { buildKnowledgeGraph } from './knowledge-graph'
import type { CompiledGraph, GraphKind, SourceFile } from './types'
import { isHiddenPath, relativeTo, trimSlash } from './uri'
import { buildWikiGraph } from './wiki'

/** Larger outputs are drawn partially, with a warning. */
export const MAX_GRAPH_FILES = 800
const READ_CONCURRENCY = 8

/** Unreadable files are skipped with a warning, like unparsable ones. */
async function readAll(
  uris: readonly string[],
  warnings: string[],
): Promise<SourceFile[]> {
  const files: (SourceFile | null)[] = new Array(uris.length).fill(null)
  let next = 0
  const worker = async () => {
    while (next < uris.length) {
      const index = next++
      try {
        const { content } = await fetchFileContent(uris[index], { raw: true })
        files[index] = { uri: uris[index], content }
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error)
        warnings.push(`${uris[index]}: could not be read (${reason})`)
      }
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(READ_CONCURRENCY, uris.length) }, worker),
  )
  return files.filter((file): file is SourceFile => file !== null)
}

async function markdownFiles(dir: string, recursive: boolean) {
  const { entries } = await fetchFsList(dir, {
    recursive,
    nodeLimit: MAX_GRAPH_FILES + 1,
  })
  return entries
    .filter(
      (entry) =>
        !entry.isDir &&
        entry.name.toLowerCase().endsWith('.md') &&
        !isHiddenPath(relativeTo(trimSlash(entry.uri), dir)),
    )
    .map((entry) => trimSlash(entry.uri))
    .sort()
}

function capped(uris: string[], warnings: string[]): string[] {
  if (uris.length <= MAX_GRAPH_FILES) return uris
  warnings.push(
    `Only the first ${MAX_GRAPH_FILES} Markdown files are drawn; the rest were skipped`,
  )
  return uris.slice(0, MAX_GRAPH_FILES)
}

/** Reads a compile output directory and builds its graph. */
export async function loadCompiledGraph(
  dirUri: string,
  kind: GraphKind,
): Promise<CompiledGraph> {
  const dir = trimSlash(dirUri)
  const warnings: string[] = []
  if (kind === 'knowledge-graph') {
    const entityUris = capped(
      await markdownFiles(`${dir}/entities`, false),
      warnings,
    )
    const [entities, relations] = await Promise.all([
      readAll(entityUris, warnings),
      fetchFileContent(`${dir}/relations.jsonl`, { raw: true }),
    ])
    const graph = buildKnowledgeGraph(entities, relations.content)
    return { ...graph, warnings: [...warnings, ...graph.warnings] }
  }
  const pages = await readAll(
    capped(await markdownFiles(dir, true), warnings),
    warnings,
  )
  const graph = buildWikiGraph(dir, pages)
  return { ...graph, warnings: [...warnings, ...graph.warnings] }
}

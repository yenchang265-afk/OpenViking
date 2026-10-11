import type { CompiledGraph } from './types'

/**
 * Nodes within `hops` of `startId`, treating links as undirected. In a wiki
 * the index links to everything, so it is never walked *through* (only
 * from, when it is the start) — otherwise one hop would light up the graph.
 */
export function neighborhood(
  graph: CompiledGraph,
  startId: string,
  hops: number,
): Set<string> {
  const adjacent = new Map<string, string[]>()
  for (const { source, target } of graph.links) {
    adjacent.set(source, [...(adjacent.get(source) ?? []), target])
    adjacent.set(target, [...(adjacent.get(target) ?? []), source])
  }
  const group = new Map(graph.nodes.map((node) => [node.id, node.group]))
  const seen = new Set([startId])
  let frontier = [startId]
  for (let hop = 0; hop < hops && frontier.length; hop++) {
    const next: string[] = []
    for (const id of frontier) {
      if (
        id !== startId &&
        graph.kind === 'llm-wiki' &&
        group.get(id) === 'index'
      )
        continue
      for (const other of adjacent.get(id) ?? []) {
        if (seen.has(other)) continue
        seen.add(other)
        next.push(other)
      }
    }
    frontier = next
  }
  return seen
}

/** Case-insensitive match on title, description, aliases and URI. */
export function matchesQuery(
  node: CompiledGraph['nodes'][number],
  query: string,
): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [node.title, node.description ?? '', node.uri, ...(node.aliases ?? [])]
    .join('\n')
    .toLowerCase()
    .includes(q)
}

/** Starting node: the wiki index, else the best connected node. */
export function initialNodeId(graph: CompiledGraph): string | null {
  const index =
    graph.kind === 'llm-wiki'
      ? graph.nodes.find((node) => node.group === 'index')
      : undefined
  if (index) return index.id
  if (graph.nodes.length === 0) return null
  return [...graph.nodes].sort((a, b) => b.degree - a.degree)[0].id
}

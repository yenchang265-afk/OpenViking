import {
  cleanLinkTarget,
  frontmatterList,
  frontmatterText,
  parseFrontmatter,
} from './markdown'
import type { CompiledGraph, GraphLink, GraphNode, SourceFile } from './types'
import { baseName } from './uri'

/** Entity types in legend order (examples/compile/graph-show/knowledge-graph). */
export const ENTITY_TYPES = [
  'person',
  'animal',
  'place',
  'artifact',
  'document',
  'organization',
  'group',
  'event',
  'product',
  'project',
  'system',
  'service',
  'module',
  'dataset',
  'standard',
  'other',
] as const

const TYPE_ALIASES: Record<string, string> = {
  human: 'person',
  character: 'person',
  people: 'person',
  location: 'place',
  region: 'place',
  site: 'place',
  item: 'artifact',
  object: 'artifact',
  tool: 'artifact',
  weapon: 'artifact',
  contract: 'document',
  book: 'document',
  record: 'document',
  org: 'organization',
  team: 'group',
  collective: 'group',
}

const RELATION = /^[a-z][a-z0-9_]*$/

export function normalizeEntityType(value: string): string {
  const key = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  const type = TYPE_ALIASES[key] ?? key
  return (ENTITY_TYPES as readonly string[]).includes(type) ? type : 'other'
}

const stem = (uri: string) => baseName(uri).replace(/\.md$/i, '')

function readEntities(files: readonly SourceFile[], warnings: string[]) {
  const nodes = new Map<string, GraphNode>()
  for (const file of [...files].sort((a, b) => a.uri.localeCompare(b.uri))) {
    const { data, body, found } = parseFrontmatter(file.content)
    const fileId = stem(file.uri)
    if (!found) warnings.push(`${baseName(file.uri)}: no frontmatter`)
    const id = frontmatterText(data, 'id') || fileId
    if (id !== fileId)
      warnings.push(`${baseName(file.uri)}: id "${id}" differs from file name`)
    if (nodes.has(id)) {
      warnings.push(`${baseName(file.uri)}: duplicate id "${id}" skipped`)
      continue
    }
    nodes.set(id, {
      id,
      uri: file.uri,
      title: frontmatterText(data, 'title') || id,
      group: normalizeEntityType(
        frontmatterText(data, 'entity_type', 'kind', 'category'),
      ),
      degree: 0,
      body: body.trim(),
      description: frontmatterText(data, 'description') || undefined,
      aliases: frontmatterList(data, 'aliases', 'alias'),
      sources: frontmatterList(data, 'sources', 'source'),
    })
  }
  return nodes
}

function readRelations(
  text: string,
  nodes: Map<string, GraphNode>,
  warnings: string[],
): GraphLink[] {
  const merged = new Map<string, GraphLink>()
  text.split(/\r?\n/).forEach((line, index) => {
    if (!line.trim()) return
    const where = `relations.jsonl:${index + 1}`
    let record: unknown
    try {
      record = JSON.parse(line)
    } catch {
      warnings.push(`${where}: not JSON`)
      return
    }
    if (!record || typeof record !== 'object' || Array.isArray(record)) {
      warnings.push(`${where}: not a JSON object`)
      return
    }
    const fields = record as Record<string, unknown>
    const field = (key: string) => {
      const value = fields[key]
      return typeof value === 'string' ? value.trim() : ''
    }
    const [source, target, relation] = [
      field('from'),
      field('to'),
      field('relation'),
    ]
    if (!source || !target || !RELATION.test(relation)) {
      warnings.push(`${where}: needs from, to and a snake_case relation`)
      return
    }
    if (!nodes.has(source) || !nodes.has(target)) {
      warnings.push(
        `${where}: unknown entity ${nodes.has(source) ? target : source}`,
      )
      return
    }
    const evidence = Array.isArray(fields.evidence)
      ? fields.evidence
          .filter((item): item is string => typeof item === 'string')
          .map((item) => item.trim())
          .filter(Boolean)
      : []
    const key = `${source}\u0000${relation}\u0000${target}`
    const existing = merged.get(key)
    if (existing) {
      for (const item of evidence)
        if (!existing.evidence!.includes(item)) existing.evidence!.push(item)
      return
    }
    merged.set(key, {
      source,
      target,
      relation,
      label: field('label') || relation,
      evidence,
    })
  })
  return [...merged.values()].sort(
    (a, b) =>
      a.source.localeCompare(b.source) ||
      a.relation!.localeCompare(b.relation!) ||
      a.target.localeCompare(b.target),
  )
}

/** Builds the entity graph from `entities/*.md` and `relations.jsonl`. */
export function buildKnowledgeGraph(
  entities: readonly SourceFile[],
  relations: string,
): CompiledGraph {
  const warnings: string[] = []
  const nodes = readEntities(entities, warnings)
  const links = readRelations(relations, nodes, warnings)
  for (const link of links) {
    nodes.get(link.source)!.degree += 1
    nodes.get(link.target)!.degree += 1
  }
  return {
    kind: 'knowledge-graph',
    nodes: [...nodes.values()].sort(
      (a, b) => b.degree - a.degree || a.title.localeCompare(b.title),
    ),
    links,
    warnings,
  }
}

/** An entity link in a body (`../entities/<id>.md`) points at that entity. */
export function resolveEntityLink(
  graph: CompiledGraph,
  href: string,
): string | null {
  const target = cleanLinkTarget(href)
  // Only relative links name entities; URLs keep their own meaning.
  if (target.includes('://') || !target.toLowerCase().endsWith('.md'))
    return null
  const id = stem(target)
  return graph.nodes.some((node) => node.id === id) ? id : null
}

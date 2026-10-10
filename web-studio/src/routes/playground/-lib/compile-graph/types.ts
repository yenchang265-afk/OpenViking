/** Compile outputs the Playground can draw as a graph. */
export type GraphKind = 'llm-wiki' | 'knowledge-graph'

export type GraphNode = {
  id: string
  /** File the node was read from. */
  uri: string
  title: string
  /** Wiki page category or knowledge-graph entity type. */
  group: string
  degree: number
  /** Markdown body without frontmatter. */
  body: string
  description?: string
  aliases?: string[]
  sources?: string[]
}

export type GraphLink = {
  source: string
  target: string
  label: string
  /** Knowledge-graph predicate, e.g. `member_of`. */
  relation?: string
  evidence?: string[]
}

export type CompiledGraph = {
  kind: GraphKind
  nodes: GraphNode[]
  links: GraphLink[]
  /** Problems that were skipped instead of failing the whole graph. */
  warnings: string[]
}

export type SourceFile = { uri: string; content: string }

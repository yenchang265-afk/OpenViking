import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  LoaderCircleIcon,
  LocateFixedIcon,
  SearchIcon,
  TriangleAlertIcon,
} from 'lucide-react'

import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import { loadCompiledGraph } from '../../-lib/compile-graph/load'
import {
  initialNodeId,
  matchesQuery,
  neighborhood,
} from '../../-lib/compile-graph/neighborhood'
import { groupColor, groupOrder } from '../../-lib/compile-graph/style'
import type { CompiledGraph, GraphKind } from '../../-lib/compile-graph/types'
import { trimSlash } from '../../-lib/compile-graph/uri'
import { GraphCanvas } from './graph-canvas'
import { GraphNodePanel } from './graph-node-panel'

export type CompileGraphViewProps = {
  dirUri: string
  kind: GraphKind
  /** Shown in the query key so another identity never sees cached files. */
  scopeKey: string
  onOpenFile: (uri: string) => void
}

/** Interactive graph of an llm-wiki or knowledge-graph compile output. */
export function CompileGraphView({
  dirUri,
  kind,
  scopeKey,
  onOpenFile,
}: CompileGraphViewProps) {
  const { t } = useTranslation('playground')
  const root = trimSlash(dirUri)
  const query = useQuery({
    queryKey: ['compile-graph', scopeKey, root, kind],
    queryFn: () => loadCompiledGraph(root, kind),
    staleTime: 30_000,
  })

  if (query.isPending)
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <LoaderCircleIcon className="size-4 animate-spin" />
        {t('compileGraph.loading')}
      </div>
    )
  if (query.isError)
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm">
        <p className="font-medium">{t('compileGraph.loadFailed')}</p>
        <p className="max-w-md text-muted-foreground">
          {query.error instanceof Error
            ? query.error.message
            : String(query.error)}
        </p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void query.refetch()}
        >
          {t('compileGraph.retry')}
        </Button>
      </div>
    )
  if (query.data.nodes.length === 0)
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {t('compileGraph.empty')}
      </div>
    )
  return (
    <GraphExplorer
      key={`${root}:${kind}`}
      graph={query.data}
      root={root}
      onOpenFile={onOpenFile}
    />
  )
}

function GraphExplorer({
  graph,
  root,
  onOpenFile,
}: {
  graph: CompiledGraph
  root: string
  onOpenFile: (uri: string) => void
}) {
  const { t } = useTranslation('playground')
  const [pickedId, setPickedId] = useState(() => initialNodeId(graph))
  // A refetch can drop the picked node; fall back instead of dangling.
  const selectedId = graph.nodes.some((node) => node.id === pickedId)
    ? pickedId
    : initialNodeId(graph)
  const [hops, setHops] = useState(1)
  const [search, setSearch] = useState('')
  const [hiddenGroups, setHiddenGroups] = useState<ReadonlySet<string>>(
    new Set(),
  )
  const [resetSignal, setResetSignal] = useState(0)

  const groups = useMemo(() => {
    const counts = new Map<string, number>()
    for (const node of graph.nodes)
      counts.set(node.group, (counts.get(node.group) ?? 0) + 1)
    const order = groupOrder(graph.kind)
    return [...counts].sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
  }, [graph])

  const reach = useMemo(
    () => (selectedId ? neighborhood(graph, selectedId, hops) : null),
    [graph, selectedId, hops],
  )
  const canExpand = useMemo(
    () =>
      !!selectedId &&
      !!reach &&
      neighborhood(graph, selectedId, hops + 1).size > reach.size,
    [graph, selectedId, hops, reach],
  )
  // Search wins over the neighborhood; hidden groups are always dimmed.
  const highlighted = useMemo(() => {
    const searching = search.trim() !== ''
    if (!searching && !reach && hiddenGroups.size === 0) return null
    return new Set(
      graph.nodes
        .filter(
          (node) =>
            !hiddenGroups.has(node.group) &&
            (searching
              ? matchesQuery(node, search)
              : !reach || reach.has(node.id)),
        )
        .map((node) => node.id),
    )
  }, [graph, hiddenGroups, reach, search])

  const select = (id: string) => {
    setPickedId(id)
    setHops(1)
    setSearch('')
  }
  const selected = graph.nodes.find((node) => node.id === selectedId) ?? null

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <div className="relative min-w-40 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            placeholder={t('compileGraph.search')}
            aria-label={t('compileGraph.search')}
            className="h-8 pl-7 text-sm"
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' || !search.trim()) return
              const first = graph.nodes.find((node) =>
                matchesQuery(node, search),
              )
              if (first) select(first.id)
            }}
          />
        </div>
        <span className="text-xs text-muted-foreground">
          {t('compileGraph.stats', {
            nodes: graph.nodes.length,
            links: graph.links.length,
          })}
        </span>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          title={t('compileGraph.resetView')}
          aria-label={t('compileGraph.resetView')}
          onClick={() => setResetSignal((value) => value + 1)}
        >
          <LocateFixedIcon />
        </Button>
      </div>
      <div
        className="flex flex-wrap gap-1 border-b px-3 py-1.5"
        role="group"
        aria-label={t('compileGraph.legend')}
      >
        {groups.map(([group, count]) => {
          const hidden = hiddenGroups.has(group)
          return (
            <button
              key={group}
              type="button"
              aria-pressed={!hidden}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition-opacity ${hidden ? 'opacity-40' : ''}`}
              onClick={() =>
                setHiddenGroups((current) => {
                  const next = new Set(current)
                  if (next.has(group)) next.delete(group)
                  else next.add(group)
                  return next
                })
              }
            >
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: groupColor(graph.kind, group) }}
              />
              {t(`compileGraph.groups.${group}`)}
              <span className="text-muted-foreground">{count}</span>
            </button>
          )
        })}
      </div>
      {graph.warnings.length ? (
        <details className="border-b px-3 py-1.5 text-xs text-amber-700 dark:text-amber-400">
          <summary className="flex cursor-pointer items-center gap-1.5">
            <TriangleAlertIcon className="size-3.5" />
            {t('compileGraph.warnings', { count: graph.warnings.length })}
          </summary>
          <ul className="mt-1 grid gap-0.5 pl-5">
            {graph.warnings.map((warning) => (
              <li key={warning} className="list-disc [overflow-wrap:anywhere]">
                {warning}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <div className="min-h-72 min-w-0 flex-1">
          <GraphCanvas
            graph={graph}
            highlighted={highlighted}
            selectedId={selectedId}
            onSelect={select}
            resetSignal={resetSignal}
            label={t('compileGraph.canvas')}
          />
        </div>
        <aside className="max-h-[50%] min-h-0 overflow-y-auto border-t md:max-h-none md:w-80 md:shrink-0 md:border-t-0 md:border-l">
          {selected ? (
            <GraphNodePanel
              graph={graph}
              root={root}
              node={selected}
              hops={hops}
              canExpand={canExpand}
              onHopsChange={setHops}
              onSelect={select}
              onOpenFile={onOpenFile}
            />
          ) : (
            <p className="p-4 text-sm text-muted-foreground">
              {t('compileGraph.pick')}
            </p>
          )}
        </aside>
      </div>
    </div>
  )
}

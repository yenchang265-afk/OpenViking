import { lazy, Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { FileTextIcon, Loader2, WorkflowIcon } from 'lucide-react'

import { fetchFileContent, fetchFsList } from '#/routes/resources/-lib/api'
import { detectGraphKind, isWikiIndex } from '../../-lib/compile-graph/detect'
import type { GraphKind } from '../../-lib/compile-graph/types'
import { trimSlash } from '../../-lib/compile-graph/uri'
import type { CompileGraphViewProps } from './graph-view'

// d3 and the graph code load only when a graph is opened.
const CompileGraphView = lazy(() =>
  import('./graph-view').then((module) => ({
    default: module.CompileGraphView,
  })),
)

async function detect(dirUri: string): Promise<GraphKind | null> {
  const { entries } = await fetchFsList(dirUri)
  const kind = detectGraphKind(entries)
  if (kind !== 'wiki-candidate') return kind
  const index = await fetchFileContent(`${trimSlash(dirUri)}/index.md`, {
    raw: true,
  })
  return isWikiIndex(index.content) ? 'llm-wiki' : null
}

/** Which graphable compile output `dirUri` holds, if any. */
export function useCompileGraphKind(
  dirUri: string | null,
  scopeKey: string,
): GraphKind | null {
  const { data } = useQuery({
    queryKey: ['compile-graph-kind', scopeKey, dirUri],
    queryFn: () => detect(dirUri!),
    enabled: !!dirUri && /^viking:\/\/[^/]+/.test(dirUri),
    staleTime: 30_000,
    retry: false,
  })
  return data ?? null
}

export function CompileGraphSwitch({
  kind,
  showGraph,
  onShowGraphChange,
}: {
  kind: GraphKind
  showGraph: boolean
  onShowGraphChange: (showGraph: boolean) => void
}) {
  const { t } = useTranslation('playground')
  const option = (active: boolean) =>
    `inline-flex items-center gap-1 px-2 py-1 text-xs ${active ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground hover:bg-muted/60'}`
  return (
    <div
      role="group"
      aria-label={t(`compileGraph.kinds.${kind}`)}
      title={t(`compileGraph.kinds.${kind}`)}
      className="flex shrink-0 overflow-hidden rounded-md border"
    >
      <button
        type="button"
        aria-pressed={!showGraph}
        className={option(!showGraph)}
        onClick={() => onShowGraphChange(false)}
      >
        <FileTextIcon className="size-3.5" />
        {t('compileGraph.contents')}
      </button>
      <button
        type="button"
        aria-pressed={showGraph}
        className={option(showGraph)}
        onClick={() => onShowGraphChange(true)}
      >
        <WorkflowIcon className="size-3.5" />
        {t('compileGraph.graph')}
      </button>
    </div>
  )
}

export function LazyCompileGraphView(props: CompileGraphViewProps) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <CompileGraphView {...props} />
    </Suspense>
  )
}

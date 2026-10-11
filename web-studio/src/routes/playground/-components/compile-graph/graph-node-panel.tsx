import { useMemo } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  FileTextIcon,
  MinusIcon,
  PlusIcon,
} from 'lucide-react'

import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import { resolveEntityLink } from '../../-lib/compile-graph/knowledge-graph'
import { cleanLinkTarget } from '../../-lib/compile-graph/markdown'
import { groupColor } from '../../-lib/compile-graph/style'
import type { CompiledGraph, GraphNode } from '../../-lib/compile-graph/types'
import { createWikiLinkResolver } from '../../-lib/compile-graph/wiki'

export type GraphNodePanelProps = {
  graph: CompiledGraph
  root: string
  node: GraphNode
  hops: number
  canExpand: boolean
  onHopsChange: (hops: number) => void
  onSelect: (id: string) => void
  onOpenFile: (uri: string) => void
}

// react-markdown blanks unknown schemes before `a` sees them; keep viking://
// (handled in-app below) and let the default still drop javascript: etc.
const keepVikingUrls = (url: string) =>
  url.startsWith('viking://') ? url : defaultUrlTransform(url)

const linkButton =
  'rounded-sm text-left text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring [overflow-wrap:anywhere]'

export function GraphNodePanel({
  graph,
  root,
  node,
  hops,
  canExpand,
  onHopsChange,
  onSelect,
  onOpenFile,
}: GraphNodePanelProps) {
  const { t } = useTranslation('playground')
  const titles = useMemo(
    () => new Map(graph.nodes.map((item) => [item.id, item.title])),
    [graph],
  )
  const titleOf = (id: string) => titles.get(id) ?? id
  const resolveWiki = useMemo(
    () => createWikiLinkResolver(graph, root),
    [graph, root],
  )

  // Same allowlist as graph-show: graph pages select, http(s) opens a new
  // tab, viking:// opens in the Playground, anything else is plain text.
  const components: Components = {
    a: ({ href = '', children }) => {
      const target =
        graph.kind === 'llm-wiki'
          ? resolveWiki(node.uri, href)
          : resolveEntityLink(graph, href)
      if (target)
        return (
          <button
            type="button"
            className={linkButton}
            onClick={() => onSelect(target)}
          >
            {children}
          </button>
        )
      if (/^https?:\/\//i.test(href))
        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={linkButton}
          >
            {children}
          </a>
        )
      if (href.startsWith('viking://'))
        return (
          <button
            type="button"
            className={linkButton}
            title={href}
            onClick={() => onOpenFile(cleanLinkTarget(href))}
          >
            {children}
          </button>
        )
      return <span>{children}</span>
    },
    img: ({ alt }) => <span>{alt}</span>,
  }

  const links = graph.links.filter(
    (link) => link.source === node.id || link.target === node.id,
  )

  return (
    <div className="grid gap-4 p-4 text-sm">
      <header className="grid gap-1.5">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span
            className="size-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: groupColor(graph.kind, node.group) }}
          />
          {t(`compileGraph.groups.${node.group}`)}
        </div>
        <h2 className="text-base font-semibold leading-6 [overflow-wrap:anywhere]">
          {node.title}
        </h2>
        <button
          type="button"
          className="flex w-fit items-center gap-1 font-mono text-xs text-muted-foreground hover:text-primary [overflow-wrap:anywhere]"
          title={t('compileGraph.openFile')}
          onClick={() => onOpenFile(node.uri)}
        >
          <FileTextIcon className="size-3.5 shrink-0" />
          {node.uri}
        </button>
        {node.description ? (
          <p className="leading-6 text-muted-foreground">{node.description}</p>
        ) : null}
        {node.aliases?.length ? (
          <div className="flex flex-wrap gap-1">
            {node.aliases.map((alias, index) => (
              <Badge key={index} variant="secondary" className="font-normal">
                {alias}
              </Badge>
            ))}
          </div>
        ) : null}
      </header>

      <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-2 py-1 text-xs">
        <span className="flex-1">
          {t('compileGraph.hops', { count: hops })}
        </span>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          aria-label={t('compileGraph.fewerHops')}
          disabled={hops <= 1}
          onClick={() => onHopsChange(hops - 1)}
        >
          <MinusIcon />
        </Button>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          aria-label={t('compileGraph.moreHops')}
          disabled={!canExpand}
          onClick={() => onHopsChange(hops + 1)}
        >
          <PlusIcon />
        </Button>
      </div>

      <section className="grid gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t(
            graph.kind === 'llm-wiki'
              ? 'compileGraph.links'
              : 'compileGraph.relations',
            {
              count: links.length,
            },
          )}
        </h3>
        {links.length === 0 ? (
          <p className="text-muted-foreground">{t('compileGraph.noLinks')}</p>
        ) : (
          <ul className="grid gap-1.5">
            {links.map((link) => {
              const outgoing = link.source === node.id
              const other = outgoing ? link.target : link.source
              const Arrow = outgoing ? ArrowRightIcon : ArrowLeftIcon
              return (
                <li
                  key={`${link.source}\u0000${link.relation ?? ''}\u0000${link.target}`}
                  className="grid gap-1 rounded-md border px-2 py-1.5"
                >
                  <div className="flex min-w-0 items-center gap-1.5">
                    <Arrow className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {link.label}
                    </span>
                    <button
                      type="button"
                      className={linkButton}
                      onClick={() => onSelect(other)}
                    >
                      {titleOf(other)}
                    </button>
                  </div>
                  {link.evidence?.length ? (
                    <details className="text-xs text-muted-foreground">
                      <summary className="cursor-pointer">
                        {t('compileGraph.evidence', {
                          count: link.evidence.length,
                        })}
                      </summary>
                      <ul className="mt-1 grid gap-1 pl-4">
                        {link.evidence.map((item, index) => (
                          <li
                            key={index}
                            className="list-disc [overflow-wrap:anywhere]"
                          >
                            {item}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {node.sources?.length ? (
        <section className="grid gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('compileGraph.sources')}
          </h3>
          <ul className="grid gap-1 font-mono text-xs">
            {node.sources.map((source, index) => (
              <li key={index} className="[overflow-wrap:anywhere]">
                {source.startsWith('viking://') ? (
                  <button
                    type="button"
                    className={linkButton}
                    onClick={() => onOpenFile(source)}
                  >
                    {source}
                  </button>
                ) : (
                  source
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {node.body ? (
        <section className="prose prose-sm max-w-none border-t pt-3 dark:prose-invert">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            urlTransform={keepVikingUrls}
            components={components}
          >
            {node.body}
          </ReactMarkdown>
        </section>
      ) : null}
    </div>
  )
}

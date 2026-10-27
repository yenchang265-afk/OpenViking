import { lazy, Suspense, useMemo } from 'react'

import { Skeleton } from '#/components/ui/skeleton'

import { COMMIT_SERIES_DAYS } from '../-constants/dashboard'
import type {
  ConsoleSeries,
  ContextCommitItem,
  HomeT,
} from '../-types/dashboard'
import {
  formatDateRange,
  formatNumber,
  getSeriesRange,
  isDisabledPayload,
  parseDateKey,
} from '../-lib/format'
import {
  buildHeatmapPanelColors,
  computeCommitHeatmapStats,
  normalizeCommitHeatmapData,
} from '../-lib/normalize'
import { EmptyState, Panel, SectionHeading, StaleNotice } from './panel'

const ContextCommitsHeatmap = lazy(() =>
  import('./context-commits-heatmap').then((module) => ({
    default: module.ContextCommitsHeatmap,
  })),
)

export function ContextCommitsPanel({
  data,
  disabled: disabledProp,
  disabledMessage,
  isError,
  isLoading,
  staleMessage,
  t,
}: {
  data: ConsoleSeries<ContextCommitItem> | undefined
  disabled?: boolean
  disabledMessage?: string
  isError: boolean
  isLoading: boolean
  staleMessage?: string
  t: HomeT
}) {
  const items = useMemo(
    () => normalizeCommitHeatmapData(data?.items),
    [data?.items],
  )
  const panelColors = useMemo(() => buildHeatmapPanelColors(items), [items])
  const totalCommits = useMemo(
    () => items.reduce((total, item) => total + item.count, 0),
    [items],
  )
  const stats = useMemo(() => computeCommitHeatmapStats(items), [items])
  const disabled = Boolean(disabledProp) || isDisabledPayload(data)
  const range = getSeriesRange(data, COMMIT_SERIES_DAYS)
  const rangeLabel = formatDateRange(range.startDate, range.endDate)
  const startDate = parseDateKey(range.startDate)
  const endDate = parseDateKey(range.endDate)
  const title =
    !isLoading && !isError && !disabled
      ? totalCommits > 0
        ? t('contextCommits.yearlyTotal', { count: formatNumber(totalCommits) })
        : t('contextCommits.yearlyEmpty')
      : t('contextCommits.title')

  return (
    <Panel>
      <SectionHeading
        action={
          <span className="pt-1 text-xs tabular-nums text-muted-foreground">
            {rangeLabel}
          </span>
        }
        description={t('contextCommits.description')}
        title={title}
      />

      {isLoading ? (
        <Skeleton className="h-72 w-full" />
      ) : isError ? (
        <EmptyState>{t('requestFailed')}</EmptyState>
      ) : disabled ? (
        <EmptyState>{disabledMessage ?? t('usageDisabled')}</EmptyState>
      ) : items.length === 0 ? (
        <EmptyState>{t('contextCommits.empty')}</EmptyState>
      ) : (
        <>
          {staleMessage ? (
            <div className="mb-3">
              <StaleNotice message={staleMessage} />
            </div>
          ) : null}
          <Suspense fallback={<Skeleton className="h-72 w-full" />}>
            <ContextCommitsHeatmap
              endDate={endDate}
              items={items}
              panelColors={panelColors}
              startDate={startDate}
              stats={stats}
              t={t}
            />
          </Suspense>
        </>
      )}
    </Panel>
  )
}

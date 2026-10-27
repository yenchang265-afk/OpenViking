import { lazy, Suspense } from 'react'

import { Skeleton } from '#/components/ui/skeleton'

import { TOKEN_SERIES_DAYS } from '../-constants/dashboard'
import type { ConsoleSeries, HomeT, TokenSeriesItem } from '../-types/dashboard'
import {
  formatDateRange,
  getSeriesRange,
  isDisabledPayload,
} from '../-lib/format'
import { normalizeTokenSeries } from '../-lib/normalize'
import { EmptyState, Panel, SectionHeading, StaleNotice } from './panel'

const TokenTrendChart = lazy(() =>
  import('./token-trend-chart').then((module) => ({
    default: module.TokenTrendChart,
  })),
)

export function TokenTrendPanel({
  data,
  disabled: disabledProp,
  disabledMessage,
  isError,
  isLoading,
  staleMessage,
  t,
}: {
  data: ConsoleSeries<TokenSeriesItem> | undefined
  disabled?: boolean
  disabledMessage?: string
  isError: boolean
  isLoading: boolean
  staleMessage?: string
  t: HomeT
}) {
  const items = normalizeTokenSeries(data?.items)
  const disabled = Boolean(disabledProp) || isDisabledPayload(data)
  const range = getSeriesRange(data, TOKEN_SERIES_DAYS)
  const rangeLabel = formatDateRange(range.startDate, range.endDate)

  return (
    <Panel>
      <SectionHeading
        action={
          <span className="pt-1 text-xs tabular-nums text-muted-foreground">
            {rangeLabel}
          </span>
        }
        description={t('tokenTrend.description')}
        title={t('tokenTrend.title')}
      />

      {isLoading ? (
        <Skeleton className="h-72 w-full" />
      ) : isError ? (
        <EmptyState>{t('requestFailed')}</EmptyState>
      ) : disabled ? (
        <EmptyState>{disabledMessage ?? t('usageDisabled')}</EmptyState>
      ) : items.length === 0 ? (
        <EmptyState>{t('tokenTrend.empty')}</EmptyState>
      ) : (
        <>
          {staleMessage ? (
            <div className="mb-3">
              <StaleNotice message={staleMessage} />
            </div>
          ) : null}
          <Suspense fallback={<Skeleton className="h-72 w-full" />}>
            <TokenTrendChart items={items} t={t} />
          </Suspense>
        </>
      )}
    </Panel>
  )
}

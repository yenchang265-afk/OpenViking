import { lazy, Suspense } from 'react'

import { Skeleton } from '#/shared/ui/skeleton'

import {
  EmptyState,
  Panel,
  SectionHeading,
  StaleNotice,
} from '#/features/workbench/home/components/panel'
import { TOKEN_SERIES_DAYS } from '#/features/workbench/home/constants/dashboard'
import {
  formatDateRange,
  getSeriesRange,
  isDisabledPayload,
} from '#/features/workbench/home/lib/format'
import { normalizeTokenSeries } from '#/features/workbench/home/lib/normalize'
import type {
  ConsoleSeries,
  HomeT,
  TokenSeriesItem,
} from '#/features/workbench/home/types/dashboard'

const TokenTrendChart = lazy(() =>
  import('#/features/workbench/home/components/token-trend-chart').then(
    (module) => ({
      default: module.TokenTrendChart,
    }),
  ),
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

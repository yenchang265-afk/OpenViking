import { lazy, Suspense } from 'react'

import { Skeleton } from '#/components/ui/skeleton'
import { cn } from '#/lib/utils'

import type { HomeT, TokenRate, TokenRateWindow } from '../-types/dashboard'
import {
  formatNumber,
  formatTpmTime,
  isDisabledPayload,
} from '../-lib/format'
import { normalizeTokenRate } from '../-lib/normalize'
import { EmptyState, Panel, SectionHeading } from './panel'

const TpmTrendChart = lazy(() =>
  import('./tpm-trend-chart').then((module) => ({
    default: module.TpmTrendChart,
  })),
)

export const TPM_WINDOWS: TokenRateWindow[] = ['1h', '6h', '24h', '7d']

export function TpmTrendPanel({
  data,
  disabled: disabledProp,
  disabledMessage,
  isError,
  isLoading,
  onWindowChange,
  t,
  window,
}: {
  data: TokenRate | undefined
  disabled?: boolean
  disabledMessage?: string
  isError: boolean
  isLoading: boolean
  onWindowChange: (window: TokenRateWindow) => void
  t: HomeT
  window: TokenRateWindow
}) {
  const disabled = Boolean(disabledProp) || isDisabledPayload(data)
  const series = normalizeTokenRate(data)

  return (
    <Panel>
      <SectionHeading
        action={
          <div
            role="group"
            aria-label={t('tpmTrend.window')}
            className="inline-flex shrink-0 rounded-lg border border-border/70 p-0.5"
          >
            {TPM_WINDOWS.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={value === window}
                onClick={() => onWindowChange(value)}
                className={cn(
                  'min-h-8 rounded-md px-3 text-xs font-medium tabular-nums transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                  value === window
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t(`tpmTrend.windows.${value}`)}
              </button>
            ))}
          </div>
        }
        description={t('tpmTrend.description')}
        title={t('tpmTrend.title')}
      />

      {isLoading ? (
        <Skeleton className="h-72 w-full" />
      ) : isError ? (
        <EmptyState>{t('requestFailed')}</EmptyState>
      ) : disabled ? (
        <EmptyState>{disabledMessage ?? t('usageDisabled')}</EmptyState>
      ) : !series.peak ? (
        <EmptyState>{t('tpmTrend.empty')}</EmptyState>
      ) : (
        <>
          <dl className="mb-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-border/60 px-4 py-3">
              <dt className="text-xs text-muted-foreground">
                {t('tpmTrend.peak')}
              </dt>
              <dd className="mt-1 flex flex-wrap items-baseline gap-x-2">
                <span className="text-2xl font-bold tabular-nums">
                  {formatNumber(series.peak.total)}
                </span>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {formatTpmTime(series.peak.minute, true)}
                </span>
              </dd>
            </div>
            <div className="rounded-xl border border-border/60 px-4 py-3">
              <dt className="text-xs text-muted-foreground">
                {t('tpmTrend.average')}
              </dt>
              <dd className="mt-1 text-2xl font-bold tabular-nums">
                {formatNumber(series.averageTotal)}
              </dd>
            </div>
          </dl>
          <Suspense fallback={<Skeleton className="h-72 w-full" />}>
            <TpmTrendChart
              bucketMinutes={series.bucketMinutes}
              items={series.items}
              t={t}
            />
          </Suspense>
        </>
      )}
    </Panel>
  )
}

import { Link } from '@tanstack/react-router'
import { ArrowRight, CircleAlert, ListTodo, Timer } from 'lucide-react'

import { formatDateTime } from '#/i18n/format'

import type { HomeT, LatencySummary, RequestHealth } from '../-types/dashboard'
import { asNumber, formatNumber, formatPercent } from '../-lib/format'
import type { TaskSummary } from '../-lib/tasks'
import { MetricPanel } from './metric-panels'
import { DetailRow } from './panel'

const LINK_CLASS =
  'flex min-h-8 items-center gap-1 py-1.5 text-xs font-medium text-primary hover:underline'

function formatMs(value: number | undefined, t: HomeT): string {
  return t('latency.value', { value: formatNumber(value) })
}

/** "N requests since 10:42" — audit retention can cut the window short. */
function coverageLabel(data: RequestHealth | undefined, t: HomeT) {
  const sampleSize = asNumber(data?.sample_size)
  if (!sampleSize || !data?.since) return undefined
  const since = new Date(data.since)
  if (Number.isNaN(since.getTime())) return undefined
  return t('requestHealth.coverage', {
    requests: formatNumber(sampleSize),
    time: formatDateTime(since, {
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      month: '2-digit',
    }),
  })
}

type RequestHealthPanelProps = {
  data: RequestHealth | undefined
  disabled: boolean
  disabledMessage: string
  isError: boolean
  isLoading: boolean
  staleMessage?: string
  t: HomeT
}

export function RequestErrorsPanel({
  data,
  disabled,
  disabledMessage,
  isError,
  isLoading,
  staleMessage,
  t,
}: RequestHealthPanelProps) {
  const sampleSize = asNumber(data?.sample_size)
  return (
    <MetricPanel
      description={t('requestErrors.description')}
      errorHint={t('requestFailed')}
      icon={CircleAlert}
      isError={isError}
      isLoading={isLoading}
      staleMessage={staleMessage}
      subtitle={disabled ? undefined : coverageLabel(data, t)}
      title={t('requestErrors.title')}
      value={disabled || !sampleSize ? '—' : formatPercent(data?.error_rate)}
    >
      {disabled ? (
        <p className="text-xs text-muted-foreground">{disabledMessage}</p>
      ) : !sampleSize ? (
        <p className="text-xs text-muted-foreground">
          {t('requestHealth.empty')}
        </p>
      ) : (
        <>
          <DetailRow
            label={t('requestErrors.serverErrors')}
            value={formatNumber(data?.server_errors)}
          />
          <DetailRow
            label={t('requestErrors.clientErrors')}
            value={formatNumber(data?.client_errors)}
          />
          <Link to="/request-logs" className={LINK_CLASS}>
            {t('requestErrors.details')}
            <ArrowRight className="size-3" />
          </Link>
        </>
      )}
    </MetricPanel>
  )
}

export function LatencyPanel({
  data,
  disabled,
  disabledMessage,
  isError,
  isLoading,
  staleMessage,
  t,
}: RequestHealthPanelProps) {
  const latency: LatencySummary | null | undefined = data?.latency_ms
  const retrieval = data?.retrieval
  return (
    <MetricPanel
      description={t('latency.description')}
      errorHint={t('requestFailed')}
      icon={Timer}
      isError={isError}
      isLoading={isLoading}
      staleMessage={staleMessage}
      subtitle={disabled ? undefined : coverageLabel(data, t)}
      title={t('latency.title')}
      value={disabled || !latency ? '—' : formatMs(latency.p95, t)}
    >
      {disabled ? (
        <p className="text-xs text-muted-foreground">{disabledMessage}</p>
      ) : !latency ? (
        <p className="text-xs text-muted-foreground">
          {t('requestHealth.empty')}
        </p>
      ) : (
        <>
          <DetailRow
            label={t('latency.p50')}
            value={formatMs(latency.p50, t)}
          />
          <DetailRow
            label={t('latency.retrievalP95')}
            value={
              retrieval?.latency_ms
                ? formatMs(retrieval.latency_ms.p95, t)
                : '—'
            }
          />
          <DetailRow
            label={t('latency.retrievalCount')}
            value={formatNumber(retrieval?.count)}
          />
        </>
      )}
    </MetricPanel>
  )
}

export function FailedTasksPanel({
  data,
  disabled,
  disabledMessage,
  isError,
  isLoading,
  staleMessage,
  t,
}: {
  data: TaskSummary | undefined
  disabled: boolean
  disabledMessage: string
  isError: boolean
  isLoading: boolean
  staleMessage?: string
  t: HomeT
}) {
  return (
    <MetricPanel
      description={t('failedTasks.description')}
      errorHint={t('requestFailed')}
      icon={ListTodo}
      isError={isError}
      isLoading={isLoading}
      staleMessage={staleMessage}
      subtitle={
        data && !disabled
          ? t('failedTasks.checked', { tasks: formatNumber(data.checked) })
          : undefined
      }
      title={t('failedTasks.title')}
      value={disabled ? '—' : formatNumber(data?.failedToday)}
    >
      {disabled ? (
        <p className="text-xs text-muted-foreground">{disabledMessage}</p>
      ) : (
        <>
          <DetailRow
            label={t('failedTasks.active')}
            value={formatNumber(data?.active)}
          />
          <Link to="/tasks" className={LINK_CLASS}>
            {t('failedTasks.details')}
            <ArrowRight className="size-3" />
          </Link>
        </>
      )}
    </MetricPanel>
  )
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { ContextCommitsPanel } from './-components/context-commits-panel'
import { DashboardHeader } from './-components/dashboard-header'
import { HealthStrip } from './-components/health-strip'
import {
  FailedTasksPanel,
  LatencyPanel,
  RequestErrorsPanel,
} from './-components/ops-panels'
import {
  CacheHitRatePanel,
  ContextDataPanel,
  TodayRetrievalsPanel,
  TodayTokensPanel,
  TokensPerMinutePanel,
} from './-components/metric-panels'
import { SummaryErrorBanner } from './-components/summary-error-banner'
import { TokenTrendPanel } from './-components/token-trend-panel'
import { TpmTrendPanel } from './-components/tpm-trend-panel'
import type { TokenRateWindow } from './-types/dashboard'
import {
  fetchConsoleContextCommits,
  fetchConsoleDashboardSummary,
  fetchConsoleRequestHealth,
  fetchConsoleTokenRate,
  fetchConsoleTokenSeries,
} from './-lib/api'
import { isDisabledPayload } from './-lib/format'
import { summarizeTasks } from './-lib/tasks'
import { useAppConnection } from '#/hooks/use-app-connection'
import {
  CACHE_STATS_REFETCH_MS,
  fetchCacheStats,
  normalizeCacheStats,
} from '#/lib/cache-stats'
import {
  fetchMonitoringOverview,
  monitoringOverviewQueryKey,
} from '#/lib/monitoring-overview'
import { fetchTasks } from '#/routes/tasks/-lib/task-list'
import type {
  ConnectionDraft,
  ConnectionRole,
} from '#/hooks/use-app-connection'

export const Route = createFileRoute('/home')({
  component: HomePage,
})

function hashSecret(value: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(36)
}

function getMetricsScopeKey(
  connection: ConnectionDraft,
  connectionRole: ConnectionRole,
) {
  const metricsKey = connection.apiKey || connection.adminApiKey
  return {
    accountId: connection.accountId,
    baseUrl: connection.baseUrl,
    keyHash: metricsKey ? hashSecret(metricsKey) : 'none',
    keySource: connection.apiKey
      ? 'api'
      : connection.adminApiKey
        ? 'admin'
        : 'none',
    role: connectionRole,
    userId: connection.userId,
  }
}

/**
 * React Query keeps the last good data when a refetch fails. Only show an
 * error when there is nothing to show; otherwise keep the data and flag it.
 */
function queryErrorState(query: { data: unknown; isError: boolean }): {
  isError: boolean
  isStale: boolean
} {
  const hasData = query.data !== undefined
  return {
    isError: query.isError && !hasData,
    isStale: query.isError && hasData,
  }
}

function HomePage() {
  const { t } = useTranslation('home')
  const {
    connection,
    connectionRole,
    identityScopeKey,
    isConnectionRoleLoading,
    serverMode,
  } = useAppConnection()
  const isOnline = serverMode !== 'offline'
  const canQueryMetrics =
    !isConnectionRoleLoading && connectionRole !== 'unknown'
  const metricsScopeKey = getMetricsScopeKey(connection, connectionRole)

  const dashboard = useQuery({
    enabled: canQueryMetrics,
    queryFn: fetchConsoleDashboardSummary,
    queryKey: ['console-dashboard-summary', metricsScopeKey],
    refetchInterval: 30_000,
  })

  const tokenSeries = useQuery({
    enabled: canQueryMetrics,
    queryFn: fetchConsoleTokenSeries,
    queryKey: ['console-token-series', 'last-14-days', metricsScopeKey],
    refetchInterval: 60_000,
  })

  const [tpmWindow, setTpmWindow] = useState<TokenRateWindow>('24h')
  const tokenRate = useQuery({
    enabled: canQueryMetrics,
    queryFn: () => fetchConsoleTokenRate(tpmWindow),
    queryKey: ['console-token-rate', tpmWindow, metricsScopeKey],
    // Keep the previous window on screen while the new one loads.
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  })

  const contextCommits = useQuery({
    enabled: canQueryMetrics,
    queryFn: fetchConsoleContextCommits,
    queryKey: ['console-context-commits', 'last-365-days', metricsScopeKey],
    refetchInterval: 60_000,
  })

  // Only rendered when the server reports at least one CacheFS-wrapped mount.
  const cacheStats = useQuery({
    enabled: canQueryMetrics,
    queryFn: fetchCacheStats,
    queryKey: ['console-cache-stats', metricsScopeKey],
    refetchInterval: CACHE_STATS_REFETCH_MS,
    retry: false,
    select: normalizeCacheStats,
  })
  const cache = cacheStats.data?.enabled ? cacheStats.data : undefined

  const requestHealth = useQuery({
    enabled: canQueryMetrics,
    queryFn: () => fetchConsoleRequestHealth('24h'),
    queryKey: ['console-request-health', '24h', metricsScopeKey],
    refetchInterval: 60_000,
  })

  // Same key and filters as the Tasks page, so the two share one cached list.
  const tasks = useQuery({
    enabled: canQueryMetrics,
    queryFn: () => fetchTasks('all', 'all'),
    queryKey: ['tasks', identityScopeKey, 'all', 'all'],
    refetchInterval: 60_000,
    select: (items) => summarizeTasks(items),
  })

  // Same key as the Monitoring page, so the two share one cached result.
  const health = useQuery({
    enabled: isOnline,
    queryFn: fetchMonitoringOverview,
    queryKey: monitoringOverviewQueryKey(identityScopeKey),
    refetchInterval: 30_000,
    retry: false,
  })

  const summary = dashboard.data
  const identityUnavailable =
    !isConnectionRoleLoading && connectionRole === 'unknown'
  const metricsUnavailable = identityUnavailable || isDisabledPayload(summary)
  const unavailableMessage = identityUnavailable
    ? t('usageAccessRequired')
    : t('usageDisabled')
  const isMetricsLoading =
    isConnectionRoleLoading || (canQueryMetrics && dashboard.isPending)
  const isSeriesLoading =
    isConnectionRoleLoading || (canQueryMetrics && tokenSeries.isPending)
  const isTokenRateLoading =
    isConnectionRoleLoading || (canQueryMetrics && tokenRate.isPending)
  const isCommitsLoading =
    isConnectionRoleLoading || (canQueryMetrics && contextCommits.isPending)
  const isRequestHealthLoading =
    isConnectionRoleLoading || (canQueryMetrics && requestHealth.isPending)
  const isTasksLoading =
    isConnectionRoleLoading || (canQueryMetrics && tasks.isPending)

  const staleMessage = t('staleData')
  const dashboardState = queryErrorState(dashboard)
  const dashboardStale = dashboardState.isStale ? staleMessage : undefined
  const tokenRateState = queryErrorState(tokenRate)
  const tokenSeriesState = queryErrorState(tokenSeries)
  const commitsState = queryErrorState(contextCommits)
  const requestHealthState = queryErrorState(requestHealth)
  const tasksState = queryErrorState(tasks)
  const requestHealthDisabled =
    identityUnavailable || isDisabledPayload(requestHealth.data)

  const metricQueries = [
    dashboard,
    tokenSeries,
    tokenRate,
    contextCommits,
    cacheStats,
    requestHealth,
    tasks,
  ]
  const queries = [...metricQueries, health]
  const isFetching = queries.some((query) => query.isFetching)
  const updatedAt = Math.max(...queries.map((query) => query.dataUpdatedAt))
  // refetch() ignores `enabled`, so only refresh queries that may run.
  const refreshAll = () => {
    if (isOnline) void health.refetch()
    if (canQueryMetrics) for (const query of metricQueries) void query.refetch()
  }

  return (
    <div className="flex flex-col gap-5 pb-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {isOnline ? (
          <HealthStrip
            data={health.data}
            isError={health.isError}
            isLoading={health.isPending}
          />
        ) : (
          <span />
        )}
        <DashboardHeader
          disabled={!isOnline && !canQueryMetrics}
          isFetching={isFetching}
          onRefresh={refreshAll}
          t={t}
          updatedAt={updatedAt}
        />
      </div>

      {dashboardState.isError ? (
        <SummaryErrorBanner
          error={dashboard.error}
          isRetrying={dashboard.isFetching}
          onRetry={() => void dashboard.refetch()}
          t={t}
        />
      ) : null}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,18rem),1fr))] gap-4">
        <ContextDataPanel
          data={summary?.context_counts}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboardState.isError}
          isLoading={isMetricsLoading}
          staleMessage={dashboardStale}
          t={t}
        />
        <TodayTokensPanel
          data={summary?.today_tokens}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboardState.isError}
          isLoading={isMetricsLoading}
          staleMessage={dashboardStale}
          t={t}
        />
        <TokensPerMinutePanel
          data={summary?.tokens_per_minute}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboardState.isError}
          isLoading={isMetricsLoading}
          staleMessage={dashboardStale}
          t={t}
        />
        <TodayRetrievalsPanel
          data={summary?.today_retrievals}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboardState.isError}
          isLoading={isMetricsLoading}
          staleMessage={dashboardStale}
          t={t}
        />
        {cache ? <CacheHitRatePanel data={cache} t={t} /> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <RequestErrorsPanel
          data={requestHealth.data}
          disabled={requestHealthDisabled}
          disabledMessage={unavailableMessage}
          isError={requestHealthState.isError}
          isLoading={isRequestHealthLoading}
          staleMessage={requestHealthState.isStale ? staleMessage : undefined}
          t={t}
        />
        <LatencyPanel
          data={requestHealth.data}
          disabled={requestHealthDisabled}
          disabledMessage={unavailableMessage}
          isError={requestHealthState.isError}
          isLoading={isRequestHealthLoading}
          staleMessage={requestHealthState.isStale ? staleMessage : undefined}
          t={t}
        />
        <FailedTasksPanel
          data={tasks.data}
          disabled={identityUnavailable}
          disabledMessage={unavailableMessage}
          isError={tasksState.isError}
          isLoading={isTasksLoading}
          staleMessage={tasksState.isStale ? staleMessage : undefined}
          t={t}
        />
      </div>

      <TpmTrendPanel
        data={tokenRate.data}
        disabled={identityUnavailable}
        disabledMessage={unavailableMessage}
        isError={tokenRateState.isError}
        isLoading={isTokenRateLoading}
        isRefreshing={tokenRate.isPlaceholderData}
        onWindowChange={setTpmWindow}
        staleMessage={tokenRateState.isStale ? staleMessage : undefined}
        t={t}
        window={tpmWindow}
      />

      <TokenTrendPanel
        data={tokenSeries.data}
        disabled={identityUnavailable}
        disabledMessage={unavailableMessage}
        isError={tokenSeriesState.isError}
        isLoading={isSeriesLoading}
        staleMessage={tokenSeriesState.isStale ? staleMessage : undefined}
        t={t}
      />

      <ContextCommitsPanel
        data={contextCommits.data}
        disabled={identityUnavailable}
        disabledMessage={unavailableMessage}
        isError={commitsState.isError}
        isLoading={isCommitsLoading}
        staleMessage={commitsState.isStale ? staleMessage : undefined}
        t={t}
      />
    </div>
  )
}

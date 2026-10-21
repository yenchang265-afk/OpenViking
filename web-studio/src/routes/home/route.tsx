import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { ContextCommitsPanel } from './-components/context-commits-panel'
import {
  CacheHitRatePanel,
  ContextDataPanel,
  TodayRetrievalsPanel,
  TodayTokensPanel,
  TokensPerMinutePanel,
} from './-components/metric-panels'
import { TokenTrendPanel } from './-components/token-trend-panel'
import { TpmTrendPanel } from './-components/tpm-trend-panel'
import type { TokenRateWindow } from './-types/dashboard'
import {
  fetchConsoleContextCommits,
  fetchConsoleDashboardSummary,
  fetchConsoleTokenRate,
  fetchConsoleTokenSeries,
} from './-lib/api'
import { isDisabledPayload } from './-lib/format'
import { useAppConnection } from '#/hooks/use-app-connection'
import {
  CACHE_STATS_REFETCH_MS,
  fetchCacheStats,
  normalizeCacheStats,
} from '#/lib/cache-stats'
import { cn } from '#/lib/utils'
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

function HomePage() {
  const { t } = useTranslation('home')
  const { connection, connectionRole, isConnectionRoleLoading } =
    useAppConnection()
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

  return (
    <div className="flex flex-col gap-5 pb-8">
      <div
        className={cn(
          'grid gap-4 md:grid-cols-2',
          cache ? 'xl:grid-cols-5' : 'xl:grid-cols-4',
        )}
      >
        <ContextDataPanel
          data={summary?.context_counts}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboard.isError}
          isLoading={isMetricsLoading}
          t={t}
        />
        <TodayTokensPanel
          data={summary?.today_tokens}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboard.isError}
          isLoading={isMetricsLoading}
          t={t}
        />
        <TokensPerMinutePanel
          data={summary?.tokens_per_minute}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboard.isError}
          isLoading={isMetricsLoading}
          t={t}
        />
        <TodayRetrievalsPanel
          data={summary?.today_retrievals}
          disabled={metricsUnavailable}
          disabledMessage={unavailableMessage}
          isError={dashboard.isError}
          isLoading={isMetricsLoading}
          t={t}
        />
        {cache ? <CacheHitRatePanel data={cache} t={t} /> : null}
      </div>

      <TpmTrendPanel
        data={tokenRate.data}
        disabled={identityUnavailable}
        disabledMessage={unavailableMessage}
        isError={tokenRate.isError}
        isLoading={isTokenRateLoading}
        onWindowChange={setTpmWindow}
        t={t}
        window={tpmWindow}
      />

      <TokenTrendPanel
        data={tokenSeries.data}
        disabled={identityUnavailable}
        disabledMessage={unavailableMessage}
        isError={tokenSeries.isError}
        isLoading={isSeriesLoading}
        t={t}
      />

      <ContextCommitsPanel
        data={contextCommits.data}
        disabled={identityUnavailable}
        disabledMessage={unavailableMessage}
        isError={contextCommits.isError}
        isLoading={isCommitsLoading}
        t={t}
      />
    </div>
  )
}

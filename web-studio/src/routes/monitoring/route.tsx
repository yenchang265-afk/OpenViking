import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import {
  ActivityIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  CpuIcon,
  DatabaseIcon,
  HardDriveIcon,
  LayoutDashboardIcon,
  ListTodoIcon,
  LockKeyholeIcon,
  RefreshCwIcon,
  SearchIcon,
  ZapIcon,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Alert, AlertDescription, AlertTitle } from '#/components/ui/alert'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'

import { Card, CardContent, CardHeader, CardTitle } from '#/components/ui/card'
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
import { cn } from '#/lib/utils'
import { CacheStatsContent } from './-components/cache-stats-content'
import { ObserverStatusContent } from './-components/observer-status-content'
import { stripVersionPrefix } from './-lib/version'

type MonitoringSearch = {
  tab?: string
}

export const Route = createFileRoute('/monitoring')({
  component: MonitoringRoute,
  validateSearch: (search: Record<string, unknown>): MonitoringSearch => ({
    tab: typeof search.tab === 'string' ? search.tab : undefined,
  }),
})

const MONITOR_TYPES = [
  ['overview', LayoutDashboardIcon],
  ['queue', ListTodoIcon],
  ['vikingdb', DatabaseIcon],
  ['models', CpuIcon],
  ['filesystem', HardDriveIcon],
  ['lock', LockKeyholeIcon],
  ['retrieval', SearchIcon],
] as const

type MonitorType = (typeof MONITOR_TYPES)[number][0]

/** CacheFS stats come from metrics, not an observer component, so the tab has no health. */
const CACHE_TAB = 'cache'

type MonitorTab = MonitorType | typeof CACHE_TAB

function parseMonitorTab(value: string | undefined): MonitorTab {
  if (value === CACHE_TAB) return CACHE_TAB
  return MONITOR_TYPES.find(([name]) => name === value)?.[0] ?? 'overview'
}

function HealthBadge({
  healthy,
  label,
}: {
  healthy: boolean | undefined
  label: string
}) {
  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1.5 font-normal',
        healthy === undefined
          ? 'text-muted-foreground'
          : healthy
            ? 'border-emerald-500/30 text-emerald-600'
            : 'border-destructive/30 text-destructive',
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          healthy === undefined
            ? 'bg-muted-foreground'
            : healthy
              ? 'bg-emerald-500'
              : 'bg-destructive',
        )}
      />
      {label}
    </Badge>
  )
}

function MonitoringRoute() {
  const { i18n, t } = useTranslation('monitoringPage')
  const { identityScopeKey, serverMode } = useAppConnection()
  const navigate = useNavigate({ from: '/monitoring' })
  const activeType = parseMonitorTab(Route.useSearch().tab)
  const setActiveType = (tab: MonitorTab) =>
    void navigate({
      replace: true,
      search: { tab: tab === 'overview' ? undefined : tab },
    })
  const monitoringQuery = useQuery({
    enabled: serverMode !== 'offline',
    queryFn: fetchMonitoringOverview,
    queryKey: monitoringOverviewQueryKey(identityScopeKey),
    refetchInterval: 10_000,
    retry: false,
    staleTime: 5_000,
  })
  const cacheQuery = useQuery({
    enabled: serverMode !== 'offline',
    queryFn: fetchCacheStats,
    queryKey: ['console-cache-stats', identityScopeKey],
    refetchInterval: CACHE_STATS_REFETCH_MS,
    retry: false,
    select: normalizeCacheStats,
  })
  // Show the tab only with CacheFS on, unless a link asked for it directly.
  const showCacheTab =
    cacheQuery.data?.enabled === true || activeType === CACHE_TAB
  const overview = monitoringQuery.data
  const selectedComponent =
    activeType === 'overview' || activeType === CACHE_TAB
      ? undefined
      : overview?.components[activeType]
  const SelectedMonitorIcon =
    activeType === CACHE_TAB
      ? ZapIcon
      : (MONITOR_TYPES.find(([name]) => name === activeType)?.[1] ??
        ActivityIcon)
  const healthyCount = Object.values(overview?.components ?? {}).filter(
    (component) => component.is_healthy && !component.has_errors,
  ).length
  const totalCount = Object.keys(overview?.components ?? {}).length
  const unhealthyTypes = MONITOR_TYPES.slice(1)
    .map(([name]) => name)
    .filter((name) => {
      const component = overview?.components[name]
      return component && (!component.is_healthy || component.has_errors)
    })
  const updatedAt = monitoringQuery.dataUpdatedAt
    ? new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }).format(monitoringQuery.dataUpdatedAt)
    : undefined

  return (
    <div className="flex w-full min-w-0 flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              {t('title')}
            </h1>
            {overview?.version ? (
              <Badge variant="outline" className="font-mono font-normal">
                {t('version', {
                  version: stripVersionPrefix(overview.version),
                })}
              </Badge>
            ) : null}
          </div>
          <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
            {t('description')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {updatedAt ? (
            <span className="text-xs text-muted-foreground">
              {t('updatedAt', { time: updatedAt })}
            </span>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={monitoringQuery.isFetching}
            onClick={() => void monitoringQuery.refetch()}
          >
            <RefreshCwIcon
              className={cn(
                'size-4',
                monitoringQuery.isFetching && 'animate-spin',
              )}
            />
            {t('refresh')}
          </Button>
        </div>
      </header>

      {serverMode === 'offline' ? (
        <Alert>
          <CircleAlertIcon />
          <AlertTitle>{t('offline.title')}</AlertTitle>
          <AlertDescription>
            {t('offline.description')}{' '}
            <Link to="/settings" className="font-medium text-primary underline">
              {t('offline.action')}
            </Link>
          </AlertDescription>
        </Alert>
      ) : monitoringQuery.isLoading ? (
        <Card className="min-h-64 items-center justify-center">
          <RefreshCwIcon className="size-5 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{t('loading')}</p>
        </Card>
      ) : monitoringQuery.isError ? (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertTitle>{t('loadFailed')}</AlertTitle>
          <AlertDescription>
            {monitoringQuery.error instanceof Error
              ? monitoringQuery.error.message
              : String(monitoringQuery.error)}
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <Card className="gap-0 overflow-hidden py-0">
            <CardContent className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    'flex size-10 items-center justify-center rounded-xl',
                    overview?.healthy
                      ? 'bg-emerald-500/10 text-emerald-600'
                      : 'bg-destructive/10 text-destructive',
                  )}
                >
                  {overview?.healthy ? (
                    <CheckCircle2Icon className="size-5" />
                  ) : (
                    <CircleAlertIcon className="size-5" />
                  )}
                </div>
                <div>
                  <p className="font-medium">
                    {overview?.healthy
                      ? t('summary.healthy')
                      : t('summary.unhealthy')}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {t('summary.components', {
                      healthy: healthyCount,
                      total: totalCount,
                    })}
                  </p>
                  {unhealthyTypes.length > 0 ? (
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                      <span>{t('summary.attention')}</span>
                      {unhealthyTypes.map((name) => (
                        <Button
                          key={name}
                          type="button"
                          variant="link"
                          size="sm"
                          className="h-auto p-0 text-destructive"
                          onClick={() => setActiveType(name)}
                        >
                          {t(`tabs.${name}`)}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <HealthBadge
                healthy={overview?.healthy === true}
                label={
                  overview?.healthy
                    ? t('health.healthy')
                    : t('health.unhealthy')
                }
              />
            </CardContent>
          </Card>

          <div
            role="tablist"
            aria-label={t('tabs.label')}
            className="flex max-w-full gap-1 overflow-x-auto rounded-xl border bg-muted/20 p-1"
          >
            {MONITOR_TYPES.map(([name, Icon]) => (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={activeType === name}
                className={cn(
                  'flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground transition-colors',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  activeType === name
                    ? 'bg-background font-medium text-foreground shadow-xs'
                    : 'hover:bg-background/60 hover:text-foreground',
                )}
                onClick={() => setActiveType(name)}
              >
                <Icon className="size-4" />
                {t(`tabs.${name}`)}
              </button>
            ))}
            {showCacheTab ? (
              <button
                type="button"
                role="tab"
                aria-selected={activeType === CACHE_TAB}
                className={cn(
                  'flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground transition-colors',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  activeType === CACHE_TAB
                    ? 'bg-background font-medium text-foreground shadow-xs'
                    : 'hover:bg-background/60 hover:text-foreground',
                )}
                onClick={() => setActiveType(CACHE_TAB)}
              >
                <ZapIcon className="size-4" />
                {t(`tabs.${CACHE_TAB}`)}
              </button>
            ) : null}
          </div>

          {activeType === 'overview' ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {MONITOR_TYPES.slice(1).map(([name, Icon]) => {
                const component = overview?.components[name]
                const healthy = component
                  ? component.is_healthy && !component.has_errors
                  : undefined
                return (
                  <button
                    key={name}
                    type="button"
                    className="group rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => setActiveType(name)}
                  >
                    <Card className="h-full gap-3 p-4 transition-colors group-hover:border-primary/35 group-hover:bg-muted/15">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <div className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                            <Icon className="size-4" />
                          </div>
                          <CardTitle>{t(`tabs.${name}`)}</CardTitle>
                        </div>
                        <HealthBadge
                          healthy={healthy}
                          label={
                            healthy === undefined
                              ? t('health.unknown')
                              : healthy
                                ? t('health.healthy')
                                : t('health.unhealthy')
                          }
                        />
                      </div>
                      <p className="text-sm leading-6 text-muted-foreground">
                        {t(`detail.descriptions.${name}`)}
                      </p>
                    </Card>
                  </button>
                )
              })}
            </div>
          ) : (
            <Card className="gap-0 overflow-hidden py-0">
              <CardHeader className="border-b px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <SelectedMonitorIcon className="size-5 text-muted-foreground" />
                    <div>
                      <CardTitle>{t(`tabs.${activeType}`)}</CardTitle>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {t(`detail.descriptions.${activeType}`)}
                      </p>
                    </div>
                  </div>
                  {activeType === CACHE_TAB ? null : (
                    <HealthBadge
                      healthy={
                        selectedComponent
                          ? selectedComponent.is_healthy &&
                            !selectedComponent.has_errors
                          : undefined
                      }
                      label={
                        !selectedComponent
                          ? t('health.unknown')
                          : selectedComponent.is_healthy &&
                              !selectedComponent.has_errors
                            ? t('health.healthy')
                            : t('health.unhealthy')
                      }
                    />
                  )}
                </div>
              </CardHeader>
              <CardContent className="px-5 py-5">
                {activeType !== CACHE_TAB ? (
                  <ObserverStatusContent
                    status={selectedComponent?.status ?? ''}
                  />
                ) : cacheQuery.isError ? (
                  <Alert variant="destructive">
                    <CircleAlertIcon />
                    <AlertTitle>{t('cache.loadFailed')}</AlertTitle>
                    <AlertDescription>
                      {cacheQuery.error instanceof Error
                        ? cacheQuery.error.message
                        : String(cacheQuery.error)}
                    </AlertDescription>
                  </Alert>
                ) : cacheQuery.data ? (
                  <CacheStatsContent stats={cacheQuery.data} />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {t('loading')}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

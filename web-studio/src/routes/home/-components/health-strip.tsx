import { Link } from '@tanstack/react-router'
import { CircleAlertIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Skeleton } from '#/components/ui/skeleton'
import { MONITOR_COMPONENTS } from '#/lib/monitoring-overview'
import type {
  MonitoringOverview,
  ObserverComponent,
} from '#/lib/monitoring-overview'
import { cn } from '#/lib/utils'

type HealthLevel = 'healthy' | 'warning' | 'unhealthy'

/** Unhealthy is red; healthy but reporting errors is amber. */
function getHealthLevel(component: ObserverComponent): HealthLevel {
  if (!component.is_healthy) return 'unhealthy'
  return component.has_errors ? 'warning' : 'healthy'
}

const DOT_CLASS: Record<HealthLevel, string> = {
  healthy: 'bg-emerald-500',
  unhealthy: 'bg-destructive',
  warning: 'bg-amber-500',
}

const CHIP_CLASS: Record<HealthLevel, string> = {
  healthy: 'border-border/70 text-muted-foreground',
  unhealthy: 'border-destructive/40 text-destructive',
  warning: 'border-amber-500/40 text-amber-700 dark:text-amber-400',
}

const CHIP_BASE =
  'inline-flex min-h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring'

export function HealthStrip({
  data,
  isError,
  isLoading,
}: {
  data: MonitoringOverview | undefined
  isError: boolean
  isLoading: boolean
}) {
  const { t } = useTranslation('monitoringPage')

  if (isLoading) return <Skeleton className="h-7 w-80" />

  if (isError || !data) {
    return (
      <Link to="/monitoring" className={cn(CHIP_BASE, CHIP_CLASS.unhealthy)}>
        <CircleAlertIcon className="size-3.5" />
        {t('loadFailed')}
      </Link>
    )
  }

  const components = MONITOR_COMPONENTS.flatMap((name) => {
    // Skip components the server did not report.
    if (!(name in data.components)) return []
    return [{ level: getHealthLevel(data.components[name]), name }]
  })
  const healthyCount = components.filter(
    ({ level }) => level === 'healthy',
  ).length
  const overall: HealthLevel = data.healthy
    ? healthyCount === components.length
      ? 'healthy'
      : 'warning'
    : 'unhealthy'

  return (
    <nav
      aria-label={t('tabs.label')}
      className="flex flex-wrap items-center gap-2"
    >
      <Link
        to="/monitoring"
        title={t('summary.components', {
          healthy: healthyCount,
          total: components.length,
        })}
        className={cn(CHIP_BASE, CHIP_CLASS[overall])}
      >
        <span className={cn('size-2 rounded-full', DOT_CLASS[overall])} />
        {overall === 'healthy' ? t('summary.healthy') : t('summary.unhealthy')}
      </Link>
      {components.map(({ level, name }) => (
        <Link
          key={name}
          to="/monitoring"
          search={{ tab: name }}
          data-health={level}
          className={cn(CHIP_BASE, CHIP_CLASS[level])}
        >
          <span className={cn('size-1.5 rounded-full', DOT_CLASS[level])} />
          {t(`tabs.${name}`)}
        </Link>
      ))}
    </nav>
  )
}

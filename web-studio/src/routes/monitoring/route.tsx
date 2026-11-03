import { MonitoringRoute } from '#/features/workbench/monitoring/page'
import { createFileRoute } from '@tanstack/react-router'

type MonitoringSearch = {
  tab?: string
}

export const Route = createFileRoute('/monitoring')({
  component: MonitoringRoute,
  validateSearch: (search: Record<string, unknown>): MonitoringSearch => ({
    tab: typeof search.tab === 'string' ? search.tab : undefined,
  }),
})

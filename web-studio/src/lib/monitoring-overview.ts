import { getHealth, getObserverSystem, getOvResult } from '#/lib/ov-client'

/** Observer components, in display order. */
export const MONITOR_COMPONENTS = [
  'queue',
  'vikingdb',
  'models',
  'filesystem',
  'lock',
  'retrieval',
] as const

export type MonitorComponent = (typeof MONITOR_COMPONENTS)[number]

export type ObserverComponent = {
  has_errors: boolean
  is_healthy: boolean
  name: string
  status: string
}

export type MonitoringOverview = {
  components: Record<string, ObserverComponent>
  errors: string[]
  healthy: boolean
  version?: string
}

/** Shared by Monitoring and Home so both pages read one cached result. */
export function monitoringOverviewQueryKey(identityScopeKey: string) {
  return ['monitoring-overview', identityScopeKey] as const
}

export function isComponentHealthy(component: ObserverComponent): boolean {
  return component.is_healthy && !component.has_errors
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeComponent(
  name: string,
  value: unknown,
): ObserverComponent | undefined {
  if (!isRecord(value)) return undefined

  return {
    has_errors: value.has_errors === true,
    is_healthy: value.is_healthy === true,
    name: typeof value.name === 'string' ? value.name : name,
    status: typeof value.status === 'string' ? value.status : '',
  }
}

export async function fetchMonitoringOverview(): Promise<MonitoringOverview> {
  const [health, observer] = await Promise.all([
    getOvResult<Record<string, unknown>>(getHealth()),
    getOvResult<Record<string, unknown>>(getObserverSystem()),
  ])
  const rawComponents = isRecord(observer.components) ? observer.components : {}
  const components: Record<string, ObserverComponent> = {}

  for (const name of MONITOR_COMPONENTS) {
    const component = normalizeComponent(name, rawComponents[name])
    if (component) components[name] = component
  }

  return {
    components,
    errors: Array.isArray(observer.errors)
      ? observer.errors.filter(
          (error): error is string => typeof error === 'string',
        )
      : [],
    healthy: observer.is_healthy === true,
    version: typeof health.version === 'string' ? health.version : undefined,
  }
}

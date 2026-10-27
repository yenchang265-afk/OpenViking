import { describe, expect, it, vi } from 'vitest'

import {
  fetchMonitoringOverview,
  isComponentHealthy,
} from './monitoring-overview'

const ov = vi.hoisted(() => ({
  health: vi.fn(),
  observer: vi.fn(),
}))
vi.mock('#/lib/ov-client', () => ({
  getHealth: ov.health,
  getObserverSystem: ov.observer,
  getOvResult: (value: unknown) => Promise.resolve(value),
}))

describe('fetchMonitoringOverview', () => {
  it('keeps known components and drops malformed fields', async () => {
    ov.health.mockReturnValue({ version: 'v1.2.3' })
    ov.observer.mockReturnValue({
      components: {
        queue: { has_errors: true, is_healthy: true, status: 'busy' },
        models: 'not-an-object',
        unknown: { is_healthy: true },
      },
      errors: ['disk full', 42],
      is_healthy: false,
    })

    const overview = await fetchMonitoringOverview()

    expect(overview).toEqual({
      components: {
        queue: {
          has_errors: true,
          is_healthy: true,
          name: 'queue',
          status: 'busy',
        },
      },
      errors: ['disk full'],
      healthy: false,
      version: 'v1.2.3',
    })
  })
})

describe('isComponentHealthy', () => {
  it('treats a healthy component that reports errors as not healthy', () => {
    const base = { name: 'queue', status: '' }
    expect(
      isComponentHealthy({ ...base, has_errors: false, is_healthy: true }),
    ).toBe(true)
    expect(
      isComponentHealthy({ ...base, has_errors: true, is_healthy: true }),
    ).toBe(false)
  })
})

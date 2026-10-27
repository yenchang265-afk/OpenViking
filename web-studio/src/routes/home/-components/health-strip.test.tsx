// @vitest-environment jsdom
import type * as React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type { MonitoringOverview } from '#/lib/monitoring-overview'

import { HealthStrip } from './health-strip'

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    search,
    to,
    ...rest
  }: {
    children: React.ReactNode
    search?: { tab?: string }
    to: string
  }) => (
    <a href={search?.tab ? `${to}?tab=${search.tab}` : to} {...rest}>
      {children}
    </a>
  ),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(cleanup)

function component(is_healthy: boolean, has_errors = false) {
  return { has_errors, is_healthy, name: '', status: '' }
}

const healthy: MonitoringOverview = {
  components: {
    models: component(true),
    queue: component(true),
  },
  errors: [],
  healthy: true,
}

it('links each component to its monitoring tab', () => {
  render(<HealthStrip data={healthy} isError={false} isLoading={false} />)
  expect(screen.getByText('summary.healthy')).toBeTruthy()
  const queue = screen.getByText('tabs.queue').closest('a')!
  expect(queue.getAttribute('href')).toBe('/monitoring?tab=queue')
  expect(queue.dataset.health).toBe('healthy')
  // Components the server did not report are not shown.
  expect(screen.queryByText('tabs.lock')).toBeNull()
})

it('marks warnings amber and failures red', () => {
  render(
    <HealthStrip
      data={{
        ...healthy,
        components: {
          models: component(false),
          queue: component(true, true),
        },
        healthy: false,
      }}
      isError={false}
      isLoading={false}
    />,
  )
  expect(screen.getByText('summary.unhealthy')).toBeTruthy()
  expect(screen.getByText('tabs.queue').closest('a')!.dataset.health).toBe(
    'warning',
  )
  expect(screen.getByText('tabs.models').closest('a')!.dataset.health).toBe(
    'unhealthy',
  )
})

it('flags degraded components even when the system reports healthy', () => {
  render(
    <HealthStrip
      data={{ ...healthy, components: { queue: component(true, true) } }}
      isError={false}
      isLoading={false}
    />,
  )
  expect(screen.getByText('summary.unhealthy')).toBeTruthy()
})

it('points to the Monitoring page when health cannot be loaded', () => {
  render(<HealthStrip data={undefined} isError isLoading={false} />)
  expect(
    screen.getByText('loadFailed').closest('a')!.getAttribute('href'),
  ).toBe('/monitoring')
})

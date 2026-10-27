// @vitest-environment jsdom
import type * as React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import type { HomeT, RequestHealth } from '../-types/dashboard'
import {
  FailedTasksPanel,
  LatencyPanel,
  RequestErrorsPanel,
} from './ops-panels'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}))

const t = ((key: string, options?: Record<string, unknown>) =>
  options ? `${key} ${JSON.stringify(options)}` : key) as HomeT

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const health: RequestHealth = {
  client_errors: 3,
  error_rate: 0.025,
  latency_ms: { p50: 12.5, p95: 480 },
  retrieval: { count: 7, latency_ms: { p50: 40, p95: 95 } },
  sample_size: 120,
  server_errors: 3,
  since: '2026-10-27T08:00:00+00:00',
  window: '24h',
}

const baseProps = {
  disabled: false,
  disabledMessage: 'off',
  isError: false,
  isLoading: false,
  t,
}

it('shows the server error rate with counts and a link to request logs', () => {
  render(<RequestErrorsPanel {...baseProps} data={health} />)
  expect(screen.getByText('2.5%')).toBeTruthy()
  expect(screen.getByText('requestErrors.serverErrors')).toBeTruthy()
  expect(screen.getAllByText('3')).toHaveLength(2)
  expect(
    screen
      .getByText('requestErrors.details')
      .closest('a')!
      .getAttribute('href'),
  ).toBe('/request-logs')
  // The window may be cut short by audit retention, so say what it covers.
  expect(
    screen.getByText(/requestHealth\.coverage.*"requests":"120"/),
  ).toBeTruthy()
})

it('says when no requests were audited instead of showing 0%', () => {
  render(
    <RequestErrorsPanel
      {...baseProps}
      data={{ ...health, sample_size: 0, since: null }}
    />,
  )
  expect(screen.getByText('—')).toBeTruthy()
  expect(screen.getByText('requestHealth.empty')).toBeTruthy()
  expect(screen.queryByText('0%')).toBeNull()
})

it('explains its own request failure', () => {
  render(<RequestErrorsPanel {...baseProps} data={undefined} isError />)
  expect(screen.getByText('—')).toBeTruthy()
  expect(screen.getByText('requestFailed')).toBeTruthy()
})

it('shows p95 latency with p50 and retrieval latency', () => {
  render(<LatencyPanel {...baseProps} data={health} />)
  expect(screen.getByText('latency.value {"value":"480"}')).toBeTruthy()
  expect(screen.getByText('latency.value {"value":"12.5"}')).toBeTruthy()
  expect(screen.getByText('latency.value {"value":"95"}')).toBeTruthy()
  expect(screen.getByText('7')).toBeTruthy()
})

it('shows the disabled message when usage audit is off', () => {
  render(<LatencyPanel {...baseProps} data={health} disabled />)
  expect(screen.getByText('—')).toBeTruthy()
  expect(screen.getByText('off')).toBeTruthy()
})

it('shows recent failed tasks with active work and a link to tasks', () => {
  render(
    <FailedTasksPanel
      {...baseProps}
      data={{ active: 4, checked: 200, failedToday: 2 }}
    />,
  )
  expect(screen.getByText('2')).toBeTruthy()
  expect(screen.getByText('4')).toBeTruthy()
  expect(screen.getByText('failedTasks.checked {"tasks":"200"}')).toBeTruthy()
  expect(
    screen.getByText('failedTasks.details').closest('a')!.getAttribute('href'),
  ).toBe('/tasks')
})

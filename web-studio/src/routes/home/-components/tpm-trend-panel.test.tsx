// @vitest-environment jsdom

import type { PropsWithChildren } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type { HomeT, TokenRate } from '../-types/dashboard'
import { TpmTrendPanel } from './tpm-trend-panel'

vi.mock('recharts', () => ({
  Area: ({ dataKey }: { dataKey: string }) => (
    <g data-testid={`area-${dataKey}`} />
  ),
  CartesianGrid: () => null,
  ComposedChart: ({ children }: PropsWithChildren) => <svg>{children}</svg>,
  Line: ({ dataKey }: { dataKey: string }) => (
    <g data-testid={`line-${dataKey}`} />
  ),
  ResponsiveContainer: ({ children }: PropsWithChildren) => <>{children}</>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}))

afterEach(cleanup)

const t = ((key: string) => key) as HomeT

const data: TokenRate = {
  average_total: 27.5,
  bucket_minutes: 5,
  items: [
    {
      start: '2026-05-12T10:20:00+00:00',
      vlm_input: 100,
      vlm_output: 0,
      embedding_input: 0,
      total: 100,
      peak_total: 400,
    },
  ],
  peak: {
    minute: '2026-05-12T10:21:00+00:00',
    vlm_input: 1000,
    vlm_output: 200,
    embedding_input: 0,
    rerank: 34,
    total: 1234,
  },
  window: '24h',
}

function renderPanel(props: Partial<Parameters<typeof TpmTrendPanel>[0]> = {}) {
  const onWindowChange = vi.fn()
  render(
    <TpmTrendPanel
      data={data}
      isError={false}
      isLoading={false}
      onWindowChange={onWindowChange}
      t={t}
      window="24h"
      {...props}
    />,
  )
  return onWindowChange
}

it('shows the peak and average tokens per minute for the window', async () => {
  renderPanel()
  expect(screen.getByText('1,234')).toBeTruthy()
  expect(screen.getByText('27.5')).toBeTruthy()
  // Wider buckets plot the busiest minute next to the average.
  expect(await screen.findByTestId('line-peak_total')).toBeTruthy()
})

it('plots rerank tokens as their own series', async () => {
  renderPanel()
  expect(await screen.findByTestId('area-rerank')).toBeTruthy()
  expect(screen.getByText('tpmTrend.rerank')).toBeTruthy()
})

it('plots bot tokens as their own series', async () => {
  renderPanel()
  expect(await screen.findByTestId('area-bot_input')).toBeTruthy()
  expect(screen.getByTestId('area-bot_output')).toBeTruthy()
  expect(screen.getByText('todayTokens.botInput')).toBeTruthy()
  expect(screen.getByText('todayTokens.botOutput')).toBeTruthy()
})

it('switches the window from the toggle', () => {
  const onWindowChange = renderPanel()
  const current = screen.getByRole('button', { name: 'tpmTrend.windows.24h' })
  expect(current.getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(screen.getByRole('button', { name: 'tpmTrend.windows.1h' }))
  expect(onWindowChange).toHaveBeenCalledWith('1h')
})

it('omits the separate peak line for one-minute buckets', async () => {
  renderPanel({ data: { ...data, bucket_minutes: 1 } })
  await screen.findByText('1,234')
  expect(screen.queryByTestId('line-peak_total')).toBeNull()
})

it('explains when the window has no minute data yet', () => {
  renderPanel({ data: { ...data, items: [], peak: null } })
  expect(screen.getByText('tpmTrend.empty')).toBeTruthy()
})

it('shows the unavailable message when usage is disabled', () => {
  renderPanel({ data: { enabled: false }, disabledMessage: 'off' })
  expect(screen.getByText('off')).toBeTruthy()
})

it('dims the chart while another window loads', () => {
  renderPanel({ isRefreshing: true })
  expect(screen.getByText('1,234').closest('[aria-busy="true"]')).toBeTruthy()
})

it('flags data left over from a failed refresh', () => {
  renderPanel({ staleMessage: 'stale' })
  expect(screen.getByRole('status').textContent).toBe('stale')
  expect(screen.getByText('1,234')).toBeTruthy()
})

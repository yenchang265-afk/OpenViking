// @vitest-environment jsdom
import type * as React from 'react'
import type { ComponentType } from 'react'
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { OvClientError } from '#/lib/ov-client'

import { Route } from './route'

const state = vi.hoisted(() => ({
  role: 'user',
  serverMode: 'online',
  health: vi.fn(),
  requestHealth: vi.fn(),
  tasks: vi.fn(),
  summary: vi.fn(),
  tokens: vi.fn(),
  tokenRate: vi.fn(),
  commits: vi.fn(),
  cache: vi.fn(),
}))
vi.mock('#/hooks/use-app-connection', () => ({
  useAppConnection: () => ({
    connection: {
      baseUrl: 'http://localhost:1933',
      accountId: 'account-a',
      userId: 'alice',
      apiKey: '',
      adminApiKey: '',
    },
    connectionRole: state.role,
    identityScopeKey: 'scope-a',
    isConnectionRoleLoading: false,
    serverMode: state.serverMode,
  }),
}))
vi.mock('./-lib/api', () => ({
  fetchConsoleDashboardSummary: state.summary,
  fetchConsoleTokenSeries: state.tokens,
  fetchConsoleTokenRate: state.tokenRate,
  fetchConsoleContextCommits: state.commits,
  fetchConsoleRequestHealth: state.requestHealth,
}))
vi.mock('#/routes/tasks/-lib/task-list', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchTasks: state.tasks,
}))
vi.mock('#/lib/monitoring-overview', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchMonitoringOverview: state.health,
}))
vi.mock('#/lib/cache-stats', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchCacheStats: state.cache,
}))
vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
beforeEach(() => {
  state.role = 'user'
  state.serverMode = 'online'
  state.health.mockReset().mockResolvedValue({
    components: {
      queue: { has_errors: false, is_healthy: true, name: 'queue', status: '' },
    },
    errors: [],
    healthy: true,
  })
  state.summary.mockReset().mockResolvedValue({
    context_counts: { total: 0 },
    today_tokens: { total: 0 },
    today_retrievals: { total: 0 },
    tokens_per_minute: { total: 0 },
  })
  state.tokens.mockReset().mockResolvedValue({ items: [] })
  state.tokenRate.mockReset().mockResolvedValue({ items: [], peak: null })
  state.commits.mockReset().mockResolvedValue({ items: [] })
  state.requestHealth.mockReset().mockResolvedValue({
    client_errors: 0,
    error_rate: 0,
    latency_ms: { p50: 5, p95: 9 },
    retrieval: { count: 1, latency_ms: { p50: 5, p95: 9 } },
    sample_size: 10,
    server_errors: 0,
    since: '2026-10-27T08:00:00+00:00',
    window: '24h',
  })
  state.tasks.mockReset().mockResolvedValue([])
  state.cache.mockReset().mockResolvedValue({ enabled: false })
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const SUMMARY_TITLES = [
  'contextData.title',
  'todayTokens.title',
  'todayRetrievals.title',
  'tokensPerMinute.title',
]

/** Matches inside the four summary cards only, not the rest of the page. */
function summaryText(text: string) {
  return SUMMARY_TITLES.flatMap((title) => {
    const panel = screen
      .queryByRole('heading', { name: title })
      ?.closest('section')
    return panel ? within(panel).queryAllByText(text) : []
  })
}

async function renderHome(
  client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  }),
) {
  const Home = Route.options.component as ComponentType & {
    preload?: () => Promise<unknown>
  }
  await Home.preload?.()
  const view = render(
    <QueryClientProvider client={client}>
      <Home />
    </QueryClientProvider>,
  )
  return () => {
    view.unmount()
    client.clear()
  }
}

it.each(['unknown', 'disabled'])(
  'shows unavailable values for %s data',
  async (reason) => {
    if (reason === 'unknown') state.role = 'unknown'
    else state.summary.mockResolvedValue({ enabled: false })
    const close = await renderHome()
    try {
      await waitFor(() => expect(summaryText('—')).toHaveLength(4), {
        timeout: 2000,
      })
      if (reason === 'unknown') expect(state.summary).not.toHaveBeenCalled()
    } finally {
      close()
    }
  },
)

it('renders successful zero measurements after the response completes', async () => {
  const zero = {
    context_counts: { total: 0 },
    today_tokens: { total: 0 },
    today_retrievals: { total: 0 },
    tokens_per_minute: { total: 0 },
  }
  let complete!: (value: typeof zero) => void
  state.summary.mockImplementation(
    () =>
      new Promise<typeof zero>((resolve) => {
        complete = resolve
      }),
  )
  const close = await renderHome()
  try {
    await waitFor(() => expect(state.summary).toHaveBeenCalled())
    expect(summaryText('0')).toHaveLength(0)
    await act(async () => {
      complete(zero)
    })
    await screen.findByText('contextData.files')
    for (const title of [
      'contextData.title',
      'todayTokens.title',
      'todayRetrievals.title',
      'tokensPerMinute.title',
    ]) {
      const panel = screen
        .getByRole('heading', { name: title })
        .closest('section')!
      expect(
        within(panel).getByText('0', { selector: '.text-4xl span' }),
      ).toBeTruthy()
      expect(within(panel).queryByText('—')).toBeNull()
    }
  } finally {
    close()
  }
})

it('renders tokens per minute with its breakdown', async () => {
  state.summary.mockResolvedValue({
    context_counts: { total: 0 },
    today_tokens: { total: 0 },
    today_retrievals: { total: 0 },
    tokens_per_minute: {
      bot_input: 30,
      bot_output: 4,
      embedding_input: 1.7,
      total: 50.7,
      vlm_input: 10,
      vlm_output: 5,
      window_minutes: 90,
    },
  })
  const close = await renderHome()
  try {
    const heading = await screen.findByRole('heading', {
      name: 'tokensPerMinute.title',
    })
    const panel = heading.closest('section')!
    await waitFor(() =>
      expect(
        within(panel).getByText('50.7', { selector: '.text-4xl span' }),
      ).toBeTruthy(),
    )
    expect(within(panel).getByText('10')).toBeTruthy()
    expect(within(panel).getByText('5')).toBeTruthy()
    expect(within(panel).getByText('1.7')).toBeTruthy()
    expect(within(panel).getByText('tokensPerMinute.botInput')).toBeTruthy()
    expect(within(panel).getByText('30')).toBeTruthy()
    expect(within(panel).getByText('4')).toBeTruthy()
    expect(within(panel).getByText('tokensPerMinute.window')).toBeTruthy()
  } finally {
    close()
  }
})

it('loads the TPM trend for the last 24 hours and refetches per window', async () => {
  const close = await renderHome()
  try {
    await waitFor(() => expect(state.tokenRate).toHaveBeenCalledWith('24h'))
    await screen.findByText('tpmTrend.empty')
    act(() => {
      screen.getByRole('button', { name: 'tpmTrend.windows.7d' }).click()
    })
    await waitFor(() => expect(state.tokenRate).toHaveBeenCalledWith('7d'))
  } finally {
    close()
  }
})

it('uses each series result when the summary is disabled', async () => {
  state.summary.mockResolvedValue({ enabled: false })
  const close = await renderHome()
  try {
    await waitFor(
      () => expect(screen.getByText('tokenTrend.empty')).toBeTruthy(),
      { timeout: 2000 },
    )
    expect(screen.getByText('contextCommits.empty')).toBeTruthy()
  } finally {
    close()
  }
})

it.each(['loading', 'error'])(
  'withholds metric detail values during %s',
  async (stateName) => {
    if (stateName === 'loading')
      state.summary.mockImplementation(() => new Promise(() => {}))
    else state.summary.mockRejectedValue(new Error('Request failed'))
    const close = await renderHome()
    try {
      await waitFor(() => expect(state.summary).toHaveBeenCalled())
      if (stateName === 'error') await screen.findByText('summaryError.title')
      expect(screen.queryByText('contextData.files')).toBeNull()
      expect(summaryText('0')).toHaveLength(0)
    } finally {
      close()
    }
  },
)

it('shows the overall cache hit rate when CacheFS is enabled', async () => {
  state.cache.mockResolvedValue({
    bypasses: 2,
    enabled: true,
    hit_rate: 0.75,
    hits: 30,
    misses: 10,
    operations: [{ hits: 30, misses: 10, operation: 'read' }],
  })
  const close = await renderHome()
  try {
    const heading = await screen.findByRole('heading', {
      name: 'cacheHitRate.title',
    })
    const panel = heading.closest('section')!
    expect(
      within(panel).getByText('75.0%', { selector: '.text-4xl span' }),
    ).toBeTruthy()
    expect(within(panel).getByText('30')).toBeTruthy()
    expect(within(panel).getByText('10')).toBeTruthy()
    expect(within(panel).getByText('cacheHitRate.details')).toBeTruthy()
  } finally {
    close()
  }
})

it('hides the cache hit rate when CacheFS is disabled', async () => {
  const close = await renderHome()
  try {
    await waitFor(() => expect(state.cache).toHaveBeenCalled())
    await screen.findByText('contextData.files')
    expect(
      screen.queryByRole('heading', { name: 'cacheHitRate.title' }),
    ).toBeNull()
  } finally {
    close()
  }
})

it('keeps the last loaded values when a refetch fails', async () => {
  state.summary.mockResolvedValue({
    context_counts: { total: 42 },
    today_tokens: { total: 0 },
    today_retrievals: { total: 0 },
    tokens_per_minute: { total: 0 },
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const close = await renderHome(client)
  try {
    const heading = await screen.findByRole('heading', {
      name: 'contextData.title',
    })
    const panel = heading.closest('section')!
    await within(panel).findByText('42', { selector: '.text-4xl span' })

    state.summary.mockRejectedValue(new Error('boom'))
    await act(async () => {
      await client.refetchQueries({ queryKey: ['console-dashboard-summary'] })
    })

    await within(panel).findByText('staleData')
    expect(
      within(panel).getByText('42', { selector: '.text-4xl span' }),
    ).toBeTruthy()
    expect(screen.queryAllByText('requestFailed')).toHaveLength(0)
  } finally {
    close()
  }
})

it('keeps the previous TPM window on screen while the next one loads', async () => {
  state.tokenRate.mockResolvedValue({
    average_total: 7,
    bucket_minutes: 5,
    items: [{ start: '2026-05-12T10:20:00+00:00', total: 7 }],
    peak: { minute: '2026-05-12T10:21:00+00:00', total: 1234 },
    window: '24h',
  })
  const close = await renderHome()
  try {
    await screen.findByText('1,234')
    state.tokenRate.mockImplementation(() => new Promise(() => {}))
    act(() => {
      screen.getByRole('button', { name: 'tpmTrend.windows.7d' }).click()
    })
    await waitFor(() => expect(state.tokenRate).toHaveBeenCalledWith('7d'))
    const peak = screen.getByText('1,234')
    expect(peak.closest('[aria-busy="true"]')).toBeTruthy()
  } finally {
    close()
  }
})

it('explains a failed summary once, with details and a retry', async () => {
  state.summary.mockRejectedValue(
    new OvClientError({
      code: 'UNAVAILABLE',
      message: 'usage store unreachable',
      requestId: 'req-123',
      statusCode: 503,
    }),
  )
  const close = await renderHome()
  try {
    const banner = await screen.findByRole('alert')
    expect(within(banner).getByText('summaryError.title')).toBeTruthy()
    expect(within(banner).getByText('usage store unreachable')).toBeTruthy()
    expect(within(banner).getByText('req-123')).toBeTruthy()
    expect(banner.textContent).toContain('UNAVAILABLE')
    // Cards stay quiet; the banner carries the reason.
    expect(summaryText('—')).toHaveLength(4)
    expect(screen.queryAllByText('requestFailed')).toHaveLength(0)

    state.summary.mockResolvedValue({
      context_counts: { total: 0 },
      today_tokens: { total: 0 },
      today_retrievals: { total: 0 },
      tokens_per_minute: { total: 0 },
    })
    act(() => {
      within(banner).getByRole('button', { name: 'summaryError.retry' }).click()
    })
    await screen.findByText('contextData.files')
    expect(screen.queryByRole('alert')).toBeNull()
  } finally {
    close()
  }
})

it('refreshes every dashboard query and shows when it last updated', async () => {
  const close = await renderHome()
  try {
    await screen.findByText('updatedAt')
    for (const fetcher of [state.summary, state.tokens, state.commits]) {
      expect(fetcher).toHaveBeenCalledTimes(1)
    }
    act(() => {
      screen.getByRole('button', { name: 'refresh' }).click()
    })
    await waitFor(() => {
      for (const fetcher of [
        state.summary,
        state.tokens,
        state.tokenRate,
        state.commits,
        state.cache,
        state.health,
        state.requestHealth,
        state.tasks,
      ]) {
        expect(fetcher).toHaveBeenCalledTimes(2)
      }
    })
  } finally {
    close()
  }
})

it('refreshes only health until the connection identity resolves', async () => {
  state.role = 'unknown'
  const close = await renderHome()
  try {
    await screen.findByText('summary.healthy')
    act(() => {
      screen.getByRole('button', { name: 'refresh' }).click()
    })
    await waitFor(() => expect(state.health).toHaveBeenCalledTimes(2))
    expect(state.summary).not.toHaveBeenCalled()
  } finally {
    close()
  }
})

it('disables refresh when nothing can be queried', async () => {
  state.role = 'unknown'
  state.serverMode = 'offline'
  const close = await renderHome()
  try {
    const button = await screen.findByRole('button', { name: 'refresh' })
    expect(button.hasAttribute('disabled')).toBe(true)
    expect(screen.queryByText('updatedAt')).toBeNull()
  } finally {
    close()
  }
})

it('shows system health above the metrics', async () => {
  const close = await renderHome()
  try {
    expect(await screen.findByText('summary.healthy')).toBeTruthy()
    expect(screen.getByText('tabs.queue')).toBeTruthy()
  } finally {
    close()
  }
})

it('skips the health check while the server is offline', async () => {
  state.serverMode = 'offline'
  const close = await renderHome()
  try {
    await screen.findByRole('button', { name: 'refresh' })
    expect(state.health).not.toHaveBeenCalled()
    expect(screen.queryByText('summary.healthy')).toBeNull()
    expect(screen.queryByText('loadFailed')).toBeNull()
  } finally {
    close()
  }
})

it('shows request errors, latency and failed tasks for the last day', async () => {
  state.requestHealth.mockResolvedValue({
    client_errors: 1,
    error_rate: 0.5,
    latency_ms: { p50: 5, p95: 9 },
    retrieval: { count: 0, latency_ms: null },
    sample_size: 2,
    server_errors: 1,
    since: '2026-10-27T08:00:00+00:00',
    window: '24h',
  })
  state.tasks.mockResolvedValue([
    { created_at_iso: new Date().toISOString(), status: 'failed' },
    { status: 'running' },
  ])
  const close = await renderHome()
  try {
    const errors = (
      await screen.findByRole('heading', { name: 'requestErrors.title' })
    ).closest('section')!
    await within(errors).findByText('50%')
    expect(state.requestHealth).toHaveBeenCalledWith('24h')
    const tasksPanel = screen
      .getByRole('heading', { name: 'failedTasks.title' })
      .closest('section')!
    await waitFor(() =>
      expect(
        within(tasksPanel).getByText('1', { selector: '.text-4xl span' }),
      ).toBeTruthy(),
    )
    expect(state.tasks).toHaveBeenCalledWith('all', 'all')
  } finally {
    close()
  }
})

it('marks request health unavailable when usage audit is off', async () => {
  state.requestHealth.mockResolvedValue({ enabled: false })
  const close = await renderHome()
  try {
    const latency = (
      await screen.findByRole('heading', { name: 'latency.title' })
    ).closest('section')!
    await within(latency).findByText('usageDisabled')
    expect(within(latency).getByText('—')).toBeTruthy()
  } finally {
    close()
  }
})

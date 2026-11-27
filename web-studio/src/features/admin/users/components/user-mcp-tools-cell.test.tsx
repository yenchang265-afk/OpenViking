// @vitest-environment jsdom
import { UserMcpToolsCell } from '#/features/admin/users/components/user-mcp-tools-cell'
import type { UserMcpTools } from '#/shared/api/admin'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetch: vi.fn(),
  update: vi.fn(),
  error: vi.fn(),
}))
vi.mock('#/shared/api/admin', () => ({
  fetchUserMcpTools: api.fetch,
  updateUserMcpTools: api.update,
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: api.error } }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && 'count' in options
        ? `${key}:${String(options.count)}/${String(options.total)}`
        : key,
  }),
}))
vi.mock('#/shared/ui/dialog', () => {
  const Container = ({ children }: { children: ReactNode }) => children
  return {
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
      open ? children : null,
    DialogContent: Container,
    DialogHeader: Container,
    DialogTitle: Container,
    DialogDescription: Container,
  }
})
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

const tools = [
  { name: 'find', description: 'Search', read_only: true },
  { name: 'read', description: 'Read', read_only: true },
  { name: 'write', description: 'Write', read_only: false },
]
function settings(allowed: string[] | null): UserMcpTools {
  return {
    account_id: 'a',
    user_id: 'u',
    allowed_tools: allowed,
    available_tools: tools,
  }
}
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <UserMcpToolsCell
        connection={{
          baseUrl: 'http://localhost',
          apiKey: 'key',
          accountId: 'a',
          userId: 'admin',
        }}
        user={{ accountId: 'a', userId: 'u', role: 'user' }}
      />
    </QueryClientProvider>,
  )
}

it('summarizes unrestricted, empty and partial allowlists', async () => {
  for (const [allowed, label] of [
    [null, 'mcpTools.all'],
    [[], 'mcpTools.none'],
    [['find'], 'mcpTools.some:1/3'],
  ] as const) {
    api.fetch.mockResolvedValue(
      settings(allowed === null ? null : [...allowed]),
    )
    mount()
    expect(await screen.findByText(label)).toBeTruthy()
    cleanup()
  }
})

it('restricts an unrestricted user to read-only tools', async () => {
  api.fetch.mockResolvedValue(settings(null))
  api.update.mockResolvedValue(settings(['find', 'read']))
  mount()
  fireEvent.click(
    await screen.findByRole('button', { name: 'mcpTools.editUser' }),
  )
  fireEvent.click(await screen.findByRole('switch'))
  fireEvent.click(
    screen.getByRole('button', { name: 'mcpTools.selectReadOnly' }),
  )
  fireEvent.click(screen.getByRole('button', { name: 'mcpTools.save' }))
  await waitFor(() =>
    expect(api.update).toHaveBeenCalledWith(expect.anything(), 'a', 'u', [
      'find',
      'read',
    ]),
  )
})

it('clears a restriction and keeps save error details', async () => {
  api.fetch.mockResolvedValue(settings(['find']))
  api.update.mockRejectedValue(new Error('server validation error'))
  mount()
  fireEvent.click(
    await screen.findByRole('button', { name: 'mcpTools.editUser' }),
  )
  fireEvent.click(await screen.findByRole('switch'))
  fireEvent.click(screen.getByRole('button', { name: 'mcpTools.save' }))
  await waitFor(() =>
    expect(api.update).toHaveBeenCalledWith(expect.anything(), 'a', 'u', null),
  )
  await waitFor(() =>
    expect(api.error).toHaveBeenCalledWith('mcpTools.saveFailed', {
      description: 'server validation error',
    }),
  )
})

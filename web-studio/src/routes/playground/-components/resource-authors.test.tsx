// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'

import { ResourceAuthors } from './resource-authors'

const fetchResourceAuthors = vi.hoisted(() => vi.fn())
vi.mock('#/routes/resources/-lib/api', () => ({ fetchResourceAuthors }))
vi.mock('#/hooks/use-app-connection', () => ({
  useAppConnection: () => ({ identityScopeKey: 'test' }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { user?: string }) =>
      options?.user ? `${key}:${options.user}` : key,
  }),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderAuthors(uri: string) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ResourceAuthors uri={uri} />
    </QueryClientProvider>,
  )
}

it('shows who uploaded the resource', async () => {
  fetchResourceAuthors.mockResolvedValue({
    uploadedBy: 'alice',
    updatedBy: 'alice',
  })

  renderAuthors('viking://resources/demo.md')

  const chip = await screen.findByText('alice')
  expect(chip.closest('[title]')?.getAttribute('title')).toBe(
    'uploadedBy:alice',
  )
  expect(screen.queryByTitle(/^updatedBy:/)).toBeNull()
  expect(fetchResourceAuthors).toHaveBeenCalledWith(
    'viking://resources/demo.md',
    expect.anything(),
  )
})

it('also shows who last updated the resource when it differs', async () => {
  fetchResourceAuthors.mockResolvedValue({
    uploadedBy: 'alice',
    updatedBy: 'bob',
  })

  renderAuthors('viking://resources/demo.md')

  expect(await screen.findByTitle('uploadedBy:alice')).toBeTruthy()
  expect((await screen.findByTitle('updatedBy:bob')).textContent).toBe('bob')
})

it('renders nothing when both are unknown', async () => {
  fetchResourceAuthors.mockResolvedValue({ uploadedBy: '', updatedBy: '' })

  const { container } = renderAuthors('viking://resources/old.md')

  await vi.waitFor(() => expect(fetchResourceAuthors).toHaveBeenCalled())
  expect(container.innerHTML).toBe('')
})

it('renders nothing when the attrs lookup fails', async () => {
  fetchResourceAuthors.mockRejectedValue(new Error('not found'))

  const { container } = renderAuthors('viking://')

  await vi.waitFor(() => expect(fetchResourceAuthors).toHaveBeenCalled())
  expect(container.innerHTML).toBe('')
})

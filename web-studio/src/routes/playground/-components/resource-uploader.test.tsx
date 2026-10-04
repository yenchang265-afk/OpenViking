// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'

import { ResourceUploader } from './resource-uploader'

const fetchResourceUploader = vi.hoisted(() => vi.fn())
vi.mock('#/routes/resources/-lib/api', () => ({ fetchResourceUploader }))
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

function renderUploader(uri: string) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ResourceUploader uri={uri} />
    </QueryClientProvider>,
  )
}

it('shows who uploaded the resource', async () => {
  fetchResourceUploader.mockResolvedValue('alice')

  renderUploader('viking://resources/demo.md')

  const chip = await screen.findByText('alice')
  expect(chip.closest('[title]')?.getAttribute('title')).toBe(
    'uploadedBy:alice',
  )
  expect(fetchResourceUploader).toHaveBeenCalledWith(
    'viking://resources/demo.md',
    expect.anything(),
  )
})

it('renders nothing when the uploader is unknown', async () => {
  fetchResourceUploader.mockResolvedValue('')

  const { container } = renderUploader('viking://resources/old.md')

  await vi.waitFor(() => expect(fetchResourceUploader).toHaveBeenCalled())
  expect(container.innerHTML).toBe('')
})

it('renders nothing when the attrs lookup fails', async () => {
  fetchResourceUploader.mockRejectedValue(new Error('not found'))

  const { container } = renderUploader('viking://')

  await vi.waitFor(() => expect(fetchResourceUploader).toHaveBeenCalled())
  expect(container.innerHTML).toBe('')
})

// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'

import { DeleteResource } from './delete-resource'

const removeResource = vi.hoisted(() => vi.fn())
vi.mock('#/routes/resources/-lib/api', () => ({ removeResource }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderDelete(
  entry: { isDir: boolean; uri: string },
  onDeleted = vi.fn(),
) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DeleteResource entry={entry} onDeleted={onDeleted} />
    </QueryClientProvider>,
  )
  return onDeleted
}

it('requires confirmation and does not delete on cancel', async () => {
  removeResource.mockResolvedValue(undefined)
  const entry = { isDir: false, uri: 'viking://resources/demo.md' }
  const onDeleted = renderDelete(entry)

  fireEvent.click(screen.getByRole('button', { name: 'deleteResource.label' }))
  expect(screen.getByText('deleteResource.fileDescription')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'deleteResource.cancel' }))
  expect(removeResource).not.toHaveBeenCalled()

  fireEvent.click(screen.getByRole('button', { name: 'deleteResource.label' }))
  fireEvent.click(
    screen.getByRole('button', { name: 'deleteResource.confirm' }),
  )
  await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(entry))
  expect(removeResource).toHaveBeenCalledExactlyOnceWith(entry.uri, {
    recursive: false,
  })
})

it('deletes directories recursively after warning about their contents', async () => {
  removeResource.mockResolvedValue(undefined)
  const entry = { isDir: true, uri: 'viking://resources/demo/' }
  const onDeleted = renderDelete(entry)

  fireEvent.click(screen.getByRole('button', { name: 'deleteResource.label' }))
  expect(screen.getByText('deleteResource.directoryDescription')).toBeTruthy()
  fireEvent.click(
    screen.getByRole('button', { name: 'deleteResource.confirm' }),
  )

  await waitFor(() => expect(onDeleted).toHaveBeenCalledOnce())
  expect(removeResource).toHaveBeenCalledExactlyOnceWith(entry.uri, {
    recursive: true,
  })
})

it('keeps the dialog open with the error when deletion fails', async () => {
  removeResource.mockRejectedValue({ message: 'Permission denied' })
  const onDeleted = renderDelete({
    isDir: false,
    uri: 'viking://resources/demo.md',
  })

  fireEvent.click(screen.getByRole('button', { name: 'deleteResource.label' }))
  fireEvent.click(
    screen.getByRole('button', { name: 'deleteResource.confirm' }),
  )

  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(onDeleted).not.toHaveBeenCalled()
  expect(
    screen.getByRole('button', { name: 'deleteResource.confirm' }),
  ).toBeTruthy()
})

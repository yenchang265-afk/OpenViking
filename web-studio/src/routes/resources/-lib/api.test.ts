import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchDirectorySidecarContent,
  fetchFsList,
  removeResource,
} from './api'

const { deleteFsMock, getContentReadMock, getFsLsMock } = vi.hoisted(() => ({
  deleteFsMock: vi.fn(),
  getContentReadMock: vi.fn(),
  getFsLsMock: vi.fn(),
}))

vi.mock('#/lib/ov-client', async (importOriginal) => {
  const original = await importOriginal()
  return {
    ...original,
    deleteFs: deleteFsMock,
    getContentRead: getContentReadMock,
    getFsLs: getFsLsMock,
  }
})

beforeEach(() => {
  deleteFsMock.mockReset()
  getContentReadMock.mockReset()
  getFsLsMock.mockReset()
  getFsLsMock.mockResolvedValue({
    data: { status: 'ok', result: [] },
    headers: {},
    status: 200,
  })
})

describe('fetchDirectorySidecarContent', () => {
  it.each(['abstract', 'overview'] as const)(
    'does not read a %s sidecar for the virtual root',
    async (level) => {
      await expect(
        fetchDirectorySidecarContent('viking://', level),
      ).resolves.toBe('')
      expect(getContentReadMock).not.toHaveBeenCalled()
    },
  )

  it('reads raw L0/L1 sidecars instead of the body-only semantic accessors', async () => {
    getContentReadMock.mockResolvedValue({
      data: {
        status: 'ok',
        result: '---\ndirectory: viking://resources/demo/\n---',
      },
      headers: {},
      status: 200,
    })

    await expect(
      fetchDirectorySidecarContent('viking://resources/demo/', 'abstract'),
    ).resolves.toContain('directory: viking://resources/demo/')
    expect(getContentReadMock).toHaveBeenCalledWith({
      query: {
        uri: 'viking://resources/demo/.abstract.md',
        offset: 0,
        limit: -1,
        raw: true,
      },
    })
  })
})

describe('fetchFsList', () => {
  it('requests newest entries before the server applies node_limit', async () => {
    await fetchFsList('viking://session', { nodeLimit: 200 })

    expect(getFsLsMock).toHaveBeenCalledWith({
      query: expect.objectContaining({
        node_limit: 200,
        sort_by: 'mtime',
        sort_order: 'desc',
      }),
    })
  })
})

describe('removeResource', () => {
  it('deletes directories recursively', async () => {
    deleteFsMock.mockResolvedValue({
      data: { status: 'ok', result: { uri: 'viking://resources/demo/' } },
      headers: {},
      status: 200,
    })

    await removeResource('viking://resources/demo/', { recursive: true })

    expect(deleteFsMock).toHaveBeenCalledWith({
      query: { uri: 'viking://resources/demo/', recursive: true },
    })
  })

  it('surfaces server errors as VikingApiError', async () => {
    deleteFsMock.mockRejectedValue({
      status: 'error',
      error: { code: 'PERMISSION_DENIED', message: 'Permission denied' },
    })

    await expect(
      removeResource('viking://resources/demo.md'),
    ).rejects.toMatchObject({ message: expect.any(String) })
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchDirectorySidecarContent,
  fetchFsList,
  fetchResourceAuthors,
  reindexResource,
  removeResource,
} from './api'

const {
  clientGetMock,
  deleteFsMock,
  getContentReadMock,
  getFsLsMock,
  postContentReindexMock,
} = vi.hoisted(() => ({
  clientGetMock: vi.fn(),
  deleteFsMock: vi.fn(),
  getContentReadMock: vi.fn(),
  getFsLsMock: vi.fn(),
  postContentReindexMock: vi.fn(),
}))

vi.mock('#/lib/ov-client', async (importOriginal) => {
  const original = await importOriginal()
  return {
    ...original,
    deleteFs: deleteFsMock,
    getContentRead: getContentReadMock,
    getFsLs: getFsLsMock,
    postContentReindex: postContentReindexMock,
    ovClient: { client: { get: clientGetMock } },
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

  it('requests entry authors and maps them onto entries', async () => {
    getFsLsMock.mockResolvedValue({
      data: {
        status: 'ok',
        result: [
          {
            uri: 'viking://resources/a.md',
            name: 'a.md',
            isDir: false,
            uploaded_by: 'alice',
            updated_by: 'bob',
          },
          {
            uri: 'viking://resources/b.md',
            name: 'b.md',
            isDir: false,
            uploaded_by: '',
            updated_by: '',
          },
        ],
      },
      headers: {},
      status: 200,
    })

    const result = await fetchFsList('viking://resources', {
      extraFields: ['authors'],
    })

    expect(getFsLsMock).toHaveBeenCalledWith({
      query: expect.objectContaining({ extra_fields: ['authors'] }),
    })
    expect(
      result.entries.map(({ name, uploadedBy, updatedBy }) => ({
        name,
        uploadedBy,
        updatedBy,
      })),
    ).toEqual([
      { name: 'a.md', uploadedBy: 'alice', updatedBy: 'bob' },
      { name: 'b.md', uploadedBy: '', updatedBy: '' },
    ])
  })

  it('omits extra_fields when none are requested', async () => {
    await fetchFsList('viking://resources')

    expect(getFsLsMock.mock.calls[0][0].query).not.toHaveProperty(
      'extra_fields',
    )
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

describe('fetchResourceAuthors', () => {
  it('reads the uploader and last updater from the resource attrs', async () => {
    clientGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        result: {
          uri: 'viking://resources/demo.md',
          attrs: { tags: [], uploaded_by: 'alice', updated_by: 'bob' },
        },
      },
      headers: {},
      status: 200,
    })

    await expect(
      fetchResourceAuthors('viking://resources/demo.md'),
    ).resolves.toEqual({ uploadedBy: 'alice', updatedBy: 'bob' })
    expect(clientGetMock).toHaveBeenCalledWith(
      expect.objectContaining({
        query: { uri: 'viking://resources/demo.md' },
        url: '/api/v1/fs/attrs',
      }),
    )
  })

  it('returns empty strings when the authors are unknown', async () => {
    clientGetMock.mockResolvedValue({
      data: { status: 'ok', result: { attrs: { tags: [] } } },
      headers: {},
      status: 200,
    })

    await expect(
      fetchResourceAuthors('viking://resources/legacy.md'),
    ).resolves.toEqual({ uploadedBy: '', updatedBy: '' })
  })
})

describe('reindexResource', () => {
  it('starts a background reindex and returns its task id', async () => {
    postContentReindexMock.mockResolvedValue({
      data: { status: 'ok', result: { task_id: 'task-1', status: 'accepted' } },
      headers: {},
      status: 200,
    })

    await expect(
      reindexResource('viking://resources/docs/', 'semantic_and_vectors'),
    ).resolves.toEqual({ taskId: 'task-1' })
    expect(postContentReindexMock).toHaveBeenCalledWith({
      body: {
        uri: 'viking://resources/docs/',
        mode: 'semantic_and_vectors',
        wait: false,
      },
    })
  })
})

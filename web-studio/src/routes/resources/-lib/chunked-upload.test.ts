import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OvClientError } from '#/lib/ov-client'
import {
  SessionsUnavailableError,
  UploadSessionError,
  resumeUploadSession,
  uploadSession,
} from './chunked-upload'
import type { UploadSource } from './chunked-upload'

const { postMock, putMock, getMock, deleteMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  putMock: vi.fn(),
  getMock: vi.fn(),
  deleteMock: vi.fn(),
}))

vi.mock('#/lib/ov-client', async (importOriginal) => {
  const original = await importOriginal()
  return {
    ...(original as object),
    ovClient: {
      client: {
        post: postMock,
        put: putMock,
        get: getMock,
        delete: deleteMock,
      },
    },
  }
})

const ok = (result: unknown) => ({
  data: { status: 'ok', result },
  headers: {},
  status: 200,
})

function source(path: string, text: string): UploadSource {
  return { path, file: new File([text], path.split('/').pop() ?? path) }
}

function mockCreateAndComplete(partSize = 4) {
  postMock.mockImplementation(({ url }: { url: string }) =>
    Promise.resolve(
      url === '/api/v1/uploads'
        ? ok({ upload_id: 'u1', part_size_bytes: partSize })
        : ok({ temp_file_id: 'session_u1' }),
    ),
  )
}

async function blobText(blob: Blob): Promise<string> {
  return await blob.text()
}

beforeEach(() => {
  postMock.mockReset()
  putMock.mockReset()
  getMock.mockReset()
  deleteMock.mockReset()
  putMock.mockResolvedValue(ok({}))
  deleteMock.mockResolvedValue(ok({}))
})

describe('uploadSession', () => {
  it('creates a session, slices each file into parts and completes', async () => {
    mockCreateAndComplete(4)
    const progress: number[] = []

    const id = await uploadSession({
      kind: 'directory',
      name: 'docs',
      sources: [source('a.md', '0123456789'), source('sub/b.txt', 'xyz')],
      onProgress: (sent) => progress.push(sent),
    })

    expect(id).toBe('session_u1')
    expect(postMock.mock.calls[0][0].body).toEqual({
      kind: 'directory',
      name: 'docs',
      files: [
        { path: 'a.md', size: 10 },
        { path: 'sub/b.txt', size: 3 },
      ],
    })
    const sent = await Promise.all(
      putMock.mock.calls.map(async ([request]) => [
        request.url,
        await blobText(request.body),
      ]),
    )
    expect(Object.fromEntries(sent)).toEqual({
      '/api/v1/uploads/u1/files/0/parts/1': '0123',
      '/api/v1/uploads/u1/files/0/parts/2': '4567',
      '/api/v1/uploads/u1/files/0/parts/3': '89',
      '/api/v1/uploads/u1/files/1/parts/1': 'xyz',
    })
    expect(putMock.mock.calls[0][0].bodySerializer).toBeNull()
    expect(progress.at(-1)).toBe(13)
    expect(postMock.mock.calls.at(-1)?.[0].url).toBe(
      '/api/v1/uploads/u1/complete',
    )
  })

  it('keeps at most `concurrency` parts in flight', async () => {
    mockCreateAndComplete(1)
    let inFlight = 0
    let peak = 0
    putMock.mockImplementation(async () => {
      inFlight += 1
      peak = Math.max(peak, inFlight)
      await new Promise((resolve) => setTimeout(resolve, 5))
      inFlight -= 1
      return ok({})
    })

    await uploadSession({
      kind: 'file',
      name: 'f.bin',
      sources: [source('f.bin', 'abcdefghij')],
      concurrency: 3,
    })

    expect(putMock).toHaveBeenCalledTimes(10)
    expect(peak).toBe(3)
  })

  it('retries a failed part', async () => {
    mockCreateAndComplete(4)
    putMock
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue(ok({}))

    await expect(
      uploadSession({
        kind: 'file',
        name: 'f.bin',
        sources: [source('f.bin', 'abc')],
        retryDelayMs: 0,
      }),
    ).resolves.toBe('session_u1')
    expect(putMock).toHaveBeenCalledTimes(2)
  })

  it('keeps the session for resume when a part keeps failing', async () => {
    mockCreateAndComplete(4)
    putMock.mockRejectedValue(new Error('network'))

    const error = await uploadSession({
      kind: 'file',
      name: 'f.bin',
      sources: [source('f.bin', 'abc')],
      maxRetries: 1,
      retryDelayMs: 0,
    }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(UploadSessionError)
    expect((error as UploadSessionError).uploadId).toBe('u1')
    expect(deleteMock).not.toHaveBeenCalled()
    expect(postMock).toHaveBeenCalledTimes(1)
  })

  it.each([404, 405, 409])(
    'reports sessions as unavailable on HTTP %i',
    async (statusCode) => {
      postMock.mockRejectedValue(
        new OvClientError({ code: 'X', message: 'no', statusCode }),
      )

      await expect(
        uploadSession({
          kind: 'file',
          name: 'f.bin',
          sources: [source('f.bin', 'abc')],
        }),
      ).rejects.toBeInstanceOf(SessionsUnavailableError)
    },
  )

  it('aborts the server session when the signal fires', async () => {
    mockCreateAndComplete(1)
    const controller = new AbortController()
    putMock.mockImplementation(async () => {
      controller.abort()
      return ok({})
    })

    await expect(
      uploadSession({
        kind: 'file',
        name: 'f.bin',
        sources: [source('f.bin', 'abc')],
        concurrency: 1,
        signal: controller.signal,
      }),
    ).rejects.toThrow()
    expect(deleteMock).toHaveBeenCalledWith({ url: '/api/v1/uploads/u1' })
  })
})

describe('resumeUploadSession', () => {
  it('sends only the parts the server is missing', async () => {
    getMock.mockResolvedValue(
      ok({
        part_size_bytes: 4,
        files: [{ index: 0, received_parts: [1, 3] }],
      }),
    )
    postMock.mockResolvedValue(ok({ temp_file_id: 'session_u1' }))
    const progress: number[] = []

    const id = await resumeUploadSession('u1', {
      kind: 'file',
      name: 'f.bin',
      sources: [source('f.bin', '0123456789')],
      onProgress: (sent) => progress.push(sent),
    })

    expect(id).toBe('session_u1')
    expect(putMock).toHaveBeenCalledTimes(1)
    expect(putMock.mock.calls[0][0].url).toBe(
      '/api/v1/uploads/u1/files/0/parts/2',
    )
    expect(await blobText(putMock.mock.calls[0][0].body)).toBe('4567')
    expect(progress).toEqual([6, 10])
  })
})

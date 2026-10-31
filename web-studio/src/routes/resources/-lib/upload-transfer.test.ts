import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  FolderTooLargeForZipError,
  ProxyRequestTooLargeError,
  transferUpload,
} from './upload-transfer'
import type * as ChunkedUpload from './chunked-upload'
import type { FolderGroup } from './folder-upload'
import type * as OvErrors from '#/lib/ov-client/errors'

const mocks = vi.hoisted(() => ({
  abortUploadSession: vi.fn(),
  uploadSession: vi.fn(),
  resumeUploadSession: vi.fn(),
  postResourcesTempUpload: vi.fn(),
}))

vi.mock('./chunked-upload', async (importOriginal) => {
  const original = await importOriginal()
  return {
    ...(original as object),
    abortUploadSession: mocks.abortUploadSession,
    uploadSession: mocks.uploadSession,
    resumeUploadSession: mocks.resumeUploadSession,
  }
})

vi.mock('#/lib/ov-client', async () => {
  const errors = await vi.importActual<typeof OvErrors>(
    '#/lib/ov-client/errors',
  )
  return {
    getOvResult: async (value: unknown) => value,
    isOvClientError: errors.isOvClientError,
    postResourcesTempUpload: mocks.postResourcesTempUpload,
  }
})

vi.mock('./upload-limits', () => ({ BROWSER_ZIP_MAX_BYTES: 8 }))

const { SessionsUnavailableError, UploadSessionError } =
  await vi.importActual<typeof ChunkedUpload>('./chunked-upload')
const { OvClientError } = await vi.importActual<typeof OvErrors>(
  '#/lib/ov-client/errors',
)

/** What a proxy's HTML 413 page normalizes to: no OpenViking error envelope. */
function proxy413() {
  return new OvClientError({
    code: 'HTTP_ERROR',
    message: '<html>413 Request Entity Too Large</html>',
    statusCode: 413,
  })
}

function folder(): FolderGroup {
  return {
    name: 'docs',
    skippedCount: 0,
    entries: [
      { path: 'docs/a.md', file: new File(['abc'], 'a.md') },
      { path: 'docs/sub/b.txt', file: new File(['de'], 'b.txt') },
    ],
  }
}

beforeEach(() => {
  mocks.abortUploadSession.mockReset()
  mocks.uploadSession.mockReset()
  mocks.resumeUploadSession.mockReset()
  mocks.postResourcesTempUpload.mockReset()
})

describe('transferUpload', () => {
  it('uploads a file through a session and reports percent progress', async () => {
    mocks.uploadSession.mockImplementation(async (options) => {
      options.onProgress(5, 10)
      return 'session_1'
    })
    const progress: number[] = []
    const file = new File(['0123456789'], 'report.pdf')

    const result = await transferUpload({ file }, (p) => progress.push(p))

    expect(result).toEqual({
      tempFileId: 'session_1',
      sourceName: 'report.pdf',
    })
    expect(mocks.uploadSession.mock.calls[0][0]).toMatchObject({
      kind: 'file',
      name: 'report.pdf',
      sources: [{ path: 'report.pdf', file }],
    })
    expect(progress).toEqual([50])
  })

  it('sends a folder as a directory session with paths relative to it', async () => {
    mocks.uploadSession.mockResolvedValue('session_2')

    const result = await transferUpload({
      file: new File([], 'docs'),
      folder: folder(),
    })

    expect(result).toEqual({ tempFileId: 'session_2', sourceName: 'docs' })
    const options = mocks.uploadSession.mock.calls[0][0]
    expect(options.kind).toBe('directory')
    expect(options.name).toBe('docs')
    expect(options.sources.map((s: { path: string }) => s.path)).toEqual([
      'a.md',
      'sub/b.txt',
    ])
  })

  it('resumes a session once when parts keep failing', async () => {
    mocks.uploadSession.mockRejectedValue(
      new UploadSessionError('u9', new Error('network')),
    )
    mocks.resumeUploadSession.mockResolvedValue('session_u9')

    const result = await transferUpload({ file: new File(['x'], 'f.bin') })

    expect(result.tempFileId).toBe('session_u9')
    expect(mocks.resumeUploadSession.mock.calls[0][0]).toBe('u9')
    expect(mocks.abortUploadSession).not.toHaveBeenCalled()
  })

  it('discards the session when the resumed upload fails too', async () => {
    const client = {} as never
    const resumeError = new Error('still offline')
    mocks.uploadSession.mockRejectedValue(
      new UploadSessionError('u9', new Error('network')),
    )
    mocks.resumeUploadSession.mockRejectedValue(resumeError)

    await expect(
      transferUpload({ file: new File(['x'], 'f.bin') }, undefined, { client }),
    ).rejects.toBe(resumeError)
    expect(mocks.abortUploadSession).toHaveBeenCalledExactlyOnceWith(
      'u9',
      client,
    )
  })

  it('leaves the discard to the cancelled upload itself', async () => {
    const controller = new AbortController()
    mocks.uploadSession.mockRejectedValue(
      new UploadSessionError('u9', new Error('network')),
    )
    mocks.resumeUploadSession.mockImplementation(async () => {
      controller.abort()
      throw new DOMException('Aborted', 'AbortError')
    })

    await expect(
      transferUpload({ file: new File(['x'], 'f.bin') }, undefined, {
        signal: controller.signal,
      }),
    ).rejects.toThrow('Aborted')
    expect(mocks.abortUploadSession).not.toHaveBeenCalled()
  })

  it('explains a proxy 413 on a part instead of resuming', async () => {
    mocks.uploadSession.mockRejectedValue(
      new UploadSessionError('u9', proxy413()),
    )

    const error = await transferUpload({
      file: new File(['x'], 'f.bin'),
    }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ProxyRequestTooLargeError)
    expect((error as Error).message).not.toContain('<html>')
    expect(mocks.resumeUploadSession).not.toHaveBeenCalled()
    expect(mocks.abortUploadSession).toHaveBeenCalledOnce()
  })

  it('explains a proxy 413 on the single-request upload', async () => {
    mocks.uploadSession.mockRejectedValue(new SessionsUnavailableError())
    mocks.postResourcesTempUpload.mockRejectedValue(proxy413())

    await expect(
      transferUpload({ file: new File(['x'], 'f.md') }),
    ).rejects.toBeInstanceOf(ProxyRequestTooLargeError)
  })

  it("passes the server's own 413 through unchanged", async () => {
    const serverError = new OvClientError({
      code: 'RESOURCE_EXHAUSTED',
      message: "'f.md' exceeds size limit (10 bytes).",
      statusCode: 413,
    })
    mocks.uploadSession.mockRejectedValue(serverError)

    await expect(
      transferUpload({ file: new File(['x'], 'f.md') }),
    ).rejects.toBe(serverError)
  })

  it('falls back to the single-request upload for a file', async () => {
    mocks.uploadSession.mockRejectedValue(new SessionsUnavailableError())
    mocks.postResourcesTempUpload.mockResolvedValue({
      temp_file_id: 'upload_1',
    })
    const file = new File(['abc'], 'f.md')

    const result = await transferUpload({ file })

    expect(result).toEqual({ tempFileId: 'upload_1', sourceName: 'f.md' })
    expect(mocks.postResourcesTempUpload.mock.calls[0][0].body.file).toBe(file)
  })

  it('zips a folder for the fallback upload', async () => {
    mocks.uploadSession.mockRejectedValue(new SessionsUnavailableError())
    mocks.postResourcesTempUpload.mockResolvedValue({
      temp_file_id: 'upload_2',
    })

    const result = await transferUpload({
      file: new File([], 'docs'),
      folder: folder(),
    })

    expect(result).toEqual({ tempFileId: 'upload_2', sourceName: 'docs.zip' })
    expect(mocks.postResourcesTempUpload.mock.calls[0][0].body.file.name).toBe(
      'docs.zip',
    )
  })

  it('refuses to zip a folder above the in-browser limit', async () => {
    mocks.uploadSession.mockRejectedValue(new SessionsUnavailableError())
    const big: FolderGroup = {
      ...folder(),
      entries: [
        { path: 'docs/big.bin', file: new File(['123456789'], 'big.bin') },
      ],
    }

    await expect(
      transferUpload({ file: new File([], 'docs'), folder: big }),
    ).rejects.toBeInstanceOf(FolderTooLargeForZipError)
    expect(mocks.postResourcesTempUpload).not.toHaveBeenCalled()
  })
})

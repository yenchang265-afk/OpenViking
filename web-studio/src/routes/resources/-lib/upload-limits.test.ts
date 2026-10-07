import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BROWSER_ZIP_MAX_BYTES,
  LEGACY_UPLOAD_LIMITS,
  fetchUploadLimits,
  folderUploadLimitBytes,
} from './upload-limits'

const MIB = 1024 * 1024

const { clientGetMock } = vi.hoisted(() => ({ clientGetMock: vi.fn() }))

vi.mock('#/lib/ov-client', async (importOriginal) => {
  const original = await importOriginal()
  return {
    ...(original as object),
    ovClient: { client: { get: clientGetMock } },
  }
})

beforeEach(() => {
  clientGetMock.mockReset()
})

describe('fetchUploadLimits', () => {
  it('maps the server limits to camelCase', async () => {
    clientGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        result: {
          max_file_bytes: 2048 * MIB,
          max_session_bytes: 5120 * MIB,
          max_files: 10_000,
          part_size_bytes: 8 * MIB,
        },
      },
      headers: {},
      status: 200,
    })

    await expect(fetchUploadLimits()).resolves.toEqual({
      maxFileBytes: 2048 * MIB,
      maxSessionBytes: 5120 * MIB,
      maxFiles: 10_000,
      partSizeBytes: 8 * MIB,
    })
    expect(clientGetMock).toHaveBeenCalledWith({
      url: '/api/v1/uploads/limits',
    })
  })

  it('falls back to the legacy server limit when the endpoint is unavailable', async () => {
    clientGetMock.mockRejectedValue(new Error('Request failed with status 404'))

    await expect(fetchUploadLimits()).resolves.toEqual(LEGACY_UPLOAD_LIMITS)
  })
})

describe('folderUploadLimitBytes', () => {
  it('caps in-browser folder zips below the server file limit', () => {
    expect(
      folderUploadLimitBytes({
        ...LEGACY_UPLOAD_LIMITS,
        maxFileBytes: 4096 * MIB,
      }),
    ).toBe(BROWSER_ZIP_MAX_BYTES)
    expect(
      folderUploadLimitBytes({
        ...LEGACY_UPLOAD_LIMITS,
        maxFileBytes: 64 * MIB,
      }),
    ).toBe(64 * MIB)
  })
})

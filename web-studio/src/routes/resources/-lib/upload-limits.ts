import { getOvResult, ovClient } from '#/lib/ov-client'

const MIB = 1024 * 1024

export interface UploadLimits {
  maxFileBytes: number
  maxSessionBytes: number
  maxFiles: number
  partSizeBytes: number
}

interface UploadLimitsResult {
  max_file_bytes: number
  max_session_bytes: number
  max_files: number
  part_size_bytes: number
}

/** Limits of servers that predate GET /api/v1/uploads/limits (their 512 MiB upload cap). */
export const LEGACY_UPLOAD_LIMITS: UploadLimits = {
  maxFileBytes: 512 * MIB,
  maxSessionBytes: 512 * MIB,
  maxFiles: 10_000,
  partSizeBytes: 8 * MIB,
}

/**
 * Largest folder zipped in browser memory, which only happens for servers without
 * chunked uploads.
 */
export const BROWSER_ZIP_MAX_BYTES = 512 * MIB

/** Fetch the server's upload limits, falling back to the legacy cap for older servers. */
export async function fetchUploadLimits(): Promise<UploadLimits> {
  try {
    const result = await getOvResult<UploadLimitsResult>(
      ovClient.client.get({ url: '/api/v1/uploads/limits' }),
    )
    return {
      maxFileBytes: result.max_file_bytes,
      maxSessionBytes: result.max_session_bytes,
      maxFiles: result.max_files,
      partSizeBytes: result.part_size_bytes,
    }
  } catch {
    return LEGACY_UPLOAD_LIMITS
  }
}

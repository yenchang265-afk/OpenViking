import { getOvResult, isOvClientError, ovClient } from '#/lib/ov-client'

/** One file of an upload: its path inside the upload and the browser File. */
export interface UploadSource {
  path: string
  file: File
}

export interface ChunkedUploadOptions {
  kind: 'file' | 'directory'
  name: string
  sources: UploadSource[]
  /** Parts sent in parallel (default 3). */
  concurrency?: number
  /** Extra attempts per part after a failure (default 3). */
  maxRetries?: number
  /** Base backoff delay in ms, doubled per attempt (default 500). */
  retryDelayMs?: number
  onProgress?: (sentBytes: number, totalBytes: number) => void
  signal?: AbortSignal
}

/** The server has no chunked uploads (older server) or refuses them (shared mode). */
export class SessionsUnavailableError extends Error {
  constructor() {
    super('Chunked uploads are not available on this server')
    this.name = 'SessionsUnavailableError'
  }
}

/** Parts still failed after retries; the session is kept so it can be resumed. */
export class UploadSessionError extends Error {
  readonly uploadId: string

  constructor(uploadId: string, cause: unknown) {
    super(cause instanceof Error ? cause.message : 'Upload failed', { cause })
    this.name = 'UploadSessionError'
    this.uploadId = uploadId
  }
}

interface CreatedSession {
  upload_id: string
  part_size_bytes: number
}

interface SessionStatus {
  part_size_bytes: number
  files: { index: number; received_parts: number[] }[]
}

interface PartPlan {
  index: number
  number: number
  start: number
  end: number
}

const UNAVAILABLE_STATUSES = new Set([404, 405, 409])
const JSON_HEADERS = { 'Content-Type': 'application/json' }

function planParts(sources: UploadSource[], partSize: number): PartPlan[] {
  return sources.flatMap((source, index) =>
    Array.from({ length: Math.ceil(source.file.size / partSize) }, (_, i) => ({
      index,
      number: i + 1,
      start: i * partSize,
      end: Math.min((i + 1) * partSize, source.file.size),
    })),
  )
}

const partKey = (index: number, number: number) => `${index}:${number}`

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function sendPart(
  uploadId: string,
  part: PartPlan,
  source: UploadSource,
  options: ChunkedUploadOptions,
): Promise<void> {
  const maxRetries = options.maxRetries ?? 3
  const baseDelay = options.retryDelayMs ?? 500
  for (let attempt = 0; ; attempt += 1) {
    options.signal?.throwIfAborted()
    try {
      await getOvResult(
        ovClient.client.put({
          url: `/api/v1/uploads/${uploadId}/files/${part.index}/parts/${part.number}`,
          body: source.file.slice(part.start, part.end),
          bodySerializer: null,
          headers: { 'Content-Type': 'application/octet-stream' },
        }),
      )
      return
    } catch (error) {
      if (attempt >= maxRetries || options.signal?.aborted) throw error
      await sleep(baseDelay * 2 ** attempt)
    }
  }
}

async function sendMissingParts(
  uploadId: string,
  partSize: number,
  received: Set<string>,
  options: ChunkedUploadOptions,
): Promise<void> {
  const parts = planParts(options.sources, partSize)
  const total = options.sources.reduce((sum, s) => sum + s.file.size, 0)
  let sent = parts
    .filter((p) => received.has(partKey(p.index, p.number)))
    .reduce((sum, p) => sum + (p.end - p.start), 0)
  options.onProgress?.(sent, total)

  const queue = parts.filter((p) => !received.has(partKey(p.index, p.number)))
  const worker = async () => {
    for (let part = queue.shift(); part; part = queue.shift()) {
      await sendPart(uploadId, part, options.sources[part.index], options)
      sent += part.end - part.start
      options.onProgress?.(sent, total)
    }
  }
  const workers = Math.max(1, options.concurrency ?? 3)
  await Promise.all(Array.from({ length: workers }, worker))
}

async function finish(
  uploadId: string,
  partSize: number,
  received: Set<string>,
  options: ChunkedUploadOptions,
): Promise<string> {
  try {
    await sendMissingParts(uploadId, partSize, received, options)
    const done = await getOvResult<{ temp_file_id: string }>(
      ovClient.client.post({ url: `/api/v1/uploads/${uploadId}/complete` }),
    )
    return done.temp_file_id
  } catch (error) {
    if (options.signal?.aborted) {
      await abortUploadSession(uploadId)
      throw error
    }
    throw new UploadSessionError(uploadId, error)
  }
}

/**
 * Upload a file or folder as a chunked session and return its temp_file_id.
 *
 * Throws SessionsUnavailableError when the caller should fall back to the
 * single-request upload, and UploadSessionError (with the uploadId) when parts
 * still fail after retries so the upload can be resumed.
 */
export async function uploadSession(
  options: ChunkedUploadOptions,
): Promise<string> {
  let created: CreatedSession
  try {
    created = await getOvResult<CreatedSession>(
      ovClient.client.post({
        url: '/api/v1/uploads',
        headers: JSON_HEADERS,
        body: {
          kind: options.kind,
          name: options.name,
          files: options.sources.map((s) => ({
            path: s.path,
            size: s.file.size,
          })),
        },
      }),
    )
  } catch (error) {
    if (
      isOvClientError(error) &&
      error.statusCode !== undefined &&
      UNAVAILABLE_STATUSES.has(error.statusCode)
    ) {
      throw new SessionsUnavailableError()
    }
    throw error
  }
  return finish(created.upload_id, created.part_size_bytes, new Set(), options)
}

/** Resume an interrupted session: send only the parts the server is missing, then complete. */
export async function resumeUploadSession(
  uploadId: string,
  options: ChunkedUploadOptions,
): Promise<string> {
  const status = await getOvResult<SessionStatus>(
    ovClient.client.get({ url: `/api/v1/uploads/${uploadId}` }),
  )
  const received = new Set(
    status.files.flatMap((f) =>
      f.received_parts.map((n) => partKey(f.index, n)),
    ),
  )
  return finish(uploadId, status.part_size_bytes, received, options)
}

/** Discard a session on the server (best effort). */
export async function abortUploadSession(uploadId: string): Promise<void> {
  try {
    await getOvResult(
      ovClient.client.delete({ url: `/api/v1/uploads/${uploadId}` }),
    )
  } catch {
    // The server sweeps abandoned sessions after temp_upload.ttl_seconds.
  }
}

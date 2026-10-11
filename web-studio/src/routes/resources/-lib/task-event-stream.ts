import { ovClient } from '#/lib/ov-client'
import { fetchSse, SseResponseError } from '#/lib/sse'
import type { FetchSseOptions, SseMessage } from '#/lib/sse'
import type { TaskRecord } from '@ov-server/api/v1/tasks'

export type TaskStreamEvent =
  | { type: 'ready'; complete: boolean }
  | { type: 'task'; record: TaskRecord }
  | { type: 'resync' }

type OpenStream = (
  url: string,
  options: FetchSseOptions & { headers: Record<string, string> },
) => AsyncIterable<SseMessage>

export type WatchTaskEventsOptions = {
  taskType: string
  onEvent: (event: TaskStreamEvent) => void
  /** True only while every task change is being pushed to this client. */
  onLiveChange: (live: boolean) => void
  open?: OpenStream
  retryDelaysMs?: number[]
  /** Reconnect when no frame (pings included) arrives for this long. */
  idleTimeoutMs?: number
}

const DEFAULT_RETRY_DELAYS_MS = [1_000, 2_000, 5_000, 10_000, 30_000]
// Three missed server pings (sent every 15s): the connection is dead.
const DEFAULT_IDLE_TIMEOUT_MS = 45_000
// Only a connection that stayed up this long resets the retry backoff, so a
// server that accepts and drops at once is not hammered every second.
const STABLE_CONNECTION_MS = 30_000

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export function parseTaskStreamMessage(
  message: SseMessage,
): TaskStreamEvent | null {
  if (message.event === 'resync') {
    return { type: 'resync' }
  }
  let data: unknown
  try {
    data = JSON.parse(message.data)
  } catch {
    return null
  }
  if (message.event === 'ready' && isRecord(data)) {
    return { type: 'ready', complete: data.complete === true }
  }
  if (
    message.event === 'task' &&
    isRecord(data) &&
    typeof data.task_id === 'string' &&
    typeof data.task_type === 'string' &&
    typeof data.status === 'string'
  ) {
    return { type: 'task', record: data as TaskRecord }
  }
  return null
}

function buildStreamHeaders(): Record<string, string> {
  const conn = ovClient.getConnection()
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  const apiKey = conn.apiKey || conn.adminApiKey
  if (apiKey) headers['X-API-Key'] = apiKey
  if (conn.identityHeaders) {
    if (conn.accountId) headers['X-OpenViking-Account'] = conn.accountId
    if (conn.userId) headers['X-OpenViking-User'] = conn.userId
  }
  return headers
}

/** A server that predates the stream answers with JSON or 404/405. */
function isStreamUnsupported(error: unknown): boolean {
  return (
    error instanceof SseResponseError &&
    (error.response.ok || [404, 405].includes(error.response.status))
  )
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const onAbort = () => {
      clearTimeout(timer)
      resolve()
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

/**
 * Follow task changes pushed by GET /api/v1/tasks/events, reconnecting with
 * backoff. Returns a function that closes the stream.
 */
export function watchTaskEvents({
  taskType,
  onEvent,
  onLiveChange,
  open = fetchSse,
  retryDelaysMs = DEFAULT_RETRY_DELAYS_MS,
  idleTimeoutMs = DEFAULT_IDLE_TIMEOUT_MS,
}: WatchTaskEventsOptions): () => void {
  const controller = new AbortController()
  const { signal } = controller
  // A function read, since the signal flips while the loop awaits.
  const stopped = (): boolean => signal.aborted
  const query = new URLSearchParams({ task_type: taskType })
  let live = false

  const setLive = (value: boolean) => {
    live = value
    onLiveChange(value)
  }

  /** One connection; resolves when it ends, rejects on request failure. */
  const connect = async () => {
    const connection = new AbortController()
    const close = () => connection.abort()
    signal.addEventListener('abort', close, { once: true })
    let idleTimer = setTimeout(close, idleTimeoutMs)
    try {
      const url = `${ovClient.getOptions().baseUrl}/api/v1/tasks/events?${query}`
      for await (const message of open(url, {
        headers: buildStreamHeaders(),
        signal: connection.signal,
      })) {
        clearTimeout(idleTimer)
        idleTimer = setTimeout(close, idleTimeoutMs)
        const event = parseTaskStreamMessage(message)
        if (!event) continue
        if (event.type === 'ready') setLive(event.complete)
        onEvent(event)
      }
    } finally {
      clearTimeout(idleTimer)
      signal.removeEventListener('abort', close)
    }
  }

  const run = async () => {
    let attempt = 0
    while (!stopped()) {
      const startedAt = Date.now()
      try {
        await connect()
      } catch (error) {
        if (stopped()) return
        if (isStreamUnsupported(error)) {
          setLive(false)
          return
        }
      }
      if (stopped()) return
      if (live) setLive(false)
      if (Date.now() - startedAt >= STABLE_CONNECTION_MS) attempt = 0
      const delays = retryDelaysMs.length ? retryDelaysMs : [0]
      await sleep(delays[Math.min(attempt, delays.length - 1)], signal)
      attempt += 1
    }
  }

  void run()
  return () => controller.abort()
}

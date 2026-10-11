import { afterEach, describe, expect, it, vi } from 'vitest'

import { SseResponseError } from '#/lib/sse'
import type { SseMessage } from '#/lib/sse'
import { parseTaskStreamMessage, watchTaskEvents } from './task-event-stream'
import type { TaskStreamEvent } from './task-event-stream'

vi.mock('#/lib/ov-client', () => ({
  ovClient: {
    getConnection: () => ({
      accountId: 'acme',
      adminApiKey: '',
      apiKey: 'user-key',
      identityHeaders: true,
      userId: 'alice',
    }),
    getOptions: () => ({ baseUrl: 'http://ov' }),
  },
}))

function message(event: string, data: unknown): SseMessage {
  return { data: JSON.stringify(data), event, id: '' }
}

async function* frames(...messages: SseMessage[]): AsyncGenerator<SseMessage> {
  for (const item of messages) yield item
}

afterEach(() => {
  vi.useRealTimers()
})

describe('parseTaskStreamMessage', () => {
  it('parses ready, task and resync frames', () => {
    expect(
      parseTaskStreamMessage(message('ready', { complete: false })),
    ).toEqual({ type: 'ready', complete: false })
    expect(
      parseTaskStreamMessage(
        message('task', { status: 'running', task_id: 't1', task_type: 'x' }),
      ),
    ).toEqual({
      type: 'task',
      record: { status: 'running', task_id: 't1', task_type: 'x' },
    })
    expect(parseTaskStreamMessage(message('resync', {}))).toEqual({
      type: 'resync',
    })
  })

  it('ignores unknown, malformed and incomplete frames', () => {
    expect(parseTaskStreamMessage(message('other', {}))).toBeNull()
    expect(parseTaskStreamMessage(message('ping', {}))).toBeNull()
    expect(
      parseTaskStreamMessage({ data: '{', event: 'task', id: '' }),
    ).toBeNull()
    expect(
      parseTaskStreamMessage(message('task', { task_id: 't1' })),
    ).toBeNull()
  })
})

describe('watchTaskEvents', () => {
  it('subscribes with the connection identity and reports live state', async () => {
    const open = vi.fn(() =>
      frames(
        message('ready', { complete: true }),
        message('task', { status: 'completed', task_id: 't1', task_type: 'x' }),
      ),
    )
    const events: TaskStreamEvent[] = []
    const onLiveChange = vi.fn()

    const stop = watchTaskEvents({
      onEvent: (event) => events.push(event),
      onLiveChange,
      open,
      retryDelaysMs: [60_000],
      taskType: 'add_resource',
    })

    await vi.waitFor(() => expect(events).toHaveLength(2))
    stop()

    const [url, init] = open.mock.calls[0] as unknown as [
      string,
      { headers: Record<string, string> },
    ]
    expect(url).toBe('http://ov/api/v1/tasks/events?task_type=add_resource')
    expect(init.headers).toMatchObject({
      Accept: 'text/event-stream',
      'X-API-Key': 'user-key',
      'X-OpenViking-Account': 'acme',
      'X-OpenViking-User': 'alice',
    })
    expect(onLiveChange.mock.calls).toEqual([[true], [false]])
  })

  it('stays not live when the server pushes only its own worker changes', async () => {
    const onLiveChange = vi.fn()
    const stop = watchTaskEvents({
      onEvent: vi.fn(),
      onLiveChange,
      open: () => frames(message('ready', { complete: false })),
      retryDelaysMs: [60_000],
      taskType: 'add_resource',
    })

    await vi.waitFor(() => expect(onLiveChange).toHaveBeenCalled())
    stop()

    expect(onLiveChange).not.toHaveBeenCalledWith(true)
  })

  it('reconnects after the stream drops', async () => {
    const open = vi
      .fn()
      .mockImplementationOnce(() =>
        frames(message('ready', { complete: true })),
      )
      .mockImplementation(() => frames(message('resync', {})))
    const events: TaskStreamEvent[] = []

    const stop = watchTaskEvents({
      onEvent: (event) => events.push(event),
      onLiveChange: vi.fn(),
      open,
      retryDelaysMs: [0],
      taskType: 'add_resource',
    })

    await vi.waitFor(() =>
      expect(events.some((event) => event.type === 'resync')).toBe(true),
    )
    stop()
    expect(open.mock.calls.length).toBeGreaterThan(1)
  })

  it('reconnects when the server goes silent past the idle timeout', async () => {
    const open = vi.fn((_url: string, { signal }: { signal?: AbortSignal }) =>
      (async function* () {
        yield message('ready', { complete: true })
        // Never sends another frame; only the watchdog can end this.
        await new Promise((resolve) =>
          signal?.addEventListener('abort', resolve, { once: true }),
        )
        throw new DOMException('aborted', 'AbortError')
      })(),
    )
    const onLiveChange = vi.fn()

    const stop = watchTaskEvents({
      idleTimeoutMs: 20,
      onEvent: vi.fn(),
      onLiveChange,
      open,
      retryDelaysMs: [0],
      taskType: 'add_resource',
    })

    await vi.waitFor(() => expect(open.mock.calls.length).toBeGreaterThan(1))
    stop()
    expect(onLiveChange).toHaveBeenCalledWith(false)
  })

  it('gives up on a server without the event stream', async () => {
    const open = vi.fn(() => {
      throw new SseResponseError(new Response('', { status: 404 }), '')
    })
    const onLiveChange = vi.fn()

    const stop = watchTaskEvents({
      onEvent: vi.fn(),
      onLiveChange,
      open,
      retryDelaysMs: [0],
      taskType: 'add_resource',
    })

    await vi.waitFor(() => expect(onLiveChange).toHaveBeenCalledWith(false))
    await new Promise((resolve) => setTimeout(resolve, 20))
    stop()
    expect(open).toHaveBeenCalledOnce()
  })
})

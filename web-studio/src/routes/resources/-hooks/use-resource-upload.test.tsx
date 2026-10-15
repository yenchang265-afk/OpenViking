// @vitest-environment jsdom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import i18n from '#/i18n'
import type * as OvClientModule from '#/lib/ov-client'
import type { WatchTaskEventsOptions } from '../-lib/task-event-stream'
import {
  ResourceUploadProvider,
  useResourceUpload,
} from './use-resource-upload'

const apiMocks = vi.hoisted(() => ({
  getTasks: vi.fn(),
  postResources: vi.fn(),
  transferUpload: vi.fn(),
}))

const streamMocks = vi.hoisted(() => ({
  options: undefined as WatchTaskEventsOptions | undefined,
}))

vi.mock('../-lib/task-event-stream', () => ({
  watchTaskEvents: (options: WatchTaskEventsOptions) => {
    streamMocks.options = options
    return () => undefined
  },
}))

vi.mock('../-lib/upload-transfer', () => ({
  transferUpload: apiMocks.transferUpload,
}))

vi.mock('#/lib/ov-client', async (importOriginal) => ({
  ...(await importOriginal<typeof OvClientModule>()),
  getOvResult: async (value: unknown) => value,
  getTasks: apiMocks.getTasks,
  isOvClientError: () => false,
  postResources: apiMocks.postResources,
  postResourcesTempUpload: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  streamMocks.options = undefined
})

it('does not load upload tasks when the workbench only supports reads', async () => {
  render(
    <ResourceUploadProvider enabled={false}>
      <span data-testid="read-only" />
    </ResourceUploadProvider>,
  )
  await screen.findByTestId('read-only')
  expect(apiMocks.getTasks).not.toHaveBeenCalled()
})

function UploadHarness({
  onAccepted,
  onCompleted,
  onFailed,
}: {
  onAccepted: (result: {
    rootUri: string | null
    taskId: string | null
  }) => void
  onCompleted: () => void
  onFailed?: () => void
}) {
  const { refreshTasks, startRemote, tasks } = useResourceUpload()

  return (
    <>
      <button
        type="button"
        data-testid="start"
        onClick={() =>
          startRemote({
            commonBody: { watch_interval: 60 },
            onAccepted,
            onCompleted,
            onFailed,
            url: 'https://github.com/volcengine/OpenViking',
          })
        }
      />
      <button
        type="button"
        data-testid="refresh"
        onClick={() => void refreshTasks()}
      />
      <output data-testid="task-error">{tasks[0]?.errorMessage}</output>
      <output data-testid="task-count">{tasks.length}</output>
    </>
  )
}

describe('ResourceUploadProvider remote completion', () => {
  it.each(['resolve', 'reject'] as const)(
    'stops remote notifications after unmount when the request later %ss',
    async (outcome) => {
      let resolveImport!: (result: { status: string; root_uri: string }) => void
      let rejectImport!: (error: Error) => void
      apiMocks.getTasks.mockResolvedValue([])
      apiMocks.postResources.mockImplementation(
        () =>
          new Promise((resolve, reject) => {
            resolveImport = resolve
            rejectImport = reject
          }),
      )
      const onAccepted = vi.fn()
      const onCompleted = vi.fn()
      const onFailed = vi.fn()
      const { unmount } = render(
        <ResourceUploadProvider>
          <UploadHarness
            onAccepted={onAccepted}
            onCompleted={onCompleted}
            onFailed={onFailed}
          />
        </ResourceUploadProvider>,
      )

      fireEvent.click(screen.getByTestId('start'))
      await waitFor(() => expect(apiMocks.postResources).toHaveBeenCalledOnce())
      const signal = apiMocks.postResources.mock.calls[0][0]
        .signal as AbortSignal
      expect(signal.aborted).toBe(false)
      unmount()
      expect(signal.aborted).toBe(true)

      await act(async () => {
        if (outcome === 'resolve') {
          resolveImport({
            status: 'success',
            root_uri: 'viking://resources/OpenViking',
          })
        } else {
          rejectImport(new Error('Late import failure'))
        }
      })

      expect(onAccepted).not.toHaveBeenCalled()
      expect(onCompleted).not.toHaveBeenCalled()
      expect(onFailed).not.toHaveBeenCalled()
      expect(toast.success).not.toHaveBeenCalled()
      expect(toast.error).not.toHaveBeenCalled()
      expect(apiMocks.getTasks).toHaveBeenCalledOnce()
    },
  )

  it('notifies after submission and again after the background task completes', async () => {
    let taskStatus = 'processing'
    apiMocks.getTasks.mockImplementation(() => [
      {
        created_at: 1,
        result: { root_uri: 'viking://resources/OpenViking' },
        status: taskStatus,
        task_id: 'resource-task',
        task_type: 'add_resource',
        updated_at: 1,
      },
    ])
    apiMocks.postResources.mockResolvedValue({
      root_uri: 'viking://resources/OpenViking',
      status: 'success',
      task_id: 'resource-task',
    })
    const onAccepted = vi.fn()
    const onCompleted = vi.fn()

    render(
      <ResourceUploadProvider>
        <UploadHarness onAccepted={onAccepted} onCompleted={onCompleted} />
      </ResourceUploadProvider>,
    )

    fireEvent.click(screen.getByTestId('start'))
    await waitFor(() => expect(apiMocks.postResources).toHaveBeenCalledOnce())
    await waitFor(() =>
      expect(apiMocks.getTasks.mock.calls.length).toBeGreaterThan(1),
    )
    expect(onAccepted).toHaveBeenCalledWith({
      rootUri: 'viking://resources/OpenViking',
      taskId: 'resource-task',
    })
    expect(onCompleted).not.toHaveBeenCalled()

    taskStatus = 'completed'
    fireEvent.click(screen.getByTestId('refresh'))

    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce())
  })

  it('notifies when the background task fails', async () => {
    apiMocks.getTasks.mockResolvedValue([
      {
        created_at: 1,
        error: 'Processing failed',
        status: 'failed',
        task_id: 'resource-task',
        task_type: 'add_resource',
        updated_at: 2,
      },
    ])
    apiMocks.postResources.mockResolvedValue({
      root_uri: 'viking://resources/OpenViking',
      status: 'success',
      task_id: 'resource-task',
    })
    const onFailed = vi.fn()

    render(
      <ResourceUploadProvider>
        <UploadHarness
          onAccepted={vi.fn()}
          onCompleted={vi.fn()}
          onFailed={onFailed}
        />
      </ResourceUploadProvider>,
    )

    fireEvent.click(screen.getByTestId('start'))

    await waitFor(() => expect(onFailed).toHaveBeenCalledOnce())
  })

  it('updates an empty server error fallback when the language changes', async () => {
    const previousLanguage = i18n.language
    try {
      await i18n.changeLanguage('en')
      apiMocks.getTasks.mockResolvedValue([
        {
          created_at: 1,
          status: 'failed',
          task_id: 'resource-task',
          task_type: 'add_resource',
          updated_at: 2,
        },
      ])

      render(
        <ResourceUploadProvider>
          <UploadHarness onAccepted={vi.fn()} onCompleted={vi.fn()} />
        </ResourceUploadProvider>,
      )

      await waitFor(() =>
        expect(screen.getByTestId('task-error').textContent).toBe(
          'Processing failed',
        ),
      )

      await i18n.changeLanguage('zh-TW')

      await waitFor(() =>
        expect(screen.getByTestId('task-error').textContent).toBe('處理失敗'),
      )
    } finally {
      await i18n.changeLanguage(previousLanguage)
    }
  })
})

describe('ResourceUploadProvider pushed task changes', () => {
  const runningRecord = {
    created_at: 1,
    status: 'running',
    task_id: 'resource-task',
    task_type: 'add_resource',
    updated_at: 2,
  }

  function goLive() {
    act(() => {
      streamMocks.options?.onLiveChange(true)
      streamMocks.options?.onEvent({ type: 'ready', complete: true })
    })
  }

  it('completes from a pushed change while the stream is live', async () => {
    apiMocks.getTasks.mockResolvedValue([])
    apiMocks.postResources.mockResolvedValue({
      root_uri: 'viking://resources/OpenViking',
      status: 'success',
      task_id: 'resource-task',
    })
    const onAccepted = vi.fn()
    const onCompleted = vi.fn()
    render(
      <ResourceUploadProvider>
        <UploadHarness onAccepted={onAccepted} onCompleted={onCompleted} />
      </ResourceUploadProvider>,
    )
    await waitFor(() => expect(streamMocks.options).toBeDefined())
    goLive()

    fireEvent.click(screen.getByTestId('start'))
    await waitFor(() => expect(onAccepted).toHaveBeenCalledOnce())
    act(() => {
      streamMocks.options?.onEvent({
        type: 'task',
        record: { ...runningRecord, status: 'completed', updated_at: 5 },
      })
    })

    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce())
    expect(streamMocks.options?.taskType).toBe('add_resource')
  })

  it('keeps one entry when the push beats the import response', async () => {
    apiMocks.getTasks.mockResolvedValue([runningRecord])
    let accept: (value: unknown) => void = () => undefined
    apiMocks.postResources.mockReturnValue(
      new Promise((resolve) => {
        accept = resolve
      }),
    )
    render(
      <ResourceUploadProvider>
        <UploadHarness onAccepted={vi.fn()} onCompleted={vi.fn()} />
      </ResourceUploadProvider>,
    )
    await waitFor(() => expect(streamMocks.options).toBeDefined())
    goLive()

    fireEvent.click(screen.getByTestId('start'))
    await waitFor(() => expect(apiMocks.postResources).toHaveBeenCalledOnce())
    act(() => {
      streamMocks.options?.onEvent({ type: 'task', record: runningRecord })
    })
    await act(async () => {
      accept({ status: 'success', task_id: 'resource-task' })
    })

    await waitFor(() =>
      expect(apiMocks.getTasks.mock.calls.length).toBeGreaterThan(2),
    )
    expect(screen.getByTestId('task-count').textContent).toBe('1')
  })
})

function FileUploadHarness() {
  const { enqueueUploads, tasks } = useResourceUpload()

  return (
    <>
      <button
        type="button"
        data-testid="upload"
        onClick={() =>
          enqueueUploads({
            commonBody: {},
            files: [{ file: new File(['x'], 'big.md'), fileType: null }],
          })
        }
      />
      <output data-testid="file-status">
        {tasks.find((task) => task.fileName === 'big.md')?.status}
      </output>
    </>
  )
}

describe('ResourceUploadProvider file uploads', () => {
  it('keeps a failed upload failed when a late part reports progress', async () => {
    let reportProgress: ((percent: number) => void) | undefined
    apiMocks.transferUpload.mockImplementation(
      (_item: unknown, onProgress: (percent: number) => void) => {
        reportProgress = onProgress
        return Promise.reject(new Error('rejected by proxy'))
      },
    )

    render(
      <ResourceUploadProvider>
        <FileUploadHarness />
      </ResourceUploadProvider>,
    )
    fireEvent.click(screen.getByTestId('upload'))

    await waitFor(() =>
      expect(screen.getByTestId('file-status').textContent).toBe('failed'),
    )
    expect(apiMocks.transferUpload).toHaveBeenCalledTimes(1)
    expect(reportProgress).toBeDefined()
    await act(async () => {
      reportProgress?.(60)
    })

    expect(screen.getByTestId('file-status').textContent).toBe('failed')
  })
})

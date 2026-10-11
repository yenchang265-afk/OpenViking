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

import i18n from '#/i18n'
import {
  ResourceUploadProvider,
  useResourceUpload,
} from './use-resource-upload'

const apiMocks = vi.hoisted(() => ({
  getTasks: vi.fn(),
  postResources: vi.fn(),
  transferUpload: vi.fn(),
}))

vi.mock('../-lib/upload-transfer', () => ({
  transferUpload: apiMocks.transferUpload,
}))

vi.mock('#/lib/ov-client', () => ({
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
    </>
  )
}

describe('ResourceUploadProvider remote completion', () => {
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

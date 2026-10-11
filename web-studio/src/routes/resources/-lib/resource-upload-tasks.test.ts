import { describe, expect, it } from 'vitest'

import {
  attachServerTask,
  mergeServerTasks,
  needsTaskPolling,
  upsertServerTask,
} from './resource-upload-tasks'
import type { ResourceUploadTask } from '../-hooks/use-resource-upload'
import type { TaskRecord } from '@ov-server/api/v1/tasks'

function serverRecord(error?: string): TaskRecord {
  return {
    error,
    status: 'failed',
    task_id: 'task-1',
    task_type: 'add_resource',
  } as TaskRecord
}

function previousTask(
  errorMessage: string,
  errorMessageOrigin?: ResourceUploadTask['errorMessageOrigin'],
  errorDetail?: string,
): ResourceUploadTask {
  return {
    createdAt: 1,
    errorCode: 'SERVER_TASK_FAILED',
    errorDetail,
    errorMessage,
    errorMessageOrigin,
    fileName: 'document.pdf',
    fileSize: null,
    fileType: null,
    finishedAt: 2,
    id: 'server-task-1',
    progress: null,
    rootUri: null,
    serverTaskId: 'task-1',
    source: 'server',
    status: 'failed',
  }
}

describe('mergeServerTasks', () => {
  it('preserves an existing server error when a later record omits it', () => {
    const [task] = mergeServerTasks(
      [previousTask('provider overloaded', 'server', 'provider overloaded')],
      [serverRecord()],
      { cancelled: 'Cancelled', failed: 'Processing failed' },
    )

    expect(task.errorMessage).toBe('provider overloaded')
    expect(task.errorMessageOrigin).toBe('server')
    expect(task.errorDetail).toBe('provider overloaded')
  })

  it('refreshes a generated fallback when the locale changes', () => {
    const [task] = mergeServerTasks(
      [previousTask('Processing failed', 'fallback')],
      [serverRecord()],
      { cancelled: '已取消', failed: '处理失败' },
    )

    expect(task.errorMessage).toBe('处理失败')
    expect(task.errorMessageOrigin).toBe('fallback')
    expect(task.errorDetail).toBeNull()
  })

  it('localizes the generic server processing error', () => {
    const [task] = mergeServerTasks(
      [],
      [serverRecord('resource processing failed')],
      { cancelled: '已取消', failed: '处理失败' },
    )

    expect(task.errorMessage).toBe('处理失败')
    expect(task.errorMessageOrigin).toBe('fallback')
    expect(task.errorDetail).toBe('resource processing failed')
  })

  it('preserves a detailed server error', () => {
    const [task] = mergeServerTasks([], [serverRecord('provider overloaded')], {
      cancelled: '已取消',
      failed: '处理失败',
    })

    expect(task.errorMessage).toBe('provider overloaded')
    expect(task.errorMessageOrigin).toBe('server')
    expect(task.errorDetail).toBe('provider overloaded')
  })

  it('keeps a detailed raw error when a later record is generic', () => {
    const [task] = mergeServerTasks(
      [previousTask('provider overloaded', 'server', 'provider overloaded')],
      [serverRecord('resource processing failed')],
      { cancelled: '已取消', failed: '处理失败' },
    )

    expect(task.errorMessage).toBe('provider overloaded')
    expect(task.errorDetail).toBe('provider overloaded')
  })
})

const FALLBACK = { cancelled: 'Cancelled', failed: 'Processing failed' }

function record(overrides: Partial<TaskRecord> = {}): TaskRecord {
  return {
    status: 'running',
    task_id: 'task-1',
    task_type: 'add_resource',
    updated_at: 10,
    ...overrides,
  }
}

function localTask(
  overrides: Partial<ResourceUploadTask> = {},
): ResourceUploadTask {
  return {
    ...previousTask(''),
    errorCode: null,
    errorMessage: null,
    errorMessageOrigin: undefined,
    finishedAt: null,
    id: 'local-1',
    serverTaskId: null,
    source: 'local',
    status: 'processing',
    ...overrides,
  }
}

describe('upsertServerTask', () => {
  it('adds a task started elsewhere, such as the CLI, to the top', () => {
    const existing = localTask({ id: 'other', serverTaskId: 'task-0' })

    const tasks = upsertServerTask([existing], record(), FALLBACK)

    expect(tasks.map((task) => task.serverTaskId)).toEqual(['task-1', 'task-0'])
    expect(tasks[0].source).toBe('server')
  })

  it('updates the matching task in place and keeps its local identity', () => {
    const tasks = upsertServerTask(
      [localTask({ serverTaskId: 'task-1' })],
      record({ status: 'completed' }),
      FALLBACK,
    )

    expect(tasks).toHaveLength(1)
    expect(tasks[0]).toMatchObject({
      fileName: 'document.pdf',
      id: 'local-1',
      status: 'success',
    })
  })

  it('ignores a record older than the state already shown', () => {
    const [done] = upsertServerTask(
      [localTask({ serverTaskId: 'task-1' })],
      record({ status: 'completed', updated_at: 20 }),
      FALLBACK,
    )

    const [after] = mergeServerTasks(
      [done],
      [record({ status: 'running', updated_at: 15 })],
      FALLBACK,
    )

    expect(after.status).toBe('success')
  })
})

describe('attachServerTask', () => {
  it('folds a task pushed before the import response into the local upload', () => {
    const pushed = upsertServerTask(
      [localTask()],
      record({ status: 'completed', result: { root_uri: 'viking://r' } }),
      FALLBACK,
    )

    const tasks = attachServerTask(pushed, 'local-1', 'task-1', null)

    expect(tasks).toHaveLength(1)
    expect(tasks[0]).toMatchObject({
      id: 'local-1',
      rootUri: 'viking://r',
      serverTaskId: 'task-1',
      source: 'local',
      status: 'success',
    })
  })

  it('keeps the pushed task when the local upload is already gone', () => {
    const pushed = upsertServerTask([], record(), FALLBACK)

    expect(attachServerTask(pushed, 'local-1', 'task-1', null)).toBe(pushed)
  })

  it('marks the upload processing when nothing was pushed yet', () => {
    const [task] = attachServerTask(
      [localTask({ status: 'uploading', progress: 80 })],
      'local-1',
      'task-1',
      'viking://r',
    )

    expect(task).toMatchObject({
      progress: null,
      rootUri: 'viking://r',
      serverTaskId: 'task-1',
      status: 'processing',
    })
  })
})

describe('needsTaskPolling', () => {
  it('polls only for server work this Studio started', () => {
    expect(needsTaskPolling([localTask({ serverTaskId: 'task-1' })])).toBe(true)
    expect(
      needsTaskPolling([
        localTask({ serverTaskId: 'task-1', source: 'remote' }),
      ]),
    ).toBe(true)
  })

  it('ignores tasks from other clients, finished work and pending uploads', () => {
    expect(
      needsTaskPolling([
        localTask({ serverTaskId: 'cli-task', source: 'server' }),
        localTask({ serverTaskId: 'task-2', status: 'success' }),
        localTask({ status: 'uploading' }),
      ]),
    ).toBe(false)
  })
})

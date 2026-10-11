import type {
  ResourceUploadTask,
  ResourceUploadTaskStatus,
} from '../-hooks/use-resource-upload'
import type { TaskListResult, TaskRecord } from '@ov-server/api/v1/tasks'

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isTaskRecord(value: unknown): value is TaskRecord {
  return (
    isRecord(value) &&
    typeof value.task_id === 'string' &&
    typeof value.task_type === 'string' &&
    typeof value.status === 'string'
  )
}

export function normalizeTaskList(value: unknown): TaskListResult {
  return Array.isArray(value) ? value.filter(isTaskRecord) : []
}

export function isUploadStatusActive(
  status: ResourceUploadTaskStatus,
): boolean {
  return (
    status === 'pending' || status === 'uploading' || status === 'processing'
  )
}

/**
 * Fallback polling follows only server work this Studio started. Tasks from
 * other clients still show up through pushes and list refreshes, but a stuck
 * one can no longer keep polling alive forever.
 */
export function needsTaskPolling(tasks: ResourceUploadTask[]): boolean {
  return tasks.some(
    (task) =>
      task.source !== 'server' &&
      task.serverTaskId !== null &&
      isUploadStatusActive(task.status),
  )
}

function toEpochMillis(value: unknown, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return fallback
  }
  return value > 10_000_000_000 ? Math.round(value) : Math.round(value * 1000)
}

function getResultString(record: TaskRecord, key: string): string | null {
  const value = record.result?.[key]
  return typeof value === 'string' && value.trim() ? value : null
}

function getTaskRootUri(record: TaskRecord): string | null {
  if (typeof record.resource_id === 'string' && record.resource_id.trim()) {
    return record.resource_id
  }
  return getResultString(record, 'root_uri')
}

function getNameFromUri(uri: string): string {
  const normalized = uri.replace(/\/+$/, '')
  const parts = normalized.split('/').filter(Boolean)
  return parts[parts.length - 1] || uri
}

function getServerTaskName(record: TaskRecord): string {
  const sourceName = getResultString(record, 'source_name')
  if (sourceName) {
    return sourceName
  }

  const rootUri = getTaskRootUri(record)
  if (rootUri) {
    return getNameFromUri(rootUri)
  }

  return record.task_id
}

function toUploadStatus(
  status: TaskRecord['status'],
): ResourceUploadTaskStatus {
  if (status === 'completed') {
    return 'success'
  }
  if (status === 'failed') {
    return 'failed'
  }
  if (status === 'cancelled') {
    return 'cancelled'
  }
  return 'processing'
}

function isGenericServerTaskError(error: string): boolean {
  return error.trim().toLowerCase() === 'resource processing failed'
}

function mergeServerTask(
  record: TaskRecord,
  fallbackMessages: { failed: string; cancelled: string },
  existing?: ResourceUploadTask,
): ResourceUploadTask {
  // Pushed changes and list reads can arrive out of order; never step back.
  if (
    existing?.serverUpdatedAt != null &&
    typeof record.updated_at === 'number' &&
    record.updated_at < existing.serverUpdatedAt
  ) {
    return existing
  }
  const status = toUploadStatus(record.status)
  const rootUri = getTaskRootUri(record) ?? existing?.rootUri ?? null
  const createdAt =
    existing?.createdAt ?? toEpochMillis(record.created_at, Date.now())
  const updatedAt = toEpochMillis(record.updated_at, Date.now())
  const fileName =
    existing && existing.source !== 'server'
      ? existing.fileName
      : getServerTaskName(record)
  const isFinished =
    status === 'success' || status === 'failed' || status === 'cancelled'
  const hasErrorStatus = status === 'failed' || status === 'cancelled'
  const recordErrorDetail =
    hasErrorStatus && typeof record.error === 'string' && record.error.trim()
      ? record.error.trim()
      : null
  const recordError =
    recordErrorDetail && !isGenericServerTaskError(recordErrorDetail)
      ? recordErrorDetail
      : null
  const existingError =
    hasErrorStatus &&
    existing?.errorMessage &&
    existing.errorMessageOrigin !== 'fallback'
      ? existing.errorMessage
      : null
  const fallbackError =
    status === 'failed'
      ? fallbackMessages.failed
      : status === 'cancelled'
        ? fallbackMessages.cancelled
        : null
  const errorMessage = recordError || existingError || fallbackError
  const errorMessageOrigin = recordError
    ? 'server'
    : existingError
      ? existing?.errorMessageOrigin
      : fallbackError
        ? 'fallback'
        : undefined
  const errorDetail = hasErrorStatus
    ? (recordError ?? existing?.errorDetail ?? recordErrorDetail)
    : null

  return {
    id: existing?.id ?? `server-${record.task_id}`,
    source: existing?.source ?? 'server',
    serverTaskId: record.task_id,
    fileName,
    fileSize: existing?.fileSize ?? null,
    fileType: existing?.fileType ?? null,
    status,
    progress: status === 'success' ? 100 : null,
    createdAt,
    finishedAt: isFinished ? (existing?.finishedAt ?? updatedAt) : null,
    errorCode:
      status === 'failed'
        ? (existing?.errorCode ?? 'SERVER_TASK_FAILED')
        : null,
    errorDetail,
    errorMessage,
    errorMessageOrigin,
    rootUri,
    serverUpdatedAt:
      typeof record.updated_at === 'number'
        ? record.updated_at
        : (existing?.serverUpdatedAt ?? null),
  }
}

export function mergeServerTasks(
  previous: ResourceUploadTask[],
  serverTasks: TaskRecord[],
  fallbackMessages: { failed: string; cancelled: string },
): ResourceUploadTask[] {
  const previousByServerId = new Map<string, ResourceUploadTask>()
  for (const task of previous) {
    if (task.serverTaskId) {
      previousByServerId.set(task.serverTaskId, task)
    }
  }

  const serverTaskIds = new Set(serverTasks.map((task) => task.task_id))
  const consumedLocalIds = new Set<string>()
  const nextTasks = serverTasks.map((record) => {
    const existing = previousByServerId.get(record.task_id)
    if (existing) {
      consumedLocalIds.add(existing.id)
    }
    return mergeServerTask(record, fallbackMessages, existing)
  })

  for (const task of previous) {
    if (consumedLocalIds.has(task.id)) {
      continue
    }
    if (
      task.source === 'server' &&
      task.serverTaskId &&
      !serverTaskIds.has(task.serverTaskId)
    ) {
      continue
    }
    nextTasks.push(task)
  }

  return nextTasks
}

/** Apply one pushed task change; tasks started elsewhere go on top. */
export function upsertServerTask(
  previous: ResourceUploadTask[],
  record: TaskRecord,
  fallbackMessages: { failed: string; cancelled: string },
): ResourceUploadTask[] {
  const index = previous.findIndex(
    (task) => task.serverTaskId === record.task_id,
  )
  if (index === -1) {
    return [mergeServerTask(record, fallbackMessages), ...previous]
  }
  return previous.map((task, i) =>
    i === index ? mergeServerTask(record, fallbackMessages, task) : task,
  )
}

/**
 * Link a local upload to its server task. A push can arrive before the import
 * response, so fold that server-only entry into the local task.
 */
export function attachServerTask(
  previous: ResourceUploadTask[],
  localId: string,
  serverTaskId: string,
  rootUri: string | null,
): ResourceUploadTask[] {
  if (!previous.some((task) => task.id === localId)) {
    return previous
  }
  const pushed = previous.find(
    (task) => task.source === 'server' && task.serverTaskId === serverTaskId,
  )
  return previous
    .filter((task) => task !== pushed)
    .map((task) => {
      if (task.id !== localId) {
        return task
      }
      if (!pushed) {
        return {
          ...task,
          serverTaskId,
          status: 'processing',
          progress: null,
          rootUri,
        }
      }
      return {
        ...task,
        serverTaskId,
        status: pushed.status,
        progress: pushed.progress,
        finishedAt: pushed.finishedAt,
        errorCode: pushed.errorCode,
        errorDetail: pushed.errorDetail,
        errorMessage: pushed.errorMessage,
        errorMessageOrigin: pushed.errorMessageOrigin,
        rootUri: rootUri ?? pushed.rootUri,
        serverUpdatedAt: pushed.serverUpdatedAt,
      }
    })
}

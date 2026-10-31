import * as React from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import i18n from '#/i18n'
import { getTasks, getOvResult } from '#/lib/ov-client'
import type { FolderGroup } from '../-lib/folder-upload'
import {
  isUploadStatusActive,
  mergeServerTasks,
  needsTaskPolling,
  normalizeTaskList,
  upsertServerTask,
} from '../-lib/resource-upload-tasks'
import { watchTaskEvents } from '../-lib/task-event-stream'
import {
  INITIAL_REMOTE_STATE,
  acquireUploadScope,
  getErrorMessage,
  selectRemoteState,
} from '../-lib/upload-scope'
import type { ResourceImportCommonBody } from '../-lib/resource-import-types'
import type { TaskListResult } from '@ov-server/api/v1/tasks'

export type ResourceUploadTaskStatus =
  | 'cancelled'
  | 'pending'
  | 'uploading'
  | 'processing'
  | 'success'
  | 'failed'

export type ResourceUploadTask = {
  id: string
  source: 'local' | 'remote' | 'server'
  serverTaskId: string | null
  fileName: string
  fileSize: number | null
  fileType: string | null
  status: ResourceUploadTaskStatus
  progress: number | null
  createdAt: number
  finishedAt: number | null
  errorCode: string | null
  errorDetail?: string | null
  errorMessage: string | null
  errorMessageOrigin?: 'fallback' | 'server' | undefined
  rootUri: string | null
  /** Server `updated_at` of the last applied record, to drop stale ones. */
  serverUpdatedAt?: number | null
}

export type RemoteUploadPhase = 'idle' | 'processing' | 'done'

export type RemoteUploadState = {
  phase: RemoteUploadPhase
  skippedFiles: string[]
  error: string | null
  remoteUrl: string
  taskId: string | null
}

export type UploadBatchItem = {
  /** The file to upload; for a folder, only a label carrying its name. */
  file: File
  fileType: string | null
  /** Set for a folder, uploaded file by file through a chunked session. */
  folder?: FolderGroup
}

export type UploadBatchParams = {
  files: UploadBatchItem[]
  commonBody: ResourceImportCommonBody
}

export type RemoteStartResult = {
  rootUri: string | null
  taskId: string | null
}

export type RemoteStartParams = {
  url: string
  commonBody: ResourceImportCommonBody
  onAccepted?: (result: RemoteStartResult) => void
  onCompleted?: () => void
  onFailed?: () => void
}

type ResourceUploadContextValue = {
  tasks: ResourceUploadTask[]
  remoteState: RemoteUploadState
  enqueueUploads: (params: UploadBatchParams) => void
  /** Stop a local upload still queued or sending data. */
  cancelUpload: (taskId: string) => void
  startRemote: (params: RemoteStartParams) => void
  resetRemote: () => void
  refreshTasks: () => Promise<void>
  isRefreshingTasks: boolean
  hasActiveTasks: boolean
  activeTaskCount: number
}

type RefreshTasksOptions = {
  notifyOnError?: boolean
  silent?: boolean
}

const RESOURCE_ADD_TASK_TYPE = 'add_resource'
const TASK_REFRESH_INTERVAL_MS = 3_000
const TASK_REFRESH_LIMIT = 50

const ResourceUploadContext =
  React.createContext<ResourceUploadContextValue | null>(null)

function getFallbackMessages(): { failed: string; cancelled: string } {
  return {
    failed: i18n.t('resources:processingTasks.errors.failed'),
    cancelled: i18n.t('resources:processingTasks.errors.cancelled'),
  }
}

function usePageVisible(): boolean {
  const [visible, setVisible] = React.useState(
    () => typeof document === 'undefined' || !document.hidden,
  )
  React.useEffect(() => {
    const onChange = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])
  return visible
}

/** Run a page callback only while the page that passed it is still mounted. */
function whileMounted<TArgs extends unknown[]>(
  mountedRef: { readonly current: boolean },
  callback: ((...args: TArgs) => void) | undefined,
): ((...args: TArgs) => void) | undefined {
  if (!callback) return undefined
  return (...args: TArgs) => {
    if (mountedRef.current) callback(...args)
  }
}

export function useResourceUpload(): ResourceUploadContextValue {
  const context = React.useContext(ResourceUploadContext)
  if (!context) {
    // eslint-disable-next-line studio-i18n/no-literal-message -- Developer invariant; retain the diagnostic for debugging.
    throw new Error(
      'useResourceUpload must be used within ResourceUploadProvider.',
    )
  }
  return context
}

/**
 * Shows the uploads of the current connection and keeps their server tasks in
 * sync. Uploads run in the connection's upload scope, so unmounting the provider
 * (leaving the page) stops only its task reads, never an upload in progress.
 */
export function ResourceUploadProvider({
  children,
  enabled = true,
  remoteOwner = 'default',
}: {
  children: React.ReactNode
  enabled?: boolean
  /**
   * The page whose remote-import form this provider serves. Each page sees and
   * resets only its own import; the shared task list shows all of them.
   */
  remoteOwner?: string
}) {
  const { t } = useTranslation('resources', { i18n })
  const [scope] = React.useState(acquireUploadScope)
  const snapshot = React.useSyncExternalStore(
    scope.subscribe,
    scope.getSnapshot,
    scope.getSnapshot,
  )
  const tasks = snapshot.tasks
  const remoteState = selectRemoteState(snapshot, remoteOwner)
  const setTasks = scope.setTasks
  const [isRefreshingTasks, setIsRefreshingTasks] = React.useState(false)
  const mountedRef = React.useRef(true)
  const operationsRef = React.useRef(new Set<AbortController>())
  const refreshAbortRef = React.useRef<AbortController | null>(null)
  const refreshQueuedRef = React.useRef(false)
  const [liveTaskEvents, setLiveTaskEvents] = React.useState(false)
  const isPageVisible = usePageVisible()

  const isSourceCurrent = React.useCallback(
    () => mountedRef.current && scope.isCurrent(),
    [scope],
  )

  const beginOperation = React.useCallback(() => {
    if (!isSourceCurrent()) return null
    const controller = new AbortController()
    operationsRef.current.add(controller)
    return controller
  }, [isSourceCurrent])

  const isOperationCurrent = React.useCallback(
    (controller: AbortController) => {
      if (controller.signal.aborted) return false
      if (isSourceCurrent()) return true
      controller.abort()
      return false
    },
    [isSourceCurrent],
  )

  React.useEffect(() => {
    mountedRef.current = true
    // A page that comes back resumes an import still running, but not the
    // result or error of one that already finished.
    scope.setRemoteState(remoteOwner, (previous) =>
      previous.phase === 'processing' ? previous : INITIAL_REMOTE_STATE,
    )
    const operations = operationsRef.current
    return () => {
      // Task reads belong to this page; uploads belong to the scope and go on.
      mountedRef.current = false
      for (const controller of operations) controller.abort()
      operations.clear()
      refreshAbortRef.current = null
    }
  }, [remoteOwner, scope])

  const refreshTasks = React.useCallback(
    async (options: RefreshTasksOptions = {}) => {
      if (refreshAbortRef.current && !refreshAbortRef.current.signal.aborted) {
        // The read in flight may predate what the caller needs (e.g. a fresh
        // stream subscription), so read again once it settles.
        refreshQueuedRef.current = true
        return
      }
      const controller = beginOperation()
      if (!controller) return

      refreshAbortRef.current = controller
      if (!options.silent) {
        setIsRefreshingTasks(true)
      }

      try {
        let rerun = true
        while (rerun) {
          refreshQueuedRef.current = false
          try {
            const result = await getOvResult<TaskListResult>(
              getTasks({
                client: scope.client,
                signal: controller.signal,
                query: {
                  limit: TASK_REFRESH_LIMIT,
                  task_type: RESOURCE_ADD_TASK_TYPE,
                },
              }),
            )
            if (!isOperationCurrent(controller)) return
            const serverTasks = normalizeTaskList(result)
            setTasks((prev) =>
              mergeServerTasks(prev, serverTasks, getFallbackMessages()),
            )
          } catch (error) {
            if (!isOperationCurrent(controller)) return
            if (options.notifyOnError !== false) {
              toast.error(getErrorMessage(error), { duration: 5000 })
            }
          }
          rerun = refreshQueuedRef.current
        }
      } finally {
        operationsRef.current.delete(controller)
        if (refreshAbortRef.current === controller) {
          refreshAbortRef.current = null
          if (isOperationCurrent(controller) && !options.silent) {
            setIsRefreshingTasks(false)
          }
        }
      }
    },
    [beginOperation, isOperationCurrent, scope, setTasks],
  )

  // An import that hands its work to a server task asks for a fresh task list.
  React.useEffect(
    () =>
      scope.onRefreshRequested(() => {
        void refreshTasks({ notifyOnError: false, silent: true })
      }),
    [refreshTasks, scope],
  )

  const enqueueUploads = React.useCallback(
    (params: UploadBatchParams) => {
      if (!isSourceCurrent()) return
      scope.enqueueUploads(params)
    },
    [isSourceCurrent, scope],
  )

  const cancelUpload = React.useCallback(
    (taskId: string) => {
      if (!isSourceCurrent()) return
      scope.cancelUpload(taskId)
    },
    [isSourceCurrent, scope],
  )

  const startRemote = React.useCallback(
    (params: RemoteStartParams) => {
      if (!isSourceCurrent()) return
      // The import itself goes on after this page unmounts; its callbacks
      // update this page, so they stop with it.
      scope.startRemote(remoteOwner, {
        ...params,
        onAccepted: whileMounted(mountedRef, params.onAccepted),
        onCompleted: whileMounted(mountedRef, params.onCompleted),
        onFailed: whileMounted(mountedRef, params.onFailed),
      })
    },
    [isSourceCurrent, remoteOwner, scope],
  )

  const resetRemote = React.useCallback(() => {
    if (!isSourceCurrent()) return
    scope.resetRemote(remoteOwner)
  }, [isSourceCurrent, remoteOwner, scope])

  // Load on mount and language change; catch up when the tab shows again,
  // since fallback polling pauses while it is hidden.
  React.useEffect(() => {
    if (enabled && isPageVisible) {
      void refreshTasks({ notifyOnError: false, silent: true })
    }
  }, [enabled, isPageVisible, refreshTasks, t])

  React.useEffect(() => {
    if (!enabled) return undefined
    return watchTaskEvents({
      taskType: RESOURCE_ADD_TASK_TYPE,
      onLiveChange: setLiveTaskEvents,
      onEvent: (event) => {
        if (event.type === 'task') {
          setTasks((prev) =>
            upsertServerTask(prev, event.record, getFallbackMessages()),
          )
          return
        }
        // Subscribed (or changes were dropped): re-read the list so nothing
        // that changed before the subscription is missed.
        void refreshTasks({ notifyOnError: false, silent: true })
      },
    })
  }, [enabled, refreshTasks, setTasks])

  // Polling is only the fallback while pushes are unavailable or partial.
  const shouldPollTasks = React.useMemo(
    () => !liveTaskEvents && isPageVisible && needsTaskPolling(tasks),
    [isPageVisible, liveTaskEvents, tasks],
  )

  React.useEffect(() => {
    if (!shouldPollTasks) {
      return undefined
    }

    const interval = window.setInterval(() => {
      void refreshTasks({ notifyOnError: false, silent: true })
    }, TASK_REFRESH_INTERVAL_MS)

    return () => window.clearInterval(interval)
  }, [shouldPollTasks, refreshTasks])

  React.useEffect(() => {
    if (!isSourceCurrent()) return
    if (remoteState.phase !== 'processing' || !remoteState.taskId) {
      return
    }

    const remoteTask = tasks.find(
      (task) => task.serverTaskId === remoteState.taskId,
    )
    if (!remoteTask || isUploadStatusActive(remoteTask.status)) {
      return
    }

    if (remoteTask.status === 'success') {
      scope.setRemoteState(remoteOwner, (prev) =>
        prev.taskId === remoteTask.serverTaskId
          ? { ...prev, phase: 'done', error: null }
          : prev,
      )
      return
    }

    if (remoteTask.status === 'failed') {
      scope.setRemoteState(remoteOwner, (prev) =>
        prev.taskId === remoteTask.serverTaskId
          ? {
              ...prev,
              phase: 'idle',
              error:
                remoteTask.errorMessage || t('processingTasks.errors.failed'),
            }
          : prev,
      )
      return
    }

    if (remoteTask.status === 'cancelled') {
      scope.setRemoteState(remoteOwner, (prev) =>
        prev.taskId === remoteTask.serverTaskId
          ? {
              ...prev,
              phase: 'idle',
              error:
                remoteTask.errorMessage ||
                t('processingTasks.errors.cancelled'),
            }
          : prev,
      )
    }
  }, [
    isSourceCurrent,
    remoteOwner,
    remoteState.phase,
    remoteState.taskId,
    scope,
    t,
    tasks,
  ])

  React.useEffect(() => {
    if (!isSourceCurrent()) return
    for (const task of tasks) {
      if (!task.serverTaskId || isUploadStatusActive(task.status)) {
        continue
      }

      const callbacks = scope.remoteCompletionCallbacks.get(task.serverTaskId)
      if (!callbacks) {
        continue
      }

      scope.remoteCompletionCallbacks.delete(task.serverTaskId)
      if (task.status === 'success') {
        callbacks.onCompleted?.()
      } else {
        callbacks.onFailed?.()
      }
    }
  }, [isSourceCurrent, scope, tasks])

  React.useEffect(() => {
    if (!isSourceCurrent()) return
    for (const task of tasks) {
      if (
        !task.serverTaskId ||
        task.source === 'server' ||
        isUploadStatusActive(task.status) ||
        scope.notifiedServerTaskIds.has(task.serverTaskId)
      ) {
        continue
      }

      scope.notifiedServerTaskIds.add(task.serverTaskId)
      if (task.status === 'success') {
        toast.success(task.fileName)
      } else if (task.status === 'failed') {
        toast.error(task.errorMessage || task.fileName, { duration: 5000 })
      }
    }
  }, [isSourceCurrent, scope, tasks])

  const activeTaskCount = React.useMemo(
    () => tasks.filter((task) => isUploadStatusActive(task.status)).length,
    [tasks],
  )
  const hasActiveTasks = activeTaskCount > 0

  const value = React.useMemo<ResourceUploadContextValue>(
    () => ({
      tasks,
      remoteState,
      enqueueUploads,
      cancelUpload,
      startRemote,
      resetRemote,
      refreshTasks,
      isRefreshingTasks,
      hasActiveTasks,
      activeTaskCount,
    }),
    [
      tasks,
      remoteState,
      enqueueUploads,
      cancelUpload,
      startRemote,
      resetRemote,
      refreshTasks,
      isRefreshingTasks,
      hasActiveTasks,
      activeTaskCount,
    ],
  )

  return (
    <ResourceUploadContext.Provider value={value}>
      {children}
    </ResourceUploadContext.Provider>
  )
}

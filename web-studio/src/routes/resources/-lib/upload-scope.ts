/**
 * Resource uploads and remote imports that outlive the page that started them.
 *
 * A scope belongs to one connection (service URL, auth mode and identity) and runs
 * its jobs with a client bound to that connection, whether or not a
 * ResourceUploadProvider is mounted: leaving the page that started an upload does
 * not cancel it, and coming back shows its task again. A connection change cancels
 * the scope's jobs; a cancelled chunked upload then discards its server session.
 */
import { toast } from 'sonner'

import i18n from '#/i18n'
import {
  createOvClient,
  getOvResult,
  isOvClientError,
  ovClient,
} from '#/lib/ov-client'
import type { OvClientAdapter } from '#/lib/ov-client'
import { parseUploadError } from './upload'
import { transferUpload } from './upload-transfer'
import { attachServerTask, isCancellableUpload } from './resource-upload-tasks'
import {
  buildRemoteResourceRequest,
  buildUploadedResourceRequest,
} from './resource-import-request'
import { postResourceImport } from './resource-import-api'
import { getFolderSize } from './folder-upload'
import type {
  ResourceImportCommonBody,
  ResourceImportResult,
} from './resource-import-types'
import type {
  RemoteStartParams,
  RemoteUploadState,
  ResourceUploadTask,
  UploadBatchItem,
  UploadBatchParams,
} from '../-hooks/use-resource-upload'

export const INITIAL_REMOTE_STATE: RemoteUploadState = {
  phase: 'idle',
  skippedFiles: [],
  error: null,
  remoteUrl: '',
  taskId: null,
}

export interface UploadScopeSnapshot {
  tasks: ResourceUploadTask[]
  /** Remote import form state per page (see ResourceUploadProvider remoteOwner). */
  remoteStates: Readonly<Record<string, RemoteUploadState>>
}

export function selectRemoteState(
  snapshot: UploadScopeSnapshot,
  owner: string,
): RemoteUploadState {
  return snapshot.remoteStates[owner] ?? INITIAL_REMOTE_STATE
}

export interface RemoteCompletionCallbacks {
  onCompleted?: () => void
  onFailed?: () => void
}

type Updater<T> = T | ((previous: T) => T)

export interface UploadScope {
  readonly client: OvClientAdapter['client']
  /** Server task ids whose completion toast was already shown. */
  readonly notifiedServerTaskIds: Set<string>
  /** Page callbacks to run when a remote import's server task finishes. */
  readonly remoteCompletionCallbacks: Map<string, RemoteCompletionCallbacks>
  isCurrent: () => boolean
  getSnapshot: () => UploadScopeSnapshot
  subscribe: (listener: () => void) => () => void
  setTasks: (updater: Updater<ResourceUploadTask[]>) => void
  setRemoteState: (owner: string, updater: Updater<RemoteUploadState>) => void
  /** Register a task-list refresh to run after an import hands work to the server. */
  onRefreshRequested: (refresh: () => void) => () => void
  enqueueUploads: (params: UploadBatchParams) => void
  /** Stop a local upload still queued or sending data (see isCancellableUpload). */
  cancelUpload: (taskId: string) => void
  /** Start one remote import per owner; the owner's form tracks only its own. */
  startRemote: (owner: string, params: RemoteStartParams) => void
  resetRemote: (owner: string) => void
  /** Stop every job for good; acquireUploadScope then starts a new scope. */
  cancel: () => void
}

export function getErrorMessage(error: unknown): string {
  if (isOvClientError(error)) {
    return `${error.code}: ${error.message}`
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function createTaskId(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID()
  }
  return `upload-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function createRemoteTaskName(url: string): string {
  const trimmed = url.trim()
  const sshMatch = trimmed.match(/^git@[^:]+:([^/]+\/[^/]+?)(?:\.git)?$/)
  if (sshMatch) {
    return sshMatch[1]
  }

  try {
    const parsed = new URL(trimmed)
    const parts = parsed.pathname.split('/').filter(Boolean)
    if (parts.length >= 2 && parsed.hostname.includes('github.com')) {
      return `${parts[0]}/${parts[1].replace(/\.git$/, '')}`
    }
    if (parts.length > 0) {
      return parts[parts.length - 1].replace(/\.git$/, '')
    }
    return parsed.hostname
  } catch {
    return trimmed
  }
}

/**
 * A client bound to the current connection, and a check that the app still uses
 * the same service and identity.
 *
 * `identityHeaders` is not part of the identity: it follows the server mode, which
 * reads 'checking' during every health re-check (e.g. after saving the active
 * profile) and is applied after child effects run on the first trusted-mode
 * render. Counting it would cancel uploads, or make a fresh scope stale, with no
 * real change. Once the app sends identity headers for this identity, the bound
 * client sends them too, and keeps sending them through later re-checks.
 */
function captureConnection() {
  const options = ovClient.getOptions()
  const connection = ovClient.getConnection()
  const adapter = createOvClient({
    ...options,
    apiKeyStorageKey: '',
    connection,
  })

  return {
    client: adapter.client,
    isCurrent() {
      const currentOptions = ovClient.getOptions()
      const current = ovClient.getConnection()
      const same =
        currentOptions.baseUrl === options.baseUrl &&
        currentOptions.apiKeyAuth === options.apiKeyAuth &&
        current.accountId === connection.accountId &&
        current.userId === connection.userId &&
        current.apiKey === connection.apiKey &&
        current.adminApiKey === connection.adminApiKey
      if (
        same &&
        current.identityHeaders &&
        !adapter.getConnection().identityHeaders
      ) {
        adapter.setConnection({ identityHeaders: true })
      }
      return same
    },
  }
}

const CONNECTION_CHECK_INTERVAL_MS = 1_000

// Jobs still sending data from this tab; closing it would lose them.
const runningJobs = new Set<AbortController>()

function warnBeforeUnload(event: BeforeUnloadEvent): void {
  event.preventDefault()
  // Browsers that predate preventDefault() here only prompt for a returnValue.
  event.returnValue = ''
}

function trackJob(controller: AbortController): void {
  if (runningJobs.size === 0 && typeof window !== 'undefined') {
    window.addEventListener('beforeunload', warnBeforeUnload)
  }
  runningJobs.add(controller)
}

function untrackJob(controller: AbortController): void {
  if (!runningJobs.delete(controller)) return
  if (runningJobs.size === 0 && typeof window !== 'undefined') {
    window.removeEventListener('beforeunload', warnBeforeUnload)
  }
}

function resolve<T>(updater: Updater<T>, previous: T): T {
  return typeof updater === 'function'
    ? (updater as (previous: T) => T)(previous)
    : updater
}

function createUploadScope(): UploadScope {
  const connection = captureConnection()
  const client = connection.client
  const listeners = new Set<() => void>()
  const refreshers = new Set<() => void>()
  const jobs = new Set<AbortController>()
  const remoteControllers = new Map<string, AbortController>()
  const uploadControllers = new Map<string, AbortController>()
  let connectionWatch: ReturnType<typeof setInterval> | null = null
  let cancelled = false
  let snapshot: UploadScopeSnapshot = { tasks: [], remoteStates: {} }
  let uploadQueue: Promise<void> = Promise.resolve()

  const isCurrent = () => !cancelled && connection.isCurrent()

  const publish = (next: UploadScopeSnapshot) => {
    snapshot = next
    for (const listener of listeners) listener()
  }

  const setTasks = (updater: Updater<ResourceUploadTask[]>) => {
    if (!isCurrent()) return
    const tasks = resolve(updater, snapshot.tasks)
    if (tasks !== snapshot.tasks) publish({ ...snapshot, tasks })
  }

  const setRemoteState = (
    owner: string,
    updater: Updater<RemoteUploadState>,
  ) => {
    if (!isCurrent()) return
    const previous = selectRemoteState(snapshot, owner)
    const next = resolve(updater, previous)
    if (next === previous) return
    publish({
      ...snapshot,
      remoteStates: { ...snapshot.remoteStates, [owner]: next },
    })
  }

  const updateTask = (
    taskId: string,
    updater: (task: ResourceUploadTask) => ResourceUploadTask,
  ) =>
    setTasks((previous) =>
      previous.map((task) => (task.id === taskId ? updater(task) : task)),
    )

  const requestRefresh = () => {
    for (const refresh of refreshers) refresh()
  }

  const stopConnectionWatch = () => {
    if (connectionWatch === null) return
    clearInterval(connectionWatch)
    connectionWatch = null
  }

  const beginJob = (): AbortController | null => {
    if (!isCurrent()) return null
    const controller = new AbortController()
    jobs.add(controller)
    trackJob(controller)
    // A job only checks the connection when it reports progress or reaches a
    // step, and a remote import does neither while its request is open. Check
    // on a timer too, so a connection switch stops every job promptly.
    connectionWatch ??= setInterval(() => {
      if (!connection.isCurrent()) scope.cancel()
    }, CONNECTION_CHECK_INTERVAL_MS)
    return controller
  }

  const endJob = (controller: AbortController) => {
    jobs.delete(controller)
    untrackJob(controller)
    if (jobs.size === 0) stopConnectionWatch()
  }

  /**
   * False once the job is cancelled. A connection change cancels the whole scope
   * here, so switching back later starts a new scope instead of reviving this
   * one with tasks stuck where they stopped.
   */
  const isJobCurrent = (controller: AbortController) => {
    if (controller.signal.aborted) return false
    if (isCurrent()) return true
    scope.cancel()
    return false
  }

  const runFileUpload = async (
    taskId: string,
    params: UploadBatchItem,
    commonBody: ResourceImportCommonBody,
    controller: AbortController,
  ): Promise<void> => {
    try {
      if (!isJobCurrent(controller)) return
      updateTask(taskId, (task) => ({
        ...task,
        status: 'uploading',
        progress: 0,
      }))

      const { tempFileId, sourceName } = await transferUpload(
        params,
        // Each part's report also notices a connection change, so the transfer
        // stops (and discards its session) without waiting for the last part.
        // Parts still in flight can report after the transfer has failed; only
        // an uploading task takes progress, so a late report never turns a
        // failed task back into an uploading one.
        (progress) => {
          if (!isJobCurrent(controller)) return
          updateTask(taskId, (task) =>
            task.status === 'uploading' ? { ...task, progress } : task,
          )
        },
        { client, signal: controller.signal },
      )
      if (!isJobCurrent(controller)) return

      updateTask(taskId, (task) => ({
        ...task,
        status: 'processing',
        progress: null,
      }))

      const addResult = await getOvResult<ResourceImportResult>(
        postResourceImport(
          buildUploadedResourceRequest(tempFileId, sourceName, commonBody),
          { client, signal: controller.signal },
        ),
      )
      if (!isJobCurrent(controller)) return

      if (addResult.status === 'error') {
        const errors = Array.isArray(addResult.errors) ? addResult.errors : []
        throw new Error(
          errors.join('; ') ||
            i18n.t('resources:processingTasks.errors.failed'),
        )
      }

      const rootUri =
        typeof addResult.root_uri === 'string' ? addResult.root_uri : null
      const serverTaskId =
        typeof addResult.task_id === 'string' && addResult.task_id.trim()
          ? addResult.task_id
          : null

      if (serverTaskId) {
        setTasks((previous) =>
          attachServerTask(previous, taskId, serverTaskId, rootUri),
        )
        requestRefresh()
        return
      }

      updateTask(taskId, (task) => ({
        ...task,
        status: 'success',
        progress: 100,
        finishedAt: Date.now(),
        rootUri,
      }))
      toast.success(params.file.name)
    } catch (error) {
      if (!isJobCurrent(controller)) return
      const { errorCode, errorMessage } = parseUploadError(
        getErrorMessage(error),
      )
      updateTask(taskId, (task) => ({
        ...task,
        status: 'failed',
        progress: null,
        finishedAt: Date.now(),
        errorCode,
        errorMessage,
      }))
      toast.error(errorMessage, { duration: 5000 })
    } finally {
      uploadControllers.delete(taskId)
      endJob(controller)
    }
  }

  const enqueueUploads = (params: UploadBatchParams) => {
    if (params.files.length === 0 || !isCurrent()) return

    const createdAt = Date.now()
    const nextTasks: ResourceUploadTask[] = params.files.map((item, index) => ({
      id: createTaskId(),
      source: 'local',
      serverTaskId: null,
      fileName: item.file.name,
      fileSize: item.folder ? getFolderSize(item.folder) : item.file.size,
      fileType: item.fileType,
      status: 'pending',
      progress: 0,
      createdAt: createdAt + index,
      finishedAt: null,
      errorCode: null,
      errorMessage: null,
      rootUri: null,
    }))
    setTasks((previous) => [...nextTasks, ...previous])

    // Files upload one at a time, in the order they were queued. Each has its
    // own controller, so cancelling one moves the queue on to the next.
    let batch = uploadQueue
    for (const [index, item] of params.files.entries()) {
      const task = nextTasks[index]
      const controller = beginJob()
      if (!controller) break
      uploadControllers.set(task.id, controller)
      batch = batch.then(() =>
        runFileUpload(task.id, item, params.commonBody, controller),
      )
    }
    // The queue lives as long as the scope: never let one failure stall it.
    uploadQueue = batch.catch(() => undefined)
  }

  /** Stop a local upload that is still queued or sending data. */
  const cancelUpload = (taskId: string) => {
    const controller = uploadControllers.get(taskId)
    const task = snapshot.tasks.find((item) => item.id === taskId)
    if (!controller || !task || !isCancellableUpload(task)) return
    controller.abort()
    updateTask(taskId, (current) => ({
      ...current,
      status: 'cancelled',
      progress: null,
      finishedAt: Date.now(),
      errorCode: 'CANCELED',
      errorMessage: i18n.t('resources:processingTasks.errors.uploadCancelled'),
    }))
  }

  const runRemoteImport = async (
    owner: string,
    taskId: string,
    params: RemoteStartParams,
    controller: AbortController,
  ): Promise<void> => {
    const setOwnRemoteState = (state: RemoteUploadState) =>
      setRemoteState(owner, state)
    try {
      const result = await getOvResult<ResourceImportResult>(
        postResourceImport(
          buildRemoteResourceRequest(params.url, params.commonBody),
          { client, signal: controller.signal },
        ),
      )
      if (!isJobCurrent(controller)) return

      if (result.status === 'error') {
        const errors = Array.isArray(result.errors) ? result.errors : []
        throw new Error(
          errors.join('; ') ||
            i18n.t('resources:processingTasks.errors.failed'),
        )
      }

      const warnings = Array.isArray(result.warnings) ? result.warnings : []
      const rootUri =
        typeof result.root_uri === 'string' ? result.root_uri : null
      const serverTaskId =
        typeof result.task_id === 'string' && result.task_id.trim()
          ? result.task_id
          : null

      params.onAccepted?.({ rootUri, taskId: serverTaskId })
      if (!isJobCurrent(controller)) return

      if (serverTaskId) {
        if (params.onCompleted || params.onFailed) {
          scope.remoteCompletionCallbacks.set(serverTaskId, {
            onCompleted: params.onCompleted,
            onFailed: params.onFailed,
          })
        }
        setTasks((previous) =>
          attachServerTask(previous, taskId, serverTaskId, rootUri),
        )
        setOwnRemoteState({
          phase: 'processing',
          skippedFiles: warnings,
          error: null,
          remoteUrl: params.url,
          taskId: serverTaskId,
        })
        requestRefresh()
        return
      }

      params.onCompleted?.()
      if (!isJobCurrent(controller)) return

      updateTask(taskId, (task) => ({
        ...task,
        status: 'success',
        progress: 100,
        finishedAt: Date.now(),
        rootUri,
      }))
      setOwnRemoteState({
        phase: 'done',
        skippedFiles: warnings,
        error: null,
        remoteUrl: params.url,
        taskId: null,
      })
      toast.success(params.url)
    } catch (error) {
      if (!isCurrent()) return
      if (controller.signal.aborted) {
        params.onFailed?.()
        updateTask(taskId, (task) => ({
          ...task,
          status: 'failed',
          progress: null,
          finishedAt: Date.now(),
          errorCode: 'CANCELED',
          errorMessage: i18n.t('resources:processingTasks.errors.cancelled'),
        }))
        return
      }
      const message = getErrorMessage(error)
      const { errorCode, errorMessage } = parseUploadError(message)
      params.onFailed?.()
      updateTask(taskId, (task) => ({
        ...task,
        status: 'failed',
        progress: null,
        finishedAt: Date.now(),
        errorCode,
        errorMessage,
      }))
      setOwnRemoteState({
        phase: 'idle',
        skippedFiles: [],
        error: message,
        remoteUrl: params.url,
        taskId: null,
      })
      toast.error(errorMessage, { duration: 5000 })
    } finally {
      endJob(controller)
      if (remoteControllers.get(owner) === controller) {
        remoteControllers.delete(owner)
      }
    }
  }

  const startRemote = (owner: string, params: RemoteStartParams) => {
    if (remoteControllers.has(owner)) return
    const controller = beginJob()
    if (!controller) return
    remoteControllers.set(owner, controller)
    const taskId = createTaskId()

    setTasks((previous) => [
      {
        id: taskId,
        source: 'remote',
        serverTaskId: null,
        fileName: createRemoteTaskName(params.url),
        fileSize: null,
        fileType: null,
        status: 'processing',
        progress: null,
        createdAt: Date.now(),
        finishedAt: null,
        errorCode: null,
        errorMessage: null,
        rootUri: null,
      },
      ...previous,
    ])
    setRemoteState(owner, {
      phase: 'processing',
      skippedFiles: [],
      error: null,
      remoteUrl: params.url,
      taskId: null,
    })
    void runRemoteImport(owner, taskId, params, controller)
  }

  const resetRemote = (owner: string) => {
    if (!isCurrent()) return
    remoteControllers.get(owner)?.abort()
    remoteControllers.delete(owner)
    setRemoteState(owner, INITIAL_REMOTE_STATE)
  }

  const cancel = () => {
    cancelled = true
    for (const controller of jobs) {
      controller.abort()
      untrackJob(controller)
    }
    jobs.clear()
    stopConnectionWatch()
    remoteControllers.clear()
    uploadControllers.clear()
    listeners.clear()
    refreshers.clear()
    scope.remoteCompletionCallbacks.clear()
  }

  const scope: UploadScope = {
    client,
    notifiedServerTaskIds: new Set(),
    remoteCompletionCallbacks: new Map(),
    isCurrent,
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    setTasks,
    setRemoteState,
    onRefreshRequested: (refresh) => {
      refreshers.add(refresh)
      return () => refreshers.delete(refresh)
    },
    enqueueUploads,
    cancelUpload,
    startRemote,
    resetRemote,
    cancel,
  }
  return scope
}

let activeScope: UploadScope | null = null

/**
 * The upload scope of the current connection. A scope left from another
 * connection is cancelled, so its uploads stop instead of finishing for an
 * identity the user has switched away from.
 */
export function acquireUploadScope(): UploadScope {
  if (activeScope?.isCurrent()) return activeScope
  activeScope?.cancel()
  activeScope = createUploadScope()
  return activeScope
}

/** Cancel every job and forget the scope; tests start each case clean. */
export function resetUploadScopeForTests(): void {
  activeScope?.cancel()
  activeScope = null
}

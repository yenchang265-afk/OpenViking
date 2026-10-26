import i18n from '#/i18n/core'
import { getOvResult, ovClient, OvClientError } from '#/lib/ov-client'
import { fetchFsList } from '#/routes/resources/-lib/api'
import type { TaskRecord } from '#/routes/tasks/-lib/task-record'

export type CompileRequest = {
  from: string[]
  to: string
  skill: string
  instruction?: string
  args?: Record<string, unknown>
}
export type CompileTask = TaskRecord & {
  task_id: string
  meta?: { request?: CompileRequest }
}
type CompileTaskPayload = Omit<CompileTask, 'meta'> & {
  meta?: {
    request?: Omit<CompileRequest, 'from'> & { from?: string[] | null }
  }
}
export type TaskPage = {
  items: CompileTask[]
  next_cursor: string | null
  has_more: boolean
}
type TaskPagePayload = Omit<TaskPage, 'items'> & { items: CompileTaskPayload[] }

const normalizeCompileTask = (task: CompileTaskPayload): CompileTask => {
  const request = task.meta?.request
  if (!request) return task as CompileTask
  return {
    ...task,
    meta: { ...task.meta, request: { ...request, from: request.from ?? [] } },
  }
}
export const active = (status?: string) =>
  ['pending', 'running', 'cancelling'].includes(status ?? '')
export const taskTitle = (task: CompileTask) =>
  task.meta?.request
    ? `${task.meta.request.skill.split('/').pop()} → ${task.meta.request.to.split('/').pop()}`
    : task.task_id
export const errorText = (error: unknown) =>
  error && typeof error === 'object' && 'message' in error
    ? String(error.message)
    : String(error)
export async function fetchCompileTasks(
  status = '',
  q = '',
  cursor?: string,
  signal?: AbortSignal,
) {
  const page = await getOvResult<TaskPagePayload>(
    ovClient.client.get({
      url: '/api/v1/tasks',
      signal,
      query: {
        task_type: 'compile',
        pagination: 'cursor',
        limit: 30,
        ...(status ? { status } : {}),
        ...(q ? { q } : {}),
        ...(cursor ? { cursor } : {}),
      },
    }),
  )
  if (!Array.isArray(page.items))
    throw new OvClientError({
      code: 'PAGINATION_UNSUPPORTED',
      message: i18n.t('compile:errors.upgrade'),
    })
  return { ...page, items: page.items.map(normalizeCompileTask) }
}
export async function fetchCompileTask(id: string, signal?: AbortSignal) {
  return normalizeCompileTask(
    await getOvResult<CompileTaskPayload>(
      ovClient.client.get({
        url: `/api/v1/tasks/${encodeURIComponent(id)}`,
        signal,
        query: { include_events: true },
      }),
    ),
  )
}
export async function createCompile(body: CompileRequest, key: string) {
  return normalizeCompileTask(
    await getOvResult<CompileTaskPayload>(
      ovClient.client.post({
        url: '/api/v1/compile',
        body,
        headers: { 'Idempotency-Key': key },
      }),
    ),
  )
}
export async function cancelCompile(id: string) {
  return normalizeCompileTask(
    await getOvResult<CompileTaskPayload>(
      ovClient.client.post({
        url: `/api/v1/tasks/${encodeURIComponent(id)}/cancel`,
      }),
    ),
  )
}
export function fetchCapabilities() {
  return getOvResult<{
    configured: boolean
    can_create: boolean
    reason_code?: string
  }>(ovClient.client.get({ url: '/api/v1/compile/capabilities' }))
}
export async function lookupSubmission(key: string) {
  return normalizeCompileTask(
    await getOvResult<CompileTaskPayload>(
      ovClient.client.get({
        url: `/api/v1/compile/submissions/${encodeURIComponent(key)}`,
      }),
    ),
  )
}
export type CompileSkill = { name: string; uri: string; description: string }
/** Bundled compile Skills, synced into every account's system namespace. */
export const SYSTEM_EXAMPLE_SKILLS_ROOT =
  'viking://system/compile/example-skills'

async function fetchInstalledSkills(
  signal?: AbortSignal,
): Promise<CompileSkill[]> {
  const result = await getOvResult<{
    skills: Array<{
      name: string
      uri?: string
      root_uri?: string
      description?: string
    }>
  }>(ovClient.client.get({ url: '/api/v1/skills', signal }))
  return result.skills.flatMap((s) => {
    const uri = s.uri || s.root_uri
    return uri ? [{ name: s.name, uri, description: s.description || '' }] : []
  })
}

/** Built-in Skills are optional: servers without the system namespace list none. */
async function fetchSystemExampleSkills(): Promise<CompileSkill[]> {
  try {
    const { entries } = await fetchFsList(SYSTEM_EXAMPLE_SKILLS_ROOT, {
      sortBy: 'name',
      sortOrder: 'asc',
    })
    return entries
      .filter((entry) => entry.isDir)
      .map((entry) => ({
        name: entry.name,
        uri: `${SYSTEM_EXAMPLE_SKILLS_ROOT}/${entry.name}`,
        description: '',
      }))
  } catch {
    return []
  }
}

export async function fetchCompileSkills(
  signal?: AbortSignal,
): Promise<CompileSkill[]> {
  const [installed, builtIn] = await Promise.all([
    fetchInstalledSkills(signal),
    fetchSystemExampleSkills(),
  ])
  const seen = new Set(installed.map((skill) => skill.uri))
  return [...installed, ...builtIn.filter((skill) => !seen.has(skill.uri))]
}

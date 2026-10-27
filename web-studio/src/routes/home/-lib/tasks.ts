import { isActiveTaskStatus } from '#/routes/tasks/-lib/task-record'
import type { TaskRecord } from '#/routes/tasks/-lib/task-record'
import { getTaskDate } from '#/routes/tasks/-lib/task-time'

const DAY_MS = 24 * 60 * 60 * 1000

export type TaskSummary = {
  active: number
  /** Failed tasks created in the last 24 hours. */
  failedToday: number
  /** How many of the newest tasks were checked. */
  checked: number
}

export function summarizeTasks(
  tasks: readonly TaskRecord[],
  nowMs = Date.now(),
): TaskSummary {
  const since = nowMs - DAY_MS
  return {
    active: tasks.filter((task) => isActiveTaskStatus(task.status)).length,
    checked: tasks.length,
    failedToday: tasks.filter((task) => {
      if (task.status !== 'failed') return false
      const created = getTaskDate(task)
      return created !== undefined && created.getTime() >= since
    }).length,
  }
}

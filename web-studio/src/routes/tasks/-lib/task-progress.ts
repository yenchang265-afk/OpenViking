import { normalizeTaskStatus } from './task-record'
import type { TaskRecord } from './task-record'

// Stages the backend reports for add_resource, in order (see
// openviking/utils/resource_processor.py and resource_service.py).
// processing_queue covers semantic + embedding work and runs longest; it
// fills the rest of the bar from the server's meta.work_progress counts.
const STAGE_PCT = new Map<string, number>([
  ['queued', 5],
  ['fetching', 15],
  ['parsing', 30],
  ['target_resolve', 45],
  ['processing_queue', 50],
])

const UNKNOWN_STAGE_PCT = 45
const QUEUE_PROGRESS_STAGE = 'processing_queue'
const QUEUE_PROGRESS_MAX_PCT = 99
const PROGRESS_QUEUES = ['Semantic', 'Embedding']

function getWorkRatio(meta: TaskRecord['meta']): number | null {
  const workProgress = meta?.work_progress
  if (!workProgress || typeof workProgress !== 'object') return null
  let done = 0
  let total = 0
  for (const queue of PROGRESS_QUEUES) {
    const counts = (workProgress as Record<string, unknown>)[queue]
    if (!counts || typeof counts !== 'object') continue
    const { done: d, total: t } = counts as { done?: unknown; total?: unknown }
    if (typeof d !== 'number' || typeof t !== 'number' || t <= 0) continue
    done += Math.min(d, t)
    total += t
  }
  return total > 0 ? done / total : null
}

export function getTaskProgressPct(task: TaskRecord): number {
  const status = normalizeTaskStatus(task.status)
  if (status === 'completed') return 100
  if (status === 'failed') return 35
  if (status === 'pending') return 0

  // Extract real queue metrics from task.result
  const resObj =
    task.result && typeof task.result === 'object'
      ? (task.result as Record<string, any>)
      : {}
  const qStatus = resObj.queue_status
  const embeddingProcessed = qStatus?.Embedding?.processed
  const semanticProcessed = qStatus?.Semantic?.processed

  if (typeof embeddingProcessed === 'number') {
    const totalEmbedding = 20
    const embedRatio = Math.min(1, embeddingProcessed / totalEmbedding)
    // Step 1 (20%) + Step 2 (30%) + Step 3 (50% * embedRatio)
    return Math.round(20 + 30 + 50 * embedRatio)
  }

  if (typeof semanticProcessed === 'number') {
    const totalSemantic = 5
    const semRatio = Math.min(1, semanticProcessed / totalSemantic)
    // Step 1 (20%) + Step 2 (30% * semRatio)
    return Math.round(20 + 30 * semRatio)
  }

  const stage = task.stage?.toLowerCase() ?? ''
  const stagePct = STAGE_PCT.get(stage) ?? UNKNOWN_STAGE_PCT
  if (stage !== QUEUE_PROGRESS_STAGE) return stagePct

  const ratio = getWorkRatio(task.meta)
  if (ratio === null) return stagePct
  return Math.round(
    stagePct + (QUEUE_PROGRESS_MAX_PCT - stagePct) * ratio,
  )
}

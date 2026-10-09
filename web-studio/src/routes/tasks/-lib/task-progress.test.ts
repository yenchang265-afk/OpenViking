import { describe, expect, it } from 'vitest'

import { getTaskProgressPct } from './task-progress'
import type { TaskRecord } from './task-record'

function running(stage: string | null, result?: unknown): TaskRecord {
  return { task_type: 'add_resource', status: 'running', stage, result }
}

describe('getTaskProgressPct', () => {
  it('maps lifecycle statuses', () => {
    expect(getTaskProgressPct({ status: 'pending' })).toBe(0)
    expect(getTaskProgressPct({ status: 'completed' })).toBe(100)
  })

  it('advances through the stages add_resource actually reports', () => {
    const stages = [
      'queued',
      'fetching',
      'parsing',
      'target_resolve',
      'processing_queue',
    ]
    const pcts = stages.map((stage) => getTaskProgressPct(running(stage)))

    for (let i = 1; i < pcts.length; i++) {
      expect(pcts[i]).toBeGreaterThan(pcts[i - 1])
    }
    expect(pcts[0]).toBeGreaterThan(0)
    expect(pcts[pcts.length - 1]).toBeLessThan(100)
  })

  it('is case-insensitive on stage names', () => {
    expect(getTaskProgressPct(running('PARSING'))).toBe(
      getTaskProgressPct(running('parsing')),
    )
  })

  it('falls back for stages it does not know', () => {
    expect(getTaskProgressPct(running(null))).toBe(45)
    expect(getTaskProgressPct(running('connector:running'))).toBe(45)
  })

  it('fills processing_queue from live work_progress counts', () => {
    const at = (work_progress: unknown) =>
      getTaskProgressPct({
        ...running('processing_queue'),
        meta: { work_progress },
      })

    const start = at({ Semantic: { done: 0, total: 4 } })
    const half = at({
      Semantic: { done: 4, total: 4 },
      Embedding: { done: 0, total: 4 },
    })
    const nearlyDone = at({
      Semantic: { done: 4, total: 4 },
      Embedding: { done: 3, total: 4 },
    })

    expect(start).toBe(getTaskProgressPct(running('processing_queue')))
    expect(half).toBeGreaterThan(start)
    expect(nearlyDone).toBeGreaterThan(half)
    expect(at({ Semantic: { done: 9, total: 9 } })).toBe(99)
  })

  it('ignores malformed or irrelevant work_progress', () => {
    const base = getTaskProgressPct(running('processing_queue'))
    const at = (work_progress: unknown) =>
      getTaskProgressPct({
        ...running('processing_queue'),
        meta: { work_progress },
      })

    expect(at(null)).toBe(base)
    expect(at({ Semantic: { done: 'x', total: 3 } })).toBe(base)
    expect(at({ AddResource: { done: 1, total: 1 } })).toBe(base)
    expect(at({ Semantic: { done: 1, total: 0 } })).toBe(base)
  })

  it('uses work_progress only during processing_queue', () => {
    expect(
      getTaskProgressPct({
        ...running('parsing'),
        meta: { work_progress: { Semantic: { done: 1, total: 1 } } },
      }),
    ).toBe(getTaskProgressPct(running('parsing')))
  })

  it('prefers queue counts when the result carries them', () => {
    expect(
      getTaskProgressPct(
        running('processing_queue', {
          queue_status: { Embedding: { processed: 20 } },
        }),
      ),
    ).toBe(100)
  })
})

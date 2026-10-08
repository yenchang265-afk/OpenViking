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

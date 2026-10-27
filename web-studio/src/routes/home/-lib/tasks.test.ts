import { expect, it } from 'vitest'

import { summarizeTasks } from './tasks'

const now = Date.parse('2026-10-27T12:00:00Z')

it('counts active tasks and failures from the last 24 hours', () => {
  const summary = summarizeTasks(
    [
      { status: 'running' },
      { status: 'pending' },
      { status: 'completed' },
      { created_at_iso: '2026-10-27T08:00:00Z', status: 'failed' },
      // Seconds since the epoch, as the server sends `created_at`.
      { created_at: now / 1000 - 60, status: 'failed' },
      { created_at_iso: '2026-10-25T08:00:00Z', status: 'failed' },
      // A failure without a timestamp cannot be placed in the window.
      { status: 'failed' },
    ],
    now,
  )
  expect(summary).toEqual({ active: 2, checked: 7, failedToday: 2 })
})

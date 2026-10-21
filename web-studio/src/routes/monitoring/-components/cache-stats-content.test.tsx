// @vitest-environment jsdom

import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { normalizeCacheStats } from '#/lib/cache-stats'
import { CacheStatsContent } from './cache-stats-content'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(cleanup)

describe('CacheStatsContent', () => {
  it('lists hit rate, hits, misses, and bypasses per operation', () => {
    render(
      <CacheStatsContent
        stats={normalizeCacheStats({
          enabled: true,
          hits: 4,
          misses: 1,
          operations: [
            { operation: 'read', hits: 3, misses: 1, bypasses: 7 },
            { operation: 'tree', hits: 1, misses: 0, bypasses: 0 },
          ],
          kinds: [{ kind: 'file', hits: 3, misses: 1 }],
        })}
      />,
    )

    const readRow = screen
      .getByText('cache.operations.read')
      .closest('tr') as HTMLElement
    expect(within(readRow).getByText('75.0%')).toBeTruthy()
    expect(within(readRow).getByText('7')).toBeTruthy()
    const treeRow = screen
      .getByText('cache.operations.tree')
      .closest('tr') as HTMLElement
    expect(within(treeRow).getByText('100%')).toBeTruthy()
    expect(screen.getByText('cache.kinds.file')).toBeTruthy()
    expect(screen.getByText('80.0%')).toBeTruthy()
  })

  it('explains how to enable CacheFS when it is off', () => {
    render(
      <CacheStatsContent stats={normalizeCacheStats({ enabled: false })} />,
    )

    expect(screen.getByText('cache.disabled')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })
})

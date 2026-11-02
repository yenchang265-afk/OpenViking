import { describe, expect, it } from 'vitest'

import { formatBytes, formatHitRate, normalizeCacheStats } from './cache-stats'

describe('normalizeCacheStats', () => {
  it('orders known operations and derives hit rates from counts', () => {
    const stats = normalizeCacheStats({
      enabled: true,
      hits: 3,
      misses: 1,
      operations: [
        { operation: 'grep', hits: 0, misses: 0, bypasses: 2 },
        { operation: 'custom', hits: 1, misses: 1 },
        { operation: 'read', hits: 3, misses: 1, hit_rate: 'bad' },
        { hits: 9 },
      ],
      kinds: [{ kind: 'file', hits: 3, misses: 1 }],
    })

    expect(stats.enabled).toBe(true)
    expect(stats.hitRate).toBe(0.75)
    expect(stats.lookups).toBe(4)
    expect(stats.operations.map((item) => item.operation)).toEqual([
      'read',
      'grep',
      'custom',
    ])
    expect(stats.operations[0].hitRate).toBe(0.75)
    expect(stats.operations[1]).toMatchObject({ bypasses: 2, hitRate: null })
    expect(stats.kinds).toEqual([
      { hitRate: 0.75, hits: 3, kind: 'file', misses: 1 },
    ])
  })

  it('treats a disabled or malformed payload as disabled with zero counts', () => {
    const stats = normalizeCacheStats({ enabled: false, hits: -1 })

    expect(stats.enabled).toBe(false)
    expect(stats.hits).toBe(0)
    expect(stats.hitRate).toBeNull()
    expect(stats.operations).toEqual([])
    expect(normalizeCacheStats(null).enabled).toBe(false)
  })
})

describe('cache stat formatting', () => {
  it('formats hit rates and byte counts', () => {
    expect(formatHitRate(null)).toBe('—')
    expect(formatHitRate(1, 'en')).toBe('100%')
    expect(formatHitRate(0.8342, 'en')).toBe('83.4%')
    expect(formatBytes(512, 'en')).toBe('512 B')
    expect(formatBytes(1536, 'en')).toBe('1.5 KiB')
  })
})

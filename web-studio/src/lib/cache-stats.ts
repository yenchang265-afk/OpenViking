import { client } from '#/gen/ov-client/client.gen'
import { getOvResult } from '#/lib/ov-client'

import type {
  ConsoleCacheOperation,
  ConsoleCacheStatsResult,
} from '@ov-server/api/v1/console'

export const CACHE_STATS_REFETCH_MS = 30_000

/** Display order for known operations; unknown ones follow as reported. */
export const CACHE_OPERATIONS = ['read', 'read_dir', 'tree', 'grep'] as const

export type CacheLookupStats = {
  hitRate: number | null
  hits: number
  misses: number
}

export type CacheOperationStats = CacheLookupStats & {
  bypasses: number
  operation: ConsoleCacheOperation
}

export type CacheKindStats = CacheLookupStats & {
  kind: string
}

export type CacheStats = CacheLookupStats & {
  backendSaved: number
  bypasses: number
  bytesFromBackend: number
  bytesFromCache: number
  enabled: boolean
  errors: number
  kinds: CacheKindStats[]
  lookups: number
  operations: CacheOperationStats[]
}

export function fetchCacheStats(): Promise<ConsoleCacheStatsResult> {
  // Not in the generated SDK yet; uses the same configured client.
  return getOvResult<ConsoleCacheStatsResult>(
    client.get({ responseType: 'json', url: '/api/v1/console/cache' }),
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function asCount(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : 0
}

function lookupStats(record: Record<string, unknown>): CacheLookupStats {
  const hits = asCount(record.hits)
  const misses = asCount(record.misses)
  // Derive the rate from counts so a missing or malformed `hit_rate` is harmless.
  return {
    hitRate: hits + misses > 0 ? hits / (hits + misses) : null,
    hits,
    misses,
  }
}

/** Normalize the `/console/cache` payload into display-ready counts. */
export function normalizeCacheStats(data: unknown): CacheStats {
  const record = asRecord(data)
  const overall = lookupStats(record)
  const operations = (Array.isArray(record.operations) ? record.operations : [])
    .map(asRecord)
    .filter((item) => typeof item.operation === 'string' && item.operation)
    .map((item) => ({
      ...lookupStats(item),
      bypasses: asCount(item.bypasses),
      operation: item.operation as string,
    }))
  const rank = (operation: string) => {
    const index = (CACHE_OPERATIONS as readonly string[]).indexOf(operation)
    return index === -1 ? CACHE_OPERATIONS.length : index
  }
  return {
    ...overall,
    backendSaved: asCount(record.backend_saved),
    bypasses: asCount(record.bypasses),
    bytesFromBackend: asCount(record.bytes_from_backend),
    bytesFromCache: asCount(record.bytes_from_cache),
    enabled: record.enabled === true,
    errors: asCount(record.errors),
    kinds: (Array.isArray(record.kinds) ? record.kinds : [])
      .map(asRecord)
      .filter((item) => typeof item.kind === 'string' && item.kind)
      .map((item) => ({ ...lookupStats(item), kind: item.kind as string })),
    lookups: overall.hits + overall.misses,
    operations: operations.sort(
      (a, b) => rank(a.operation) - rank(b.operation),
    ),
  }
}

/** Format a 0..1 ratio as a percentage, or an em dash when there is no data. */
export function formatHitRate(rate: number | null, locale?: string): string {
  if (rate === null) return '—'
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 1,
    minimumFractionDigits: rate > 0 && rate < 1 ? 1 : 0,
    style: 'percent',
  }).format(rate)
}

/** Format a byte count with binary units. */
export function formatBytes(bytes: number, locale?: string): string {
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 ? 0 : 1
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value)} ${units[unit]}`
}

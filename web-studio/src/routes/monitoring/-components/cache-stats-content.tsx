import { useTranslation } from 'react-i18next'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '#/components/ui/table'
import { formatBytes, formatHitRate } from '#/lib/cache-stats'
import type { CacheLookupStats, CacheStats } from '#/lib/cache-stats'

function HitRateBar({ rate }: { rate: number | null }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-emerald-500"
          style={{ width: `${Math.round((rate ?? 0) * 100)}%` }}
        />
      </div>
      <span className="tabular-nums">{formatHitRate(rate)}</span>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/20 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function LookupCells({ stats }: { stats: CacheLookupStats }) {
  return (
    <>
      <TableCell>
        <HitRateBar rate={stats.hitRate} />
      </TableCell>
      <TableCell className="text-right font-mono text-xs">
        {stats.hits.toLocaleString()}
      </TableCell>
      <TableCell className="text-right font-mono text-xs">
        {stats.misses.toLocaleString()}
      </TableCell>
    </>
  )
}

/** CacheFS hit rates since server start, overall and per operation. */
export function CacheStatsContent({ stats }: { stats: CacheStats }) {
  const { t } = useTranslation('monitoringPage')

  if (!stats.enabled) {
    return (
      <p className="text-sm text-muted-foreground">{t('cache.disabled')}</p>
    )
  }

  const label = (group: 'kinds' | 'operations', name: string) =>
    t(`cache.${group}.${name}`, { defaultValue: name })

  return (
    <div className="grid gap-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t('cache.overall')} value={formatHitRate(stats.hitRate)} />
        <Stat
          label={t('cache.lookups')}
          value={stats.lookups.toLocaleString()}
        />
        <Stat
          label={t('cache.bytesFromCache')}
          value={formatBytes(stats.bytesFromCache)}
        />
        <Stat
          label={t('cache.bytesFromBackend')}
          value={formatBytes(stats.bytesFromBackend)}
        />
      </div>

      <section className="grid gap-2">
        <h3 className="text-sm font-medium">{t('cache.byOperation')}</h3>
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/20 hover:bg-muted/20">
                <TableHead>{t('cache.operation')}</TableHead>
                <TableHead>{t('cache.hitRate')}</TableHead>
                <TableHead className="text-right">{t('cache.hits')}</TableHead>
                <TableHead className="text-right">
                  {t('cache.misses')}
                </TableHead>
                <TableHead className="text-right">
                  {t('cache.bypasses')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stats.operations.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center text-sm text-muted-foreground"
                  >
                    {t('cache.noLookups')}
                  </TableCell>
                </TableRow>
              ) : (
                stats.operations.map((operation) => (
                  <TableRow key={operation.operation}>
                    <TableCell>
                      <p className="font-medium">
                        {label('operations', operation.operation)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t(`cache.operationHints.${operation.operation}`, {
                          defaultValue: operation.operation,
                        })}
                      </p>
                    </TableCell>
                    <LookupCells stats={operation} />
                    <TableCell className="text-right font-mono text-xs">
                      {operation.bypasses.toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      {stats.kinds.length > 0 ? (
        <section className="grid gap-2">
          <h3 className="text-sm font-medium">{t('cache.byKind')}</h3>
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/20 hover:bg-muted/20">
                  <TableHead>{t('cache.kind')}</TableHead>
                  <TableHead>{t('cache.hitRate')}</TableHead>
                  <TableHead className="text-right">
                    {t('cache.hits')}
                  </TableHead>
                  <TableHead className="text-right">
                    {t('cache.misses')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.kinds.map((kind) => (
                  <TableRow key={kind.kind}>
                    <TableCell className="font-medium">
                      {label('kinds', kind.kind)}
                    </TableCell>
                    <LookupCells stats={kind} />
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      ) : null}

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>
          {t('cache.backendSaved')}: {stats.backendSaved.toLocaleString()}
        </span>
        <span>
          {t('cache.errors')}: {stats.errors.toLocaleString()}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{t('cache.sinceStart')}</p>
    </div>
  )
}

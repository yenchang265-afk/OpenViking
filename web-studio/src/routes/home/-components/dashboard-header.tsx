import { RefreshCwIcon } from 'lucide-react'

import { Button } from '#/components/ui/button'
import { formatDateTime } from '#/i18n/format'
import { cn } from '#/lib/utils'

import type { HomeT } from '../-types/dashboard'

export function DashboardHeader({
  disabled = false,
  isFetching,
  onRefresh,
  t,
  updatedAt,
}: {
  disabled?: boolean
  isFetching: boolean
  onRefresh: () => void
  t: HomeT
  /** Epoch ms of the latest successful load; 0 when nothing has loaded. */
  updatedAt: number
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-3">
      {updatedAt ? (
        <span className="text-xs tabular-nums text-muted-foreground">
          {t('updatedAt', {
            time: formatDateTime(new Date(updatedAt), {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            }),
          })}
        </span>
      ) : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled || isFetching}
        onClick={onRefresh}
      >
        <RefreshCwIcon className={cn('size-4', isFetching && 'animate-spin')} />
        {t('refresh')}
      </Button>
    </div>
  )
}

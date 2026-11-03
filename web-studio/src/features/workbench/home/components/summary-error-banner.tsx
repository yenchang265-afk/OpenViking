import { AlertCircleIcon, RefreshCwIcon } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '#/shared/ui/alert'
import { Button } from '#/shared/ui/button'
import { normalizeOvClientError } from '#/shared/api/ov-client'
import { cn } from '#/shared/lib/utils'

import type { HomeT } from '#/features/workbench/home/types/dashboard'

/** One place to explain why the summary cards are empty, with a retry. */
export function SummaryErrorBanner({
  error,
  isRetrying,
  onRetry,
  t,
}: {
  error: unknown
  isRetrying: boolean
  onRetry: () => void
  t: HomeT
}) {
  const { code, message, requestId, statusCode } = normalizeOvClientError(error)
  const meta = [
    statusCode ? t('summaryError.status', { status: statusCode }) : null,
    code,
  ].filter(Boolean)

  return (
    <Alert variant="destructive">
      <AlertCircleIcon />
      <AlertTitle>{t('summaryError.title')}</AlertTitle>
      <AlertDescription className="grid gap-1">
        <p className="break-words">{message}</p>
        {meta.length || requestId ? (
          <p className="text-xs text-muted-foreground">
            {meta.join(' · ')}
            {requestId ? (
              <>
                {meta.length ? ' · ' : null}
                {t('summaryError.requestId')}{' '}
                <code className="select-all font-mono">{requestId}</code>
              </>
            ) : null}
          </p>
        ) : null}
        <div className="mt-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isRetrying}
            onClick={onRetry}
          >
            <RefreshCwIcon
              className={cn('size-4', isRetrying && 'animate-spin')}
            />
            {t('summaryError.retry')}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  )
}

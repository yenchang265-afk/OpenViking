import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '#/components/ui/alert-dialog'
import { RadioGroup } from '#/components/ui/radio-group'
import { ResourceOptionRadioCard } from '#/routes/resources/-components/resource-option-radio-card'
import { reindexResource } from '#/routes/resources/-lib/api'
import type { ReindexMode } from '#/routes/resources/-lib/api'
import type { VikingFsEntry } from '#/routes/resources/-types/viking-fm'

import { getErrorMessage } from '../-lib/utils'

const REINDEX_MODES: ReindexMode[] = ['vectors_only', 'semantic_and_vectors']

export function ReindexDialog({
  entry,
  onOpenChange,
  open,
}: {
  entry: Pick<VikingFsEntry, 'isDir' | 'uri'>
  onOpenChange: (open: boolean) => void
  open: boolean
}) {
  const { t } = useTranslation('playground')
  const navigate = useNavigate()
  const [mode, setMode] = useState<ReindexMode>('vectors_only')
  const mutation = useMutation({
    mutationFn: () => reindexResource(entry.uri, mode),
  })
  const { reset } = mutation

  useEffect(() => {
    if (open) reset()
  }, [open, reset])

  return (
    <AlertDialog
      open={open}
      onOpenChange={(value) => {
        if (!mutation.isPending) onOpenChange(value)
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('reindex.title')}</AlertDialogTitle>
          <AlertDialogDescription className="break-all">
            {t(
              entry.isDir
                ? 'reindex.directoryDescription'
                : 'reindex.fileDescription',
              { uri: entry.uri },
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <RadioGroup
          aria-label={t('reindex.modeLabel')}
          value={mode}
          onValueChange={(value) =>
            setMode(
              value === 'semantic_and_vectors'
                ? 'semantic_and_vectors'
                : 'vectors_only',
            )
          }
          disabled={mutation.isPending}
        >
          {REINDEX_MODES.map((value) => (
            <ResourceOptionRadioCard
              key={value}
              value={value}
              title={t(`reindex.modes.${value}.title`)}
              description={t(`reindex.modes.${value}.description`)}
            />
          ))}
        </RadioGroup>
        {mutation.error ? (
          <p role="alert" className="text-sm text-destructive">
            {t('reindex.failed', { error: getErrorMessage(mutation.error) })}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>
            {t('reindex.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            disabled={mutation.isPending}
            onClick={async (event) => {
              event.preventDefault()
              if (mutation.isPending) return
              try {
                await mutation.mutateAsync()
                onOpenChange(false)
                toast.success(t('reindex.started'), {
                  action: {
                    label: t('reindex.viewTasks'),
                    onClick: () => void navigate({ to: '/tasks' }),
                  },
                })
              } catch {
                // Keep the dialog and error visible, e.g. when a reindex of
                // the same URI is already running.
              }
            }}
          >
            {t(mutation.isPending ? 'reindex.starting' : 'reindex.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

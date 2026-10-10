import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Trash2Icon } from 'lucide-react'

import { Button } from '#/components/ui/button'
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
import { removeResource } from '#/routes/resources/-lib/api'
import type { VikingFsEntry } from '#/routes/resources/-types/viking-fm'

import { pruneNestedEntries } from '../-lib/tree-actions'
import { getErrorMessage } from '../-lib/utils'

type DeletableEntry = Pick<VikingFsEntry, 'isDir' | 'uri'>

type BatchDeleteResult = {
  deleted: DeletableEntry[]
  failed: { entry: DeletableEntry; error: unknown }[]
}

/**
 * Deletes one at a time so a failure stops nothing else and every outcome is
 * known. Nested entries are skipped: their selected folder removes them.
 */
async function deleteEntries(
  entries: readonly DeletableEntry[],
): Promise<BatchDeleteResult> {
  const deleted: DeletableEntry[] = []
  const failed: BatchDeleteResult['failed'] = []
  for (const entry of pruneNestedEntries(entries)) {
    try {
      await removeResource(entry.uri, { recursive: entry.isDir })
      deleted.push(entry)
    } catch (error) {
      failed.push({ entry, error })
    }
  }
  return { deleted, failed }
}

export function DeleteResource({
  entry,
  onDeleted,
}: {
  entry: DeletableEntry
  onDeleted: (entry: DeletableEntry) => void
}) {
  const { t } = useTranslation('playground')
  const [open, setOpen] = useState(false)
  const label = t('deleteResource.label')

  return (
    <>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        className="text-muted-foreground hover:text-destructive"
        title={label}
        aria-label={label}
        onClick={() => setOpen(true)}
      >
        <Trash2Icon className="size-4" />
      </Button>
      <DeleteResourceDialog
        entry={entry}
        open={open}
        onOpenChange={setOpen}
        onDeleted={onDeleted}
      />
    </>
  )
}

export function DeleteResourceDialog({
  entry,
  onDeleted,
  onOpenChange,
  open,
}: {
  entry: DeletableEntry
  onDeleted: (entry: DeletableEntry) => void
  onOpenChange: (open: boolean) => void
  open: boolean
}) {
  const { t } = useTranslation('playground')
  const mutation = useMutation({
    mutationFn: () => removeResource(entry.uri, { recursive: entry.isDir }),
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
          <AlertDialogTitle>{t('deleteResource.title')}</AlertDialogTitle>
          <AlertDialogDescription className="break-all">
            {t(
              entry.isDir
                ? 'deleteResource.directoryDescription'
                : 'deleteResource.fileDescription',
              { uri: entry.uri },
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {mutation.error ? (
          <p role="alert" className="text-sm text-destructive">
            {t('deleteResource.failed', {
              error: getErrorMessage(mutation.error),
            })}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>
            {t('deleteResource.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-white hover:bg-destructive/90"
            disabled={mutation.isPending}
            onClick={async (event) => {
              event.preventDefault()
              if (mutation.isPending) return
              try {
                await mutation.mutateAsync()
                onOpenChange(false)
                onDeleted(entry)
              } catch {
                // Keep the dialog and error visible so the user can retry.
              }
            }}
          >
            {t(
              mutation.isPending
                ? 'deleteResource.deleting'
                : 'deleteResource.confirm',
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/**
 * Confirms and deletes several entries. Successful deletions are reported
 * even when others fail; the dialog then stays open on the failures so the
 * caller can shrink `entries` to them and the user can retry.
 */
export function BatchDeleteResourceDialog({
  entries,
  onDeleted,
  onOpenChange,
  open,
}: {
  entries: readonly DeletableEntry[]
  onDeleted: (deleted: DeletableEntry[]) => void
  onOpenChange: (open: boolean) => void
  open: boolean
}) {
  const { t } = useTranslation('playground')
  const mutation = useMutation({ mutationFn: deleteEntries })
  const { reset } = mutation
  const failed = mutation.data?.failed ?? []

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
          <AlertDialogTitle>
            {t('deleteResource.batchTitle', { count: entries.length })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t('deleteResource.batchDescription')}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ul
          aria-label={t('deleteResource.batchListLabel')}
          className="max-h-40 overflow-y-auto rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs"
        >
          {entries.map((entry) => (
            <li key={entry.uri} className="break-all leading-5">
              {entry.uri}
            </li>
          ))}
        </ul>
        {failed.length > 0 ? (
          <p role="alert" className="text-sm text-destructive">
            {t('deleteResource.batchFailed', {
              count: failed.length,
              error: getErrorMessage(failed[0].error),
            })}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>
            {t('deleteResource.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-white hover:bg-destructive/90"
            disabled={mutation.isPending || entries.length === 0}
            onClick={async (event) => {
              event.preventDefault()
              if (mutation.isPending) return
              const result = await mutation.mutateAsync(entries)
              if (result.failed.length === 0) onOpenChange(false)
              if (result.deleted.length > 0) onDeleted(result.deleted)
            }}
          >
            {t(
              mutation.isPending
                ? 'deleteResource.deleting'
                : 'deleteResource.confirm',
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

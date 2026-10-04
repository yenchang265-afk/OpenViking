import { useState } from 'react'
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

import { getErrorMessage } from '../-lib/utils'

export function DeleteResource({
  entry,
  onDeleted,
}: {
  entry: Pick<VikingFsEntry, 'isDir' | 'uri'>
  onDeleted: (entry: Pick<VikingFsEntry, 'isDir' | 'uri'>) => void
}) {
  const { t } = useTranslation('playground')
  const [open, setOpen] = useState(false)
  const mutation = useMutation({
    mutationFn: () => removeResource(entry.uri, { recursive: entry.isDir }),
  })
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
        onClick={() => {
          mutation.reset()
          setOpen(true)
        }}
      >
        <Trash2Icon className="size-4" />
      </Button>
      <AlertDialog
        open={open}
        onOpenChange={(value) => {
          if (!mutation.isPending) setOpen(value)
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
                  setOpen(false)
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
    </>
  )
}

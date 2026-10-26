import { useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

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

import { deleteSkill } from '../-lib/delete-skill'
import type { DeletableSkill } from '../-lib/delete-skill'

export function DeleteSkillDialog({
  getErrorMessage,
  onDeleted,
  onOpenChange,
  open,
  skill,
}: {
  getErrorMessage: (error: unknown) => string
  onDeleted: (skill: DeletableSkill) => void
  onOpenChange: (open: boolean) => void
  open: boolean
  skill: DeletableSkill
}) {
  const { t } = useTranslation('skillsPage')
  const mutation = useMutation({ mutationFn: deleteSkill })
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
          <AlertDialogTitle>
            {t('delete.title', { name: skill.name })}
          </AlertDialogTitle>
          <AlertDialogDescription className="break-all">
            {t('delete.description', { uri: skill.uri })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {mutation.error ? (
          <p role="alert" className="text-sm break-all text-destructive">
            {t('delete.failed', { error: getErrorMessage(mutation.error) })}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>
            {t('delete.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-white hover:bg-destructive/90"
            disabled={mutation.isPending}
            onClick={async (event) => {
              event.preventDefault()
              if (mutation.isPending) return
              try {
                await mutation.mutateAsync(skill)
                onOpenChange(false)
                onDeleted(skill)
              } catch {
                // Keep the dialog and error visible so the user can retry.
              }
            }}
          >
            {t(mutation.isPending ? 'delete.deleting' : 'delete.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

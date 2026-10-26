import { useEffect, useId, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { DownloadIcon } from 'lucide-react'
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
import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'
import {
  createDataManagementClient,
  downloadBlob,
  exportOvpack,
} from '#/routes/filesystem/-lib/data-management'

import { deleteSkill, skillTargetUri } from '../-lib/delete-skill'
import type { DeletableSkill } from '../-lib/delete-skill'
import type { SkillScope } from './skill-scope-tabs'

type ScopedSkill = DeletableSkill & { scope: SkillScope }

export function DeleteSkillDialog({
  getErrorMessage,
  onDeleted,
  onOpenChange,
  open,
  skill,
}: {
  getErrorMessage: (error: unknown) => string
  onDeleted: (skill: ScopedSkill) => void
  onOpenChange: (open: boolean) => void
  open: boolean
  skill: ScopedSkill
}) {
  const { t } = useTranslation('skillsPage')
  const confirmId = useId()
  const [typedName, setTypedName] = useState('')
  const exportAbort = useRef<AbortController | null>(null)
  const mutation = useMutation({ mutationFn: deleteSkill })
  const backup = useMutation({
    mutationFn: async () => {
      exportAbort.current?.abort()
      const controller = new AbortController()
      exportAbort.current = controller
      const blob = await exportOvpack(
        createDataManagementClient(),
        skill.uri,
        controller.signal,
      )
      if (!controller.signal.aborted) downloadBlob(blob, skill.uri)
    },
  })
  const { reset } = mutation
  const { reset: resetBackup } = backup
  const busy = mutation.isPending || backup.isPending
  // A shared skill disappears for everyone, so make the user type its name.
  const needsTypedName = skill.scope === 'agent'
  const confirmed = !needsTypedName || typedName.trim() === skill.name

  useEffect(() => {
    if (open) {
      reset()
      resetBackup()
      setTypedName('')
      return
    }
    exportAbort.current?.abort()
  }, [open, reset, resetBackup])

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

        <div className="grid gap-2 rounded-lg border bg-muted/30 p-3 text-sm">
          <p className="text-muted-foreground">
            {t('delete.backupHint', { parent: skillTargetUri(skill.uri) })}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => backup.mutate()}
            >
              <DownloadIcon />
              {t(backup.isPending ? 'delete.backingUp' : 'delete.backup')}
            </Button>
            {backup.isSuccess ? (
              <span role="status" className="text-xs text-muted-foreground">
                {t('delete.backedUp')}
              </span>
            ) : null}
          </div>
          {backup.error ? (
            <p role="alert" className="text-xs break-all text-destructive">
              {t('delete.backupFailed', {
                error: getErrorMessage(backup.error),
              })}
            </p>
          ) : null}
        </div>

        {needsTypedName ? (
          <div className="grid gap-2">
            <Label htmlFor={confirmId}>
              {t('delete.typeName', { name: skill.name })}
            </Label>
            <Input
              id={confirmId}
              value={typedName}
              autoComplete="off"
              spellCheck={false}
              disabled={mutation.isPending}
              onChange={(event) => setTypedName(event.target.value)}
            />
          </div>
        ) : null}

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
            disabled={busy || !confirmed}
            onClick={async (event) => {
              event.preventDefault()
              if (busy || !confirmed) return
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

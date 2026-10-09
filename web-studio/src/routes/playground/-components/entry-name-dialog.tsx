import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Button } from '#/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '#/components/ui/dialog'
import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'

import { getErrorMessage } from '../-lib/utils'
import {
  CREATABLE_FILE_EXTENSIONS,
  validateEntryName,
} from '../-lib/tree-actions'
import type { EntryNameMode } from '../-lib/tree-actions'

const EXTENSION_LIST = CREATABLE_FILE_EXTENSIONS.join(' ')

export function EntryNameDialog({
  description,
  initialName = '',
  mode,
  onOpenChange,
  onSubmit,
  open,
  selectStem = false,
}: {
  description: string
  initialName?: string
  mode: EntryNameMode
  onOpenChange: (open: boolean) => void
  /** Resolves once the entry exists; rejects to keep the dialog open. */
  onSubmit: (name: string) => Promise<void>
  open: boolean
  /** Pre-select the name without its extension, like desktop explorers. */
  selectStem?: boolean
}) {
  const { t } = useTranslation('playground')
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [name, setName] = useState(initialName)
  const [touched, setTouched] = useState(false)
  const mutation = useMutation({ mutationFn: onSubmit })
  const { reset } = mutation

  useEffect(() => {
    if (!open) return
    setName(initialName)
    setTouched(false)
    reset()
  }, [initialName, open, reset])

  const validationError = validateEntryName(name, mode)
  const visibleError = touched ? validationError : null
  const isRename = mode === 'rename'
  const title = t(
    isRename
      ? 'explorer.nameDialog.renameTitle'
      : mode === 'file'
        ? 'explorer.nameDialog.newFileTitle'
        : 'explorer.nameDialog.newFolderTitle',
  )
  const submitLabel = isRename
    ? t(
        mutation.isPending
          ? 'explorer.nameDialog.renaming'
          : 'explorer.nameDialog.rename',
      )
    : t(
        mutation.isPending
          ? 'explorer.nameDialog.creating'
          : 'explorer.nameDialog.create',
      )

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setTouched(true)
    if (validationError || mutation.isPending) return
    try {
      await mutation.mutateAsync(name.trim())
      onOpenChange(false)
    } catch {
      // Keep the dialog and error visible so the user can fix the name.
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!mutation.isPending) onOpenChange(value)
      }}
    >
      <DialogContent
        initialFocus={inputRef}
        className="sm:max-w-sm"
        showCloseButton={false}
      >
        <form className="grid gap-4" noValidate onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription className="break-all font-mono text-xs">
              {description}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor={inputId}>
              {t('explorer.nameDialog.nameLabel')}
            </Label>
            <Input
              ref={inputRef}
              id={inputId}
              value={name}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={visibleError ? true : undefined}
              aria-describedby={`${inputId}-hint`}
              disabled={mutation.isPending}
              placeholder={
                mode === 'file'
                  ? t('explorer.nameDialog.filePlaceholder')
                  : undefined
              }
              onChange={(event) => setName(event.target.value)}
              onFocus={(event) => {
                if (selectStem) selectNameStem(event.currentTarget)
              }}
            />
            <p
              id={`${inputId}-hint`}
              role={visibleError ? 'alert' : undefined}
              className={
                visibleError
                  ? 'text-xs text-destructive'
                  : 'text-xs text-muted-foreground'
              }
            >
              {visibleError
                ? t(`explorer.nameDialog.errors.${visibleError}`, {
                    extensions: EXTENSION_LIST,
                  })
                : mode === 'file'
                  ? t('explorer.nameDialog.fileHint', {
                      extensions: EXTENSION_LIST,
                    })
                  : null}
            </p>
          </div>
          {mutation.error ? (
            <p role="alert" className="text-sm break-all text-destructive">
              {t('explorer.nameDialog.failed', {
                error: getErrorMessage(mutation.error),
              })}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => onOpenChange(false)}
            >
              {t('explorer.nameDialog.cancel')}
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function selectNameStem(input: HTMLInputElement) {
  const dot = input.value.lastIndexOf('.')
  input.setSelectionRange(0, dot > 0 ? dot : input.value.length)
}

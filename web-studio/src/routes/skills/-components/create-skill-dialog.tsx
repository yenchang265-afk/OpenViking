import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { TriangleAlertIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Alert, AlertDescription, AlertTitle } from '#/components/ui/alert'
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
import { RadioGroup } from '#/components/ui/radio-group'
import { Textarea } from '#/components/ui/textarea'
import { ResourceOptionRadioCard } from '#/routes/resources/-components/resource-option-radio-card'

import {
  MAX_SKILL_DESCRIPTION_LENGTH,
  MAX_SKILL_NAME_LENGTH,
  SKILL_TARGET_URIS,
  createSkill,
  validateSkillDescription,
  validateSkillName,
} from '../-lib/create-skill'
import type { SkillDraft } from '../-lib/create-skill'
import type { SkillScope } from './skill-scope-tabs'

const SKILL_SCOPES: SkillScope[] = ['user', 'agent']

export function CreateSkillDialog({
  existingSkills,
  getErrorMessage,
  initialScope,
  onCreated,
  onOpenChange,
  open,
}: {
  existingSkills: { name: string; scope: SkillScope }[]
  getErrorMessage: (error: unknown) => string
  initialScope: SkillScope
  onCreated: (draft: SkillDraft, replaced: boolean) => void
  onOpenChange: (open: boolean) => void
  open: boolean
}) {
  const { t } = useTranslation('skillsPage')
  const formId = useId()
  const nameRef = useRef<HTMLInputElement>(null)
  const [scope, setScope] = useState<SkillScope>(initialScope)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [body, setBody] = useState('')
  const [touched, setTouched] = useState(false)
  // Set once the user has been told the name is taken and pressed submit again.
  const [confirmingReplace, setConfirmingReplace] = useState(false)
  const mutation = useMutation({ mutationFn: createSkill })
  const { reset } = mutation

  useEffect(() => {
    if (!open) return
    setScope(initialScope)
    setName('')
    setDescription('')
    setBody('')
    setTouched(false)
    setConfirmingReplace(false)
    reset()
  }, [initialScope, open, reset])

  const existingNames = useMemo(
    () =>
      new Set(
        existingSkills
          .filter((skill) => skill.scope === scope)
          .map((skill) => skill.name),
      ),
    [existingSkills, scope],
  )
  const nameError = validateSkillName(name)
  // The server overwrites a same-named skill's SKILL.md, so ask first.
  const replacing = !nameError && existingNames.has(name.trim())
  const descriptionError = validateSkillDescription(description)
  const visibleNameError = touched ? nameError : null
  const visibleDescriptionError = touched ? descriptionError : null

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setTouched(true)
    if (nameError || descriptionError || mutation.isPending) return
    if (replacing && !confirmingReplace) {
      setConfirmingReplace(true)
      return
    }
    const draft: SkillDraft = {
      body,
      description: description.trim(),
      name: name.trim(),
      scope,
    }
    try {
      await mutation.mutateAsync(draft)
      onCreated(draft, replacing)
      onOpenChange(false)
    } catch {
      // Keep the dialog and its contents so the user can fix and retry.
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!mutation.isPending) onOpenChange(value)
      }}
    >
      <DialogContent initialFocus={nameRef} className="sm:max-w-2xl">
        <form className="grid gap-5" noValidate onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t('create.title')}</DialogTitle>
            <DialogDescription>{t('create.description')}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-2">
            <Label>{t('create.scopeLabel')}</Label>
            <RadioGroup
              aria-label={t('create.scopeLabel')}
              value={scope}
              onValueChange={(value) => {
                setScope(value as SkillScope)
                setConfirmingReplace(false)
              }}
              disabled={mutation.isPending}
              className="grid gap-2 sm:grid-cols-2"
            >
              {SKILL_SCOPES.map((option) => (
                <ResourceOptionRadioCard
                  key={option}
                  value={option}
                  title={t(`scopes.${option}`)}
                  description={t(`create.scopeHint.${option}`, {
                    uri: SKILL_TARGET_URIS[option],
                  })}
                  disabled={mutation.isPending}
                />
              ))}
            </RadioGroup>
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`${formId}-name`}>{t('create.nameLabel')}</Label>
            <Input
              ref={nameRef}
              id={`${formId}-name`}
              value={name}
              autoComplete="off"
              spellCheck={false}
              placeholder={t('create.namePlaceholder')}
              aria-invalid={visibleNameError ? true : undefined}
              aria-describedby={`${formId}-name-hint`}
              disabled={mutation.isPending}
              onChange={(event) => {
                setName(event.target.value)
                setConfirmingReplace(false)
              }}
            />
            <p
              id={`${formId}-name-hint`}
              role={visibleNameError ? 'alert' : undefined}
              className={
                visibleNameError
                  ? 'text-xs text-destructive'
                  : replacing
                    ? 'text-xs text-amber-600 dark:text-amber-400'
                    : 'text-xs text-muted-foreground'
              }
            >
              {visibleNameError
                ? t(`create.errors.name.${visibleNameError}`, {
                    max: MAX_SKILL_NAME_LENGTH,
                  })
                : replacing
                  ? t('create.nameExists', { scope: t(`scopes.${scope}`) })
                  : t('create.nameHint', { max: MAX_SKILL_NAME_LENGTH })}
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`${formId}-description`}>
              {t('create.descriptionLabel')}
            </Label>
            <Textarea
              id={`${formId}-description`}
              value={description}
              rows={2}
              placeholder={t('create.descriptionPlaceholder')}
              aria-invalid={visibleDescriptionError ? true : undefined}
              aria-describedby={`${formId}-description-hint`}
              disabled={mutation.isPending}
              onChange={(event) => setDescription(event.target.value)}
            />
            <p
              id={`${formId}-description-hint`}
              role={visibleDescriptionError ? 'alert' : undefined}
              className={
                visibleDescriptionError
                  ? 'text-xs text-destructive'
                  : 'text-xs text-muted-foreground'
              }
            >
              {visibleDescriptionError
                ? t(`create.errors.description.${visibleDescriptionError}`, {
                    max: MAX_SKILL_DESCRIPTION_LENGTH,
                  })
                : t('create.descriptionHint')}
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`${formId}-body`}>
              {t('create.instructionsLabel')}
            </Label>
            <Textarea
              id={`${formId}-body`}
              value={body}
              placeholder={t('create.instructionsPlaceholder')}
              aria-describedby={`${formId}-body-hint`}
              disabled={mutation.isPending}
              className="field-sizing-fixed min-h-56 font-mono text-xs leading-5 md:text-xs"
              onChange={(event) => setBody(event.target.value)}
            />
            <p
              id={`${formId}-body-hint`}
              className="text-xs text-muted-foreground"
            >
              {t('create.instructionsHint')}
            </p>
          </div>

          {confirmingReplace ? (
            <Alert variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>
                {t('create.replace.title', { name: name.trim() })}
              </AlertTitle>
              <AlertDescription>
                {t('create.replace.description', {
                  scope: t(`scopes.${scope}`),
                })}
              </AlertDescription>
            </Alert>
          ) : null}

          {mutation.error ? (
            <p role="alert" className="text-sm break-all text-destructive">
              {t('create.failed', {
                error: getErrorMessage(mutation.error),
              })}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={mutation.isPending}
              onClick={() =>
                confirmingReplace
                  ? setConfirmingReplace(false)
                  : onOpenChange(false)
              }
            >
              {t(confirmingReplace ? 'create.replace.back' : 'create.cancel')}
            </Button>
            {confirmingReplace ? (
              <Button
                type="submit"
                variant="destructive"
                disabled={mutation.isPending}
              >
                {t(
                  mutation.isPending
                    ? 'create.replace.replacing'
                    : 'create.replace.confirm',
                )}
              </Button>
            ) : (
              <Button type="submit" disabled={mutation.isPending}>
                {t(mutation.isPending ? 'create.creating' : 'create.submit')}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

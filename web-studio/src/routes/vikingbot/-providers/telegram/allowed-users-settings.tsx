import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Button } from '#/components/ui/button'
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '#/components/ui/dialog'
import { updateConnectionSettings } from '../../-api'
import { allowedUsers, formatAllowList, parseAllowList } from './allow-list'
import type { Connection } from '../../-api'

export function AllowedUsersSettings({
  connection,
  onSaved,
}: {
  connection: Connection
  onSaved: () => void
}) {
  const { t } = useTranslation('vikingbot')
  const saved = formatAllowList(allowedUsers(connection.settings)).join('\n')
  const [text, setText] = useState(saved)
  const [open, setOpen] = useState(false)
  const allowFrom = parseAllowList(text)
  const mutation = useMutation({
    mutationFn: () =>
      updateConnectionSettings(connection, { allow_from: allowFrom }),
    onSuccess: () => {
      setOpen(false)
      onSaved()
    },
  })
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (mutation.isPending) return
        setText(saved)
        mutation.reset()
        setOpen(value)
      }}
    >
      <DialogTrigger render={<Button variant="ghost" />}>
        {t('telegram.allowedUsers')}
      </DialogTrigger>
      <DialogContent showCloseButton={!mutation.isPending}>
        <DialogHeader>
          <DialogTitle>{t('telegram.allowedUsers')}</DialogTitle>
          <DialogDescription>{connection.bot_name}</DialogDescription>
        </DialogHeader>
        <label className="grid gap-2 text-sm">
          <span>{t('telegram.allowFrom')}</span>
          <textarea
            aria-label={t('telegram.allowFrom')}
            className="min-h-28 rounded-md border bg-background px-3 py-2"
            value={text}
            disabled={mutation.isPending}
            onChange={(event) => setText(event.target.value)}
          />
          <span className="text-xs leading-6 text-muted-foreground">
            {t('telegram.allowFromHint')}
          </span>
        </label>
        {mutation.error && (
          <p role="alert" className="text-sm text-destructive">
            {t('operationFailed')} {mutation.error.message}
          </p>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            disabled={mutation.isPending}
            onClick={() => setOpen(false)}
          >
            {t('telegram.cancel')}
          </Button>
          <Button
            disabled={
              allowFrom.length === 0 || text === saved || mutation.isPending
            }
            onClick={() => mutation.mutate()}
          >
            {t(mutation.isPending ? 'telegram.saving' : 'telegram.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

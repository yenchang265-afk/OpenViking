import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '#/components/ui/dialog'
import { rotateCredentials } from '../../-api'
import type { Connection } from '../../-api'

export function TokenRotation({
  connection,
  onSaved,
}: {
  connection: Connection
  onSaved: () => void
}) {
  const { t } = useTranslation('vikingbot')
  const [token, setToken] = useState('')
  const [open, setOpen] = useState(false)
  const mutation = useMutation({
    mutationFn: () =>
      rotateCredentials(
        connection,
        { token: token.trim() },
        connection.identity_user,
      ),
    onSuccess: () => {
      setToken('')
      setOpen(false)
      onSaved()
    },
  })
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (mutation.isPending) return
        setToken('')
        mutation.reset()
        setOpen(value)
      }}
    >
      <DialogTrigger render={<Button variant="ghost" />}>
        {t('telegram.rotate')}
      </DialogTrigger>
      <DialogContent showCloseButton={!mutation.isPending}>
        <DialogHeader>
          <DialogTitle>{t('telegram.rotate')}</DialogTitle>
          <DialogDescription>{t('telegram.rotateHint')}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (!mutation.isPending && token.trim()) mutation.mutate()
          }}
        >
          <label className="block space-y-1 text-sm">
            <span>{t('telegram.token')}</span>
            <Input
              autoComplete="new-password"
              type="password"
              disabled={mutation.isPending}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          {mutation.error && (
            <p role="alert" className="text-sm text-destructive">
              {t('operationFailed')} {mutation.error.message}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => setOpen(false)}
            >
              {t('telegram.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={!token.trim() || mutation.isPending}
            >
              {t('telegram.saveToken')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

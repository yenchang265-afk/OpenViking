import {
  RuntimeUserSelect,
  useRuntimeUserSelection,
} from '../../-components/runtime-user-select'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ExternalLinkIcon, Loader2Icon } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import { createConnection } from '../../-api'
import { allowedUsers, formatAllowList, parseAllowList } from './allow-list'
import type { Connection } from '../../-api'

export function TelegramSetup({
  connection,
  onChange,
  onClose,
}: {
  connection?: Connection
  onChange: (connection: Connection) => void
  onClose: () => void
}) {
  const { t } = useTranslation('vikingbot')
  const [token, setToken] = useState('')
  const [allowList, setAllowList] = useState('')
  const userSelection = useRuntimeUserSelection(!connection)
  const { selectedUser } = userSelection
  const allowFrom = parseAllowList(allowList)
  const mutation = useMutation({
    mutationFn: () =>
      createConnection({
        type: 'telegram',
        credentials: { token: token.trim() },
        user_id: selectedUser,
        settings: { allow_from: allowFrom },
      }),
    onSuccess: (value) => {
      setToken('')
      onChange(value)
    },
  })
  return (
    <section className="mx-auto w-full min-w-0 max-w-3xl space-y-6 px-6 py-8 sm:px-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">
            {t(connection ? 'telegram.connectedTitle' : 'telegram.setupTitle')}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {t(connection ? 'telegram.connectedHint' : 'telegram.setupHint')}
          </p>
        </div>
        <Button variant="ghost" onClick={onClose}>
          {t('telegram.close')}
        </Button>
      </div>
      {connection ? (
        <ConnectedBot connection={connection} />
      ) : (
        <div className="space-y-6 rounded-xl border p-6 sm:p-8">
          <label className="grid gap-3 text-sm">
            <span>{t('telegram.token')}</span>
            <Input
              type="password"
              value={token}
              placeholder={t('telegram.tokenPlaceholder')}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          <label className="grid gap-3 text-sm">
            <span>{t('telegram.allowFrom')}</span>
            <textarea
              aria-label={t('telegram.allowFrom')}
              className="min-h-20 rounded-md border bg-background px-3 py-2 text-sm"
              value={allowList}
              placeholder={t('telegram.allowFromPlaceholder')}
              onChange={(e) => setAllowList(e.target.value)}
            />
            <span className="text-xs leading-6 text-muted-foreground">
              {t('telegram.allowFromHint')}
            </span>
          </label>
          <RuntimeUserSelect
            selection={userSelection}
            disabled={mutation.isPending}
          />
          <details className="rounded-lg border p-4">
            <summary className="cursor-pointer text-sm font-medium">
              {t('telegram.instructions')}
            </summary>
            <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-7 text-muted-foreground">
              <li>{t('telegram.step1')}</li>
              <li>{t('telegram.step2')}</li>
              <li>{t('telegram.step3')}</li>
              <li>{t('telegram.step4')}</li>
            </ol>
            <a
              className="mt-3 inline-flex items-center gap-2 text-sm text-primary underline"
              href="https://t.me/BotFather"
              target="_blank"
              rel="noreferrer"
            >
              {t('telegram.openBotFather')}
              <ExternalLinkIcon className="size-4" />
            </a>
          </details>
          {mutation.error && (
            <p role="alert" className="text-sm text-destructive">
              {t('operationFailed')} {mutation.error.message}
            </p>
          )}
          <Button
            disabled={
              !token.trim() ||
              allowFrom.length === 0 ||
              !selectedUser ||
              mutation.isPending
            }
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending && (
              <Loader2Icon className="size-4 animate-spin" />
            )}
            {t(mutation.isPending ? 'telegram.connecting' : 'telegram.connect')}
          </Button>
        </div>
      )}
    </section>
  )
}

function ConnectedBot({ connection }: { connection: Connection }) {
  const { t } = useTranslation('vikingbot')
  const username = connection.bot_username
  return (
    <div className="space-y-4 rounded-xl border p-6 text-sm sm:p-8">
      {username && (
        <a
          className="inline-flex items-center gap-2 text-primary underline"
          href={`https://t.me/${encodeURIComponent(username)}`}
          target="_blank"
          rel="noreferrer"
        >
          {t('telegram.openChat', { username })}
          <ExternalLinkIcon className="size-4" />
        </a>
      )}
      <dl className="grid gap-2">
        <dt className="text-muted-foreground">{t('telegram.allowedUsers')}</dt>
        <dd>{formatAllowList(allowedUsers(connection.settings)).join(', ')}</dd>
        <dt className="text-muted-foreground">{t('runtimeUser')}</dt>
        <dd>{connection.identity_user}</dd>
      </dl>
      {connection.status.last_error && (
        <p role="alert" className="text-destructive">
          {connection.status.last_error}
        </p>
      )}
    </div>
  )
}

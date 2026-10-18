import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDownIcon, Loader2Icon } from 'lucide-react'
import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '#/components/ui/card'
import { PLAIN_INPUT_PROPS } from '#/lib/form-input'
import {
  StudioSetupError,
  StudioSetupRequestError,
  studioSetupDestination,
  completeStudioSetup,
  markStudioSetupPending,
  savedSetupConnections,
  verifyStudioSetup,
} from '#/lib/connection/onboarding'
import { isValidConnectionUrl } from '#/lib/connection/profiles'
import type { ConnectionDraft } from '#/hooks/use-app-connection'

const ADVANCED_FIELDS = ['adminApiKey', 'accountId', 'userId'] as const
type SavedConnection = ReturnType<typeof savedSetupConnections>[number]

function normalizedAddress(baseUrl: string): string {
  try {
    return new URL(baseUrl).href.replace(/\/+$/, '')
  } catch {
    return baseUrl
  }
}

function savedOpenSourceConnections(): SavedConnection[] {
  let activeId: string | undefined
  try {
    activeId = JSON.parse(
      localStorage.getItem('ov_console_connection_profiles') || '{}',
    ).activeId as string | undefined
  } catch {
    activeId = undefined
  }
  return savedSetupConnections()
    .filter((profile) => profile.connection.serviceSelection === 'opensource')
    .sort((a, b) => (a.id === activeId ? -1 : b.id === activeId ? 1 : 0))
}

function initialDraft(profile: SavedConnection | undefined): ConnectionDraft {
  if (profile)
    return { ...profile.connection, apiKey: '', adminApiKey: '' }
  return {
    serviceSelection: 'opensource',
    // Served by an OpenViking server under its base path: that server is the
    // natural default. The dev server leaves the address for the user.
    baseUrl: import.meta.env.BASE_URL !== '/' ? window.location.origin : '',
    apiKey: '',
    adminApiKey: '',
    accountId: 'default',
    userId: 'default',
  }
}

function matchingProfileId(
  connection: ConnectionDraft,
  profiles: SavedConnection[],
): string | undefined {
  const address = normalizedAddress(connection.baseUrl)
  return profiles.find(
    (profile) =>
      normalizedAddress(profile.connection.baseUrl) === address &&
      profile.connection.accountId === connection.accountId &&
      profile.connection.userId === connection.userId,
  )?.id
}

export function StudioSetup({
  onComplete,
}: {
  onComplete: (connection: ConnectionDraft) => void
}) {
  const { t } = useTranslation(['onboarding', 'studio', 'settings'])
  const [savedConnections] = useState(savedOpenSourceConnections)
  const [draft, setDraft] = useState<ConnectionDraft>(() =>
    initialDraft(savedConnections.at(0)),
  )
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [verified, setVerified] = useState<ConnectionDraft | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const connectionRevisionRef = useRef(0)
  const abortRef = useRef<AbortController | null>(null)
  const keyInputRef = useRef<HTMLInputElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const validUrl = isValidConnectionUrl(draft.baseUrl)
  useEffect(() => {
    markStudioSetupPending()
    headingRef.current?.focus()
    return () => abortRef.current?.abort()
  }, [])
  function update(next: Partial<ConnectionDraft>) {
    connectionRevisionRef.current += 1
    setDraft((value) => ({ ...value, ...next }))
    setVerified(null)
    setError('')
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
    setError('')
    if (verified) {
      try {
        completeStudioSetup(
          verified,
          t('studio:providers.opensource'),
          matchingProfileId(verified, savedConnections),
        )
        onComplete(verified)
      } catch {
        setError(t('storageError'))
      }
      return
    }
    if (!validUrl) {
      setError(t('studio:profiles.invalidUrl'))
      return
    }
    const controller = new AbortController()
    const connectionRevision = connectionRevisionRef.current
    abortRef.current = controller
    setBusy(true)
    try {
      const result = await verifyStudioSetup(draft, controller.signal)
      if (
        !controller.signal.aborted &&
        connectionRevision === connectionRevisionRef.current
      ) {
        setDraft(result)
        setVerified(result)
      }
    } catch (err) {
      if (controller.signal.aborted) return
      if (err instanceof StudioSetupError && err.code === 'keyRequired')
        keyInputRef.current?.focus()
      setError(
        err instanceof StudioSetupRequestError
          ? `${t(err.stage === 'health' ? 'healthRequestFailed' : 'dataRequestFailed')} ${err.message}`
          : err instanceof StudioSetupError
            ? t(err.code)
            : err instanceof Error
              ? err.message
              : String(err),
      )
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
        setBusy(false)
      }
    }
  }
  return (
    <main className="flex h-svh flex-col items-center overflow-y-auto bg-background px-5 py-6 text-foreground sm:px-8 sm:py-8 lg:pt-[max(2rem,calc((100svh-40rem)/2))]">
      <div className="w-full max-w-5xl shrink-0">
        <div className="mb-6 flex items-center gap-3 lg:mb-8">
          <img
            src={`${import.meta.env.BASE_URL}ov-logo.png`}
            alt=""
            className="size-10 rounded-xl"
          />
          <span className="text-base font-semibold tracking-tight">
            {t('brand')}
          </span>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[1fr_1.15fr] lg:gap-20">
          <header className="lg:pt-5">
            <h1
              ref={headingRef}
              tabIndex={-1}
              className="whitespace-nowrap text-[clamp(1.25rem,3vw,2rem)] leading-tight font-semibold tracking-tight outline-none"
            >
              {t('connectionTitle')}
            </h1>
            <p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground lg:mt-5 lg:leading-7">
              {t('connectionDescription')}
            </p>
          </header>
          <Card className="gap-0 overflow-hidden rounded-2xl border-border/70 bg-card py-0 shadow-sm">
            <CardHeader className="gap-2 border-b border-border/70 px-6 py-4 sm:px-8 sm:py-5">
              <CardTitle className="text-lg font-semibold tracking-tight">
                {t('connection')}
              </CardTitle>
              <CardDescription className="text-sm leading-6">
                {t('connectionHint')}
              </CardDescription>
            </CardHeader>
            <CardContent className="px-6 py-5 sm:px-8">
              <form
                onSubmit={(event) => void submit(event)}
                className="space-y-5"
              >
                <fieldset disabled={busy} className="space-y-4">
                  <div className="grid gap-2">
                    <label
                      htmlFor="setup-url"
                      className="text-sm font-medium"
                    >
                      {t('settings:fields.baseUrl')}
                    </label>
                    <Input
                      id="setup-url"
                      className="h-11 rounded-lg"
                      type="url"
                      value={draft.baseUrl}
                      placeholder="http://127.0.0.1:1933"
                      aria-invalid={Boolean(draft.baseUrl) && !validUrl}
                      aria-describedby="setup-url-help"
                      onChange={(event) =>
                        update({ baseUrl: event.target.value })
                      }
                      {...PLAIN_INPUT_PROPS}
                    />
                    <p
                      id="setup-url-help"
                      className="text-xs text-muted-foreground"
                    >
                      {draft.baseUrl && !validUrl
                        ? t('studio:profiles.invalidUrl')
                        : t('newAddressHint')}
                    </p>
                  </div>
                  <label
                    className="grid gap-2 text-sm font-medium"
                    htmlFor="setup-key"
                  >
                    {t('settings:fields.userApiKey')}
                    <Input
                      ref={keyInputRef}
                      className="h-11 rounded-lg bg-background/60 text-sm"
                      id="setup-key"
                      name="apiKey"
                      type="password"
                      aria-invalid={error === t('keyRequired')}
                      aria-describedby={
                        error === t('keyRequired')
                          ? 'setup-key-error'
                          : undefined
                      }
                      value={draft.apiKey}
                      onChange={(event) =>
                        update({ apiKey: event.target.value })
                      }
                      {...PLAIN_INPUT_PROPS}
                      autoComplete="new-password"
                    />
                  </label>
                  {error === t('keyRequired') ? (
                    <p
                      id="setup-key-error"
                      role="alert"
                      className="text-sm text-destructive"
                    >
                      {error}
                    </p>
                  ) : null}
                  <p className="text-sm text-muted-foreground">
                    {t('keyHelp')}
                  </p>
                  <div>
                    <button
                      type="button"
                      aria-expanded={advancedOpen}
                      aria-controls="setup-advanced-fields"
                      onClick={() => setAdvancedOpen((open) => !open)}
                      className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      <ChevronDownIcon
                        aria-hidden="true"
                        className={`size-3 transition-transform duration-300 motion-reduce:transition-none ${advancedOpen ? 'rotate-180' : ''}`}
                      />
                      {t('advanced')}
                    </button>
                    <div
                      id="setup-advanced-fields"
                      aria-hidden={!advancedOpen}
                      inert={!advancedOpen}
                      className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out motion-reduce:transition-none ${advancedOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}`}
                    >
                      <div className="min-h-0 overflow-hidden">
                        <div className="grid gap-3 pt-3">
                          {ADVANCED_FIELDS.map((key) => (
                            <label
                              className="grid gap-2 text-sm"
                              key={key}
                              htmlFor={`setup-${key}`}
                            >
                              {t(
                                `settings:fields.${key === 'accountId' ? 'account' : key === 'userId' ? 'user' : 'rootApiKey'}`,
                              )}
                              <Input
                                id={`setup-${key}`}
                                className="focus-visible:ring-inset"
                                name={key}
                                type={
                                  key === 'adminApiKey' ? 'password' : 'text'
                                }
                                value={draft[key]}
                                onChange={(event) =>
                                  update({ [key]: event.target.value })
                                }
                                {...PLAIN_INPUT_PROPS}
                                autoComplete={
                                  key === 'adminApiKey'
                                    ? 'new-password'
                                    : 'off'
                                }
                              />
                            </label>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </fieldset>
                {error && error !== t('keyRequired') ? (
                  <p
                    role="alert"
                    className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm leading-6 text-destructive"
                  >
                    {t('verifyFailed')} {error}
                  </p>
                ) : null}
                {verified ? (
                  <p
                    role="status"
                    className="rounded-lg border border-emerald-600/20 bg-emerald-600/5 p-3 text-sm leading-6 text-emerald-700 dark:text-emerald-400"
                  >
                    {t(
                      studioSetupDestination(verified) === '/users'
                        ? 'verifiedManagement'
                        : 'verified',
                    )}
                    {verified.accountId && verified.userId
                      ? ` ${verified.accountId} / ${verified.userId}`
                      : null}
                  </p>
                ) : null}
                <div className="border-t border-border/70 pt-5">
                  <Button
                    type="submit"
                    className="min-h-11 w-full rounded-lg"
                    disabled={busy || !validUrl}
                  >
                    {busy ? (
                      <Loader2Icon className="size-4 animate-spin" />
                    ) : null}
                    {t(busy ? 'verifying' : verified ? 'enter' : 'verify')}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  )
}

import { useAppConnection } from '#/features/connection/hooks/use-app-connection'
import { useStudioService } from '#/features/connection/hooks/use-studio-service'
import { buttonVariants } from '#/shared/ui/button'
import { Link } from '@tanstack/react-router'
import { SlidersHorizontalIcon } from 'lucide-react'
import { ConnectionProfilesList } from '#/features/connection/components/connection-profiles'
import { useTranslation } from 'react-i18next'

// Local connection configuration is also the recovery page for an unavailable server.
export function ConnectionSettingsPage() {
  const { t } = useTranslation('studio')
  const { connectionRole } = useAppConnection()
  const { provider } = useStudioService()
  return (
    <div className="flex w-full min-w-0 flex-col gap-5">
      <h1 className="text-2xl font-semibold">
        {t('appShell:footer.connection')}
      </h1>
      <ConnectionProfilesList />
      {connectionRole === 'root' && provider === 'opensource' ? (
        <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-5">
          <div className="grid gap-1">
            <h2 className="font-medium">{t('featureToggles.title')}</h2>
            <p className="text-sm text-muted-foreground">
              {t('featureToggles.subtitle')}
            </p>
          </div>
          <Link
            to="/admin/studio-features"
            className={buttonVariants({ variant: 'outline' })}
          >
            <SlidersHorizontalIcon />
            {t('featureToggles.openSettings')}
          </Link>
        </section>
      ) : null}
    </div>
  )
}

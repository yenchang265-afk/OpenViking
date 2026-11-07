import { useAppConnection } from '#/features/connection/hooks/use-app-connection'
import { useStudioFeatureToggles } from '#/features/connection/hooks/use-studio-feature-toggles'
import { useStudioService } from '#/features/connection/hooks/use-studio-service'
import { STUDIO_FEATURES } from '#/shared/lib/studio-service'
import { Badge } from '#/shared/ui/badge'
import { Button } from '#/shared/ui/button'
import { Switch } from '#/shared/ui/switch'
import {
  CheckIcon,
  InfoIcon,
  LoaderCircleIcon,
  ShieldCheckIcon,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

const FEATURE_DOMAINS = ['workspace', 'extensions'] as const

export function StudioFeatureSettings() {
  const { connectionRole } = useAppConnection()
  const service = useStudioService()
  const { t } = useTranslation('studio')
  const toggles = useStudioFeatureToggles()
  if (connectionRole !== 'root' || service.provider !== 'opensource')
    return null
  const hasError = toggles.isError || toggles.mutation.isError
  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-2">
          <p className="text-sm text-muted-foreground">
            {t('appShell:modes.management')}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t('featureToggles.title')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('featureToggles.subtitle')}
          </p>
        </div>
        <Badge variant="secondary">
          <ShieldCheckIcon />
          {t('featureToggles.rootOnly')}
        </Badge>
      </header>
      <div className="flex items-start gap-3 rounded-xl border bg-muted/30 p-4 text-sm">
        <InfoIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <p>{t('featureToggles.description')}</p>
      </div>
      {hasError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/30 p-4 text-sm text-destructive"
        >
          <p>{t('featureToggles.error')}</p>
          {toggles.isError ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => toggles.refetch()}
            >
              {t('featureToggles.retry')}
            </Button>
          ) : null}
        </div>
      ) : null}
      <p
        role="status"
        aria-live="polite"
        className="flex items-center gap-2 text-sm text-muted-foreground"
      >
        {toggles.mutation.isPending || toggles.isLoading ? (
          <LoaderCircleIcon className="size-4 animate-spin" />
        ) : !hasError && toggles.data ? (
          <CheckIcon className="size-4 text-primary" />
        ) : null}
        {toggles.mutation.isPending
          ? t('featureToggles.saving')
          : toggles.isLoading
            ? t('featureToggles.loading')
            : !hasError && toggles.data
              ? t('featureToggles.saved')
              : null}
      </p>
      {FEATURE_DOMAINS.map((domain) => (
        <section
          key={domain}
          aria-labelledby={`studio-features-${domain}`}
          className="overflow-hidden rounded-xl border bg-card"
        >
          <h2
            id={`studio-features-${domain}`}
            className="border-b px-5 py-4 text-lg font-medium"
          >
            {t(`featureToggles.groups.${domain}`)}
          </h2>
          <div className="divide-y px-5">
            {STUDIO_FEATURES.filter((feature) => feature.domain === domain).map(
              (feature) => (
                <div
                  key={feature.id}
                  className="flex items-center justify-between gap-6 py-4"
                >
                  <div className="grid gap-1">
                    <label
                      htmlFor={`studio-feature-${feature.id}`}
                      className="cursor-pointer text-sm font-medium"
                    >
                      {t(`featureToggles.features.${feature.id}`)}
                    </label>
                    <p
                      id={`studio-feature-${feature.id}-description`}
                      className="text-sm text-muted-foreground"
                    >
                      {t(`featureToggles.descriptions.${feature.id}`)}
                    </p>
                  </div>
                  <Switch
                    id={`studio-feature-${feature.id}`}
                    aria-describedby={`studio-feature-${feature.id}-description`}
                    checked={toggles.isEnabled(feature.id)}
                    disabled={
                      !toggles.data ||
                      toggles.isError ||
                      toggles.mutation.isPending
                    }
                    onCheckedChange={(checked) =>
                      toggles.mutation.mutate({ [feature.id]: checked })
                    }
                  />
                </div>
              ),
            )}
          </div>
        </section>
      ))}
    </div>
  )
}

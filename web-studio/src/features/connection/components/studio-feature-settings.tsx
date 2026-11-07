import { useAppConnection } from '#/features/connection/hooks/use-app-connection'
import { useStudioFeatureToggles } from '#/features/connection/hooks/use-studio-feature-toggles'
import { useStudioService } from '#/features/connection/hooks/use-studio-service'
import { STUDIO_FEATURES } from '#/shared/lib/studio-service'
import { useTranslation } from 'react-i18next'

export function StudioFeatureSettings() {
  const { connectionRole } = useAppConnection()
  const service = useStudioService()
  const { t } = useTranslation('studio')
  const toggles = useStudioFeatureToggles()
  if (connectionRole !== 'root' || service.provider !== 'opensource')
    return null
  return (
    <section className="grid gap-4 rounded-xl border p-5">
      <h2 className="text-lg font-medium">{t('featureToggles.title')}</h2>
      <p className="text-sm text-muted-foreground">
        {t('featureToggles.description')}
      </p>
      {toggles.isError || toggles.mutation.isError ? (
        <p role="alert">{t('featureToggles.error')}</p>
      ) : null}
      {STUDIO_FEATURES.filter((feature) => feature.domain !== 'management').map(
        (feature) => (
          <label
            key={feature.id}
            className="flex items-center justify-between gap-4"
          >
            <span>{t(`featureToggles.features.${feature.id}`)}</span>
            <input
              type="checkbox"
              role="switch"
              checked={toggles.isEnabled(feature.id)}
              disabled={
                !toggles.data || toggles.isError || toggles.mutation.isPending
              }
              onChange={(event) =>
                toggles.mutation.mutate({ [feature.id]: event.target.checked })
              }
            />
          </label>
        ),
      )}
    </section>
  )
}

import { StudioFeatureSettings } from '#/features/connection/components/studio-feature-settings'
import { useAppConnection } from '#/features/connection/hooks/use-app-connection'
import { useStudioService } from '#/features/connection/hooks/use-studio-service'
import { useTranslation } from 'react-i18next'

export function StudioFeaturesRoute() {
  const { t } = useTranslation('appShell')
  const { connectionRole, isConnectionRoleLoading } = useAppConnection()
  const { provider } = useStudioService()
  if (isConnectionRoleLoading) return <p role="status">{t('modes.checking')}</p>
  if (connectionRole !== 'root' || provider !== 'opensource')
    return <p>{t('modes.rootRequired')}</p>
  return <StudioFeatureSettings />
}

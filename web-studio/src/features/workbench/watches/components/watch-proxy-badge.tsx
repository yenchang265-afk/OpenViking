import { useTranslation } from 'react-i18next'

import { Badge } from '#/shared/ui/badge'

type WatchProxyBadgeProps = {
  proxyHost: string | null
  viaProxy: boolean
}

/** Marks a sync whose source is fetched through an admin-configured proxy. */
export function WatchProxyBadge({ proxyHost, viaProxy }: WatchProxyBadgeProps) {
  const { t } = useTranslation('watchesPage')
  if (!viaProxy) return null

  return (
    <Badge
      variant="outline"
      title={
        proxyHost ? t('proxy.hostHint', { host: proxyHost }) : t('proxy.hint')
      }
    >
      {t('proxy.badge')}
    </Badge>
  )
}

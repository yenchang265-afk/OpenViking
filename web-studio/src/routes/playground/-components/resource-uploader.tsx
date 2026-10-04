import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { UserIcon } from 'lucide-react'

import { useAppConnection } from '#/hooks/use-app-connection'
import { fetchResourceUploader } from '#/routes/resources/-lib/api'

export function ResourceUploader({ uri }: { uri: string }) {
  const { t } = useTranslation('playground')
  const { identityScopeKey } = useAppConnection()
  const { data: uploadedBy } = useQuery({
    queryKey: ['resource-uploader', identityScopeKey, uri],
    queryFn: ({ signal }) => fetchResourceUploader(uri, signal),
    // Unknown for the root and for resources added before uploads were recorded.
    retry: false,
  })

  if (!uploadedBy) return null

  const label = t('uploadedBy', { user: uploadedBy })
  return (
    <span
      className="flex max-w-40 shrink-0 items-center gap-1 text-xs text-muted-foreground"
      title={label}
      aria-label={label}
    >
      <UserIcon className="size-3.5 shrink-0" />
      <span className="truncate">{uploadedBy}</span>
    </span>
  )
}

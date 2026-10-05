import type { LucideIcon } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { PencilIcon, UserIcon } from 'lucide-react'

import { useAppConnection } from '#/hooks/use-app-connection'
import { fetchResourceAuthors } from '#/routes/resources/-lib/api'

export function ResourceAuthors({ uri }: { uri: string }) {
  const { t } = useTranslation('playground')
  const { identityScopeKey } = useAppConnection()
  const { data } = useQuery({
    queryKey: ['resource-authors', identityScopeKey, uri],
    queryFn: ({ signal }) => fetchResourceAuthors(uri, signal),
    // Unknown for the root and for resources added before authors were recorded.
    retry: false,
  })

  const uploadedBy = data?.uploadedBy ?? ''
  const updatedBy = data?.updatedBy ?? ''
  const showUpdater = Boolean(updatedBy) && updatedBy !== uploadedBy
  if (!uploadedBy && !showUpdater) return null

  return (
    <>
      {uploadedBy ? (
        <AuthorChip
          icon={UserIcon}
          label={t('uploadedBy', { user: uploadedBy })}
          user={uploadedBy}
        />
      ) : null}
      {showUpdater ? (
        <AuthorChip
          icon={PencilIcon}
          label={t('updatedBy', { user: updatedBy })}
          user={updatedBy}
        />
      ) : null}
    </>
  )
}

function AuthorChip({
  icon: Icon,
  label,
  user,
}: {
  icon: LucideIcon
  label: string
  user: string
}) {
  return (
    <span
      className="flex max-w-40 shrink-0 items-center gap-1 text-xs text-muted-foreground"
      title={label}
      aria-label={label}
    >
      <Icon className="size-3.5 shrink-0" />
      <span className="truncate">{user}</span>
    </span>
  )
}

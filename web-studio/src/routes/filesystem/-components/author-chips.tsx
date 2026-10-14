import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PencilIcon, UserIcon } from 'lucide-react'

import { cn } from '#/lib/utils'

/** Creator chip, plus an updater chip when someone else changed it last. */
export function AuthorChips({
  createdBy = '',
  updatedBy = '',
  compact = false,
}: {
  createdBy?: string
  updatedBy?: string
  compact?: boolean
}) {
  const { t } = useTranslation('filesystem')
  const showUpdater = Boolean(updatedBy) && updatedBy !== createdBy
  if (!createdBy && !showUpdater) return null

  return (
    <>
      {createdBy ? (
        <AuthorChip
          compact={compact}
          icon={UserIcon}
          label={t('createdBy', { user: createdBy })}
          user={createdBy}
        />
      ) : null}
      {showUpdater ? (
        <AuthorChip
          compact={compact}
          icon={PencilIcon}
          label={t('updatedBy', { user: updatedBy })}
          user={updatedBy}
        />
      ) : null}
    </>
  )
}

function AuthorChip({
  compact,
  icon: Icon,
  label,
  user,
}: {
  compact: boolean
  icon: LucideIcon
  label: string
  user: string
}) {
  return (
    <span
      className={cn(
        'flex shrink-0 items-center gap-1 text-muted-foreground',
        compact ? 'max-w-20 font-sans text-[10px]' : 'max-w-40 text-xs',
      )}
      title={label}
      aria-label={label}
    >
      <Icon className={cn('shrink-0', compact ? 'size-3' : 'size-3.5')} />
      <span className="truncate">{user}</span>
    </span>
  )
}

import type { TFunction } from 'i18next'

import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'
import type { FolderFilters } from '../-lib/folder-filter'

type DirectoryScanFieldsProps = {
  value: FolderFilters
  onChange: (value: FolderFilters) => void
  t: TFunction<'addResource'>
  /** Explain how the filters apply to a picked folder (upload mode). */
  showHint?: boolean
}

/** Ignore dirs / include / exclude, as `ov add-resource` takes them. */
export function DirectoryScanFields({
  value,
  onChange,
  t,
  showHint = false,
}: DirectoryScanFieldsProps) {
  const fields = [
    { key: 'include', id: 'add-resource-include' },
    { key: 'exclude', id: 'add-resource-exclude' },
    { key: 'ignoreDirs', id: 'add-resource-ignore-dirs' },
  ] as const

  return (
    <div className="space-y-3">
      {showHint ? (
        <p className="text-xs text-muted-foreground">
          {t('directoryScan.hint')}
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-3">
        {fields.map(({ key, id }) => (
          <div key={key} className="space-y-2">
            <Label htmlFor={id}>{t(`directoryScan.${key}`)}</Label>
            <Input
              id={id}
              placeholder={t(`directoryScan.${key}.placeholder`)}
              value={value[key]}
              onChange={(event) =>
                onChange({ ...value, [key]: event.target.value })
              }
            />
          </div>
        ))}
      </div>
    </div>
  )
}

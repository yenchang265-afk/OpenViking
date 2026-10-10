import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { DownloadIcon, LoaderCircleIcon, SparklesIcon } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '#/components/ui/button'
import { useInvalidateVikingFs } from '#/routes/resources/-hooks/viking-fm'
import { errorText } from '../-lib/api'
import {
  BUILTIN_SKILLS_ROOT,
  installMissingBuiltinSkills,
  missingBuiltinSkills,
} from '../-lib/builtin-skills'

/** Refreshes every view that lists skills: pickers, the Skills page, the tree. */
export function useRefreshSkillViews() {
  const queryClient = useQueryClient()
  const { invalidateList } = useInvalidateVikingFs()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['compile-skills'] }),
      queryClient.invalidateQueries({ queryKey: ['skills'] }),
      invalidateList('viking://agent'),
      invalidateList(BUILTIN_SKILLS_ROOT),
    ])
}

/** Offers to install the bundled compile skills that are not installed yet. */
export function BuiltinSkillsNotice({
  installed,
}: {
  installed?: readonly { uri: string }[]
}) {
  const { t } = useTranslation('compile')
  const refresh = useRefreshSkillViews()
  const [busy, setBusy] = useState(false)
  if (!installed) return null
  const missing = missingBuiltinSkills(installed)
  if (!missing.length) return null

  async function install() {
    setBusy(true)
    try {
      // Re-checks the server, so skills installed since this render are kept.
      const { installed: added, failed } = await installMissingBuiltinSkills()
      if (failed.length)
        toast.error(
          t('builtinInstallFailed', {
            details: failed
              .map(({ name, error }) => `${name}: ${errorText(error)}`)
              .join('; '),
          }),
        )
      else toast.success(t('builtinInstalled', { count: added.length }))
    } catch (error) {
      toast.error(t('builtinInstallFailed', { details: errorText(error) }))
    } finally {
      await refresh()
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed bg-muted/30 p-3 text-sm">
      <SparklesIcon className="size-4 shrink-0 text-primary" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {t('builtinTitle', { count: missing.length })}
        </p>
        <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {t('builtinHint', {
            names: missing.map((skill) => skill.name).join(', '),
            root: BUILTIN_SKILLS_ROOT,
          })}
        </p>
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => void install()}
      >
        {busy ? (
          <LoaderCircleIcon className="animate-spin" />
        ) : (
          <DownloadIcon />
        )}
        {t('builtinInstall')}
      </Button>
    </div>
  )
}

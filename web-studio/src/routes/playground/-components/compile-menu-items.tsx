import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { WandSparklesIcon } from 'lucide-react'
import { toast } from 'sonner'

import {
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
} from '#/components/ui/context-menu'
import { useRefreshSkillViews } from '#/routes/compile/-components/builtin-skills'
import { errorText } from '#/routes/compile/-lib/api'
import {
  BUILTIN_COMPILE_SKILLS,
  BUILTIN_SKILLS_ROOT,
  ensureBuiltinSkill,
  isSkillRootUri,
  suggestCompileTarget,
} from '#/routes/compile/-lib/builtin-skills'
import type { BuiltinCompileSkill } from '#/routes/compile/-lib/builtin-skills'

type CompilePrefill = { skill?: string; from?: string; to?: string }

/**
 * Compile actions for a tree directory. A skill folder compiles *with* that
 * skill; any other folder is a source for one of the bundled compile skills.
 */
export function CompileMenuItems({ dirUri }: { dirUri: string }) {
  const { t } = useTranslation('playground')
  const navigate = useNavigate()
  const refreshSkillViews = useRefreshSkillViews()
  const uri = dirUri.replace(/\/+$/, '')
  const openForm = (search: CompilePrefill) =>
    void navigate({ to: '/compile/new', search })

  if (isSkillRootUri(uri)) {
    return (
      <ContextMenuItem onClick={() => openForm({ skill: uri })}>
        <WandSparklesIcon />
        {t('explorer.menu.compileWithSkill')}
      </ContextMenuItem>
    )
  }

  const compileWith = async (skill: BuiltinCompileSkill) => {
    try {
      if (await ensureBuiltinSkill(skill)) {
        toast.success(t('explorer.menu.compileInstalled', { name: skill.name }))
        // Refetching the open tree must not hold up opening the form.
        void refreshSkillViews()
      }
    } catch (error) {
      toast.error(
        t('explorer.menu.compileInstallFailed', {
          name: skill.name,
          message: errorText(error),
        }),
      )
      return
    }
    openForm({
      skill: skill.uri,
      from: uri,
      to: suggestCompileTarget(uri, skill.name),
    })
  }

  return (
    <ContextMenuSub>
      <ContextMenuSubTrigger>
        <WandSparklesIcon />
        {t('explorer.menu.compileWith')}
      </ContextMenuSubTrigger>
      <ContextMenuSubContent className="max-w-72">
        <p className="px-2 py-1.5 text-xs text-muted-foreground">
          {t('explorer.menu.compileInstallHint', { root: BUILTIN_SKILLS_ROOT })}
        </p>
        {BUILTIN_COMPILE_SKILLS.map((skill) => (
          <ContextMenuItem
            key={skill.uri}
            title={skill.description}
            onClick={() => void compileWith(skill)}
          >
            {skill.name}
          </ContextMenuItem>
        ))}
        <ContextMenuSeparator />
        <ContextMenuItem onClick={() => openForm({ from: uri })}>
          {t('explorer.menu.compileOther')}
        </ContextMenuItem>
      </ContextMenuSubContent>
    </ContextMenuSub>
  )
}

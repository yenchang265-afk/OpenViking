import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { WandSparklesIcon } from 'lucide-react'

import {
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
} from '#/components/ui/context-menu'
import { useAppConnection } from '#/hooks/use-app-connection'
import { fetchCompileSkills } from '#/routes/compile/-lib/api'
import {
  isSkillRootUri,
  suggestCompileTarget,
} from '#/routes/compile/-lib/tree-compile'

type CompilePrefill = { skill?: string; from?: string; to?: string }

/**
 * Compile actions for a tree directory. A skill folder compiles *with* that
 * skill; any other folder is a source for one of the installed skills.
 */
export function CompileMenuItems({ dirUri }: { dirUri: string }) {
  const { t } = useTranslation('playground')
  const navigate = useNavigate()
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

  return (
    <ContextMenuSub>
      <ContextMenuSubTrigger>
        <WandSparklesIcon />
        {t('explorer.menu.compileWith')}
      </ContextMenuSubTrigger>
      <ContextMenuSubContent className="max-w-72">
        <SkillItems
          onPick={(skill) =>
            openForm({
              skill: skill.uri,
              from: uri,
              to: suggestCompileTarget(uri, skill.name),
            })
          }
        />
        <ContextMenuSeparator />
        <ContextMenuItem onClick={() => openForm({ from: uri })}>
          {t('explorer.menu.compileOther')}
        </ContextMenuItem>
      </ContextMenuSubContent>
    </ContextMenuSub>
  )
}

/** Same list as the compile form's Skill picker; loads when the submenu opens. */
function SkillItems({
  onPick,
}: {
  onPick: (skill: { name: string; uri: string }) => void
}) {
  const { t } = useTranslation('playground')
  const { identityScopeKey } = useAppConnection()
  const skills = useQuery({
    queryKey: ['compile-skills', identityScopeKey],
    queryFn: ({ signal }) => fetchCompileSkills(signal),
    staleTime: 30_000,
  })
  const status = skills.isPending
    ? t('explorer.menu.compileLoading')
    : skills.isError
      ? t('explorer.menu.compileLoadFailed')
      : skills.data.length === 0
        ? t('explorer.menu.compileNoSkills')
        : null
  if (status) return <ContextMenuItem disabled>{status}</ContextMenuItem>
  return skills.data!.map((skill) => (
    <ContextMenuItem
      key={skill.uri}
      title={skill.description || skill.uri}
      onClick={() => onPick(skill)}
    >
      {skill.name}
    </ContextMenuItem>
  ))
}

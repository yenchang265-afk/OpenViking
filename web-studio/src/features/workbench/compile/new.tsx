import { useEffect, useRef, useState } from 'react'
import { getRouteApi, useNavigate } from '@tanstack/react-router'
import { useAppConnection } from '#/features/connection/hooks/use-app-connection'
import { CompileForm } from '#/features/workbench/compile/components/compile-form'
import type { CompilePrefill } from '#/features/workbench/compile/components/compile-form'

export type NewCompileSearch = {
  fromTask?: string
  skill?: string
  from?: string
  to?: string
  // Edit the saved schedule of this Compile target.
  target?: string
}

export function NewCompile() {
  const { identityScopeKey } = useAppConnection()
  const navigate = useNavigate()
  const { fromTask, skill, from, to, target } =
    getRouteApi('/compile/new').useSearch()
  const [prefill] = useState<CompilePrefill | undefined>(() =>
    !target && (skill || from || to) ? { skill, from, to } : undefined,
  )
  // Read once: a reload must keep the edited draft, not re-apply the link.
  const stripped = useRef(false)
  useEffect(() => {
    if (!prefill || stripped.current) return
    stripped.current = true
    void navigate({
      to: '/compile/new',
      search: fromTask ? { fromTask } : {},
      replace: true,
    })
  }, [prefill, fromTask, navigate])
  return (
    <CompileForm
      // The prefill is held in state, so stripping it from the URL must not remount.
      key={`${identityScopeKey}:${target || ''}:${fromTask || ''}`}
      fromTask={target ? undefined : fromTask}
      prefill={prefill}
      target={target}
    />
  )
}

import { useEffect, useRef, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useAppConnection } from '#/hooks/use-app-connection'
import { CompileForm } from './-components/compile-form'
import type { CompilePrefill } from './-components/compile-form'

type NewCompileSearch = {
  fromTask?: string
  skill?: string
  from?: string
  to?: string
}
const text = (value: unknown) => (typeof value === 'string' ? value : undefined)
// Prefill only ever names Viking URIs; anything else in a link is dropped.
const vikingUri = (value: unknown) =>
  typeof value === 'string' && value.startsWith('viking://') ? value : undefined

export const Route = createFileRoute('/compile/new')({
  validateSearch: (s: Record<string, unknown>): NewCompileSearch => ({
    fromTask: text(s.fromTask),
    // Prefill from the context tree's "Compile with" menu.
    skill: vikingUri(s.skill),
    from: vikingUri(s.from),
    to: vikingUri(s.to),
  }),
  component: NewCompile,
})
function NewCompile() {
  const { identityScopeKey } = useAppConnection()
  const navigate = useNavigate()
  const { fromTask, skill, from, to } = Route.useSearch()
  const [prefill] = useState<CompilePrefill | undefined>(() =>
    skill || from || to ? { skill, from, to } : undefined,
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
      key={`${identityScopeKey}:${fromTask || ''}`}
      fromTask={fromTask}
      prefill={prefill}
    />
  )
}

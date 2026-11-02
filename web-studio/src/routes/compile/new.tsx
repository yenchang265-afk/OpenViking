import { NewCompile } from '#/features/workbench/compile/new'
import type { NewCompileSearch } from '#/features/workbench/compile/new'
import { createFileRoute } from '@tanstack/react-router'

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

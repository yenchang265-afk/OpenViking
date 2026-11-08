import { ArrangerPage } from '#/features/workbench/arranger/page'
import type { ArrangerSearch } from '#/features/workbench/arranger/page'
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/arranger')({
  validateSearch: (search: Record<string, unknown>): ArrangerSearch => ({
    selected: typeof search.selected === 'string' ? search.selected : undefined,
    uri: typeof search.uri === 'string' ? search.uri : undefined,
    view:
      search.view === 'graph' || search.view === 'list'
        ? search.view
        : undefined,
  }),
  component: ArrangerPage,
})

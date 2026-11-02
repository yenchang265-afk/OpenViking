import { useQuery } from '@tanstack/react-query'

import { useAppConnection } from '#/features/connection/hooks/use-app-connection'
import { fetchResourceAuthors } from '#/features/workbench/resources/lib/api'

import { AuthorChips } from './author-chips'

export function ResourceAuthors({ uri }: { uri: string }) {
  const { identityScopeKey } = useAppConnection()
  const { data } = useQuery({
    queryKey: ['resource-authors', identityScopeKey, uri],
    queryFn: ({ signal }) => fetchResourceAuthors(uri, signal),
    // Unknown for the root and for resources added before authors were recorded.
    retry: false,
  })

  return (
    <AuthorChips
      createdBy={data?.createdBy ?? ''}
      updatedBy={data?.updatedBy ?? ''}
    />
  )
}

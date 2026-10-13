import { useQuery } from '@tanstack/react-query'

import { useAppConnection } from '#/hooks/use-app-connection'
import { fetchResourceAuthors } from '#/routes/resources/-lib/api'

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
      uploadedBy={data?.uploadedBy ?? ''}
      updatedBy={data?.updatedBy ?? ''}
    />
  )
}

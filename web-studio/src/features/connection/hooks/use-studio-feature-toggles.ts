import i18n from '#/i18n/core'
import { useAppConnection } from '#/features/connection/hooks/use-app-connection'
import { useStudioService } from '#/features/connection/hooks/use-studio-service'
import { createOvClient, getOvResult } from '#/shared/api/ov-client/index'
import type { STUDIO_FEATURES } from '#/shared/lib/studio-service'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export type StudioFeatureToggles = Partial<
  Record<(typeof STUDIO_FEATURES)[number]['id'], boolean>
>

export function useStudioFeatureToggles() {
  const { connection, identityScopeKey, serverMode, connectionRole } =
    useAppConnection()
  const service = useStudioService()
  const queryClient = useQueryClient()
  const queryKey = ['studio-feature-toggles', identityScopeKey]
  const { client } = createOvClient({
    baseUrl: connection.baseUrl,
    connection: { ...connection, identityHeaders: serverMode === 'trusted' },
  })
  const query = useQuery({
    queryKey,
    enabled: service.ready && service.provider === 'opensource',
    queryFn: ({ signal }) =>
      getOvResult<StudioFeatureToggles>(
        client.get({ url: '/api/v1/studio/features', signal }),
      ),
    refetchInterval: 15_000,
    retry: false,
  })
  const mutation = useMutation({
    mutationFn: async (patch: StudioFeatureToggles) => {
      if (connectionRole !== 'root')
        throw new Error(i18n.t('studio:states.managementRequired.title'))
      const scopeKey = queryKey
      await queryClient.cancelQueries({ queryKey: scopeKey })
      const data = await getOvResult<StudioFeatureToggles>(
        client.patch({
          url: '/api/v1/admin/studio/features',
          headers: { 'Content-Type': 'application/json' },
          body: patch,
        }),
      )
      return { data, scopeKey }
    },
    onSuccess: ({ data, scopeKey }) => queryClient.setQueryData(scopeKey, data),
  })
  return {
    ...query,
    mutation,
    isEnabled: (id: (typeof STUDIO_FEATURES)[number]['id']) =>
      query.data?.[id] !== false,
  }
}

import { StudioFeaturesRoute } from '#/features/admin/studio-features/page'
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/admin/studio-features')({
  component: StudioFeaturesRoute,
})

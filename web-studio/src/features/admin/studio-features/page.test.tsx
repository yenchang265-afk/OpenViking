// @vitest-environment jsdom
import { StudioFeaturesRoute } from '#/features/admin/studio-features/page'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  role: 'root',
  loading: false,
  provider: 'opensource',
}))
vi.mock('#/features/connection/hooks/use-app-connection', () => ({
  useAppConnection: () => ({
    connectionRole: state.role,
    isConnectionRoleLoading: state.loading,
  }),
}))
vi.mock('#/features/connection/hooks/use-studio-service', () => ({
  useStudioService: () => ({ provider: state.provider }),
}))
vi.mock('#/features/connection/components/studio-feature-settings', () => ({
  StudioFeatureSettings: () => <h1>Studio feature controls</h1>,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
afterEach(() => {
  cleanup()
  Object.assign(state, { role: 'root', loading: false, provider: 'opensource' })
})
it('opens the dedicated page for root', () => {
  render(<StudioFeaturesRoute />)
  expect(
    screen.getByRole('heading', { name: 'Studio feature controls' }),
  ).toBeTruthy()
})
it.each(['admin', 'user'])('blocks direct access for %s', (role) => {
  state.role = role
  render(<StudioFeaturesRoute />)
  expect(screen.queryByRole('heading')).toBeNull()
  expect(screen.getByText('modes.rootRequired')).toBeTruthy()
})
it('waits for root identity verification', () => {
  state.loading = true
  render(<StudioFeaturesRoute />)
  expect(screen.getByRole('status')).toBeTruthy()
  expect(screen.queryByRole('heading')).toBeNull()
})
it('does not expose controls for hosted providers', () => {
  state.provider = 'volcengine'
  render(<StudioFeaturesRoute />)
  expect(screen.queryByRole('heading')).toBeNull()
})

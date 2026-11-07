// @vitest-environment jsdom
import { StudioFeatureSettings } from '#/features/connection/components/studio-feature-settings'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  role: 'root',
  pending: false,
  mutate: vi.fn(),
}))
vi.mock('#/features/connection/hooks/use-app-connection', () => ({
  useAppConnection: () => ({ connectionRole: state.role }),
}))
vi.mock('#/features/connection/hooks/use-studio-service', () => ({
  useStudioService: () => ({ provider: 'opensource' }),
}))
vi.mock('#/features/connection/hooks/use-studio-feature-toggles', () => ({
  useStudioFeatureToggles: () => ({
    data: { compile: false },
    isError: false,
    isEnabled: (id: string) => id !== 'compile',
    mutation: {
      isPending: state.pending,
      isError: false,
      mutate: state.mutate,
    },
  }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
afterEach(() => {
  cleanup()
  state.role = 'root'
  state.pending = false
  vi.clearAllMocks()
})
it('lets root re-enable a disabled feature and preserves management access', () => {
  render(<StudioFeatureSettings />)
  const toggle = screen.getByRole<HTMLInputElement>('switch', {
    name: 'featureToggles.features.compile',
  })
  expect(toggle.checked).toBe(false)
  fireEvent.click(toggle)
  expect(state.mutate).toHaveBeenCalledWith({ compile: true })
  expect(screen.queryByText('featureToggles.features.users')).toBeNull()
})
it.each(['user', 'admin'])('hides controls for %s', (role) => {
  state.role = role
  render(<StudioFeatureSettings />)
  expect(screen.queryAllByRole('switch')).toHaveLength(0)
})
it('disables controls during a save', () => {
  state.pending = true
  render(<StudioFeatureSettings />)
  expect(
    screen
      .getAllByRole<HTMLInputElement>('switch')
      .every((input) => input.disabled),
  ).toBe(true)
})

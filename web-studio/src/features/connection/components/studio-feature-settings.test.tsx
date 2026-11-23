// @vitest-environment jsdom
import { StudioFeatureSettings } from '#/features/connection/components/studio-feature-settings'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  role: 'root',
  disabled: ['compile'] as string[],
  pending: false,
  error: false,
  refetch: vi.fn(),
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
    isError: state.error,
    refetch: state.refetch,
    isEnabled: (id: string) => !state.disabled.includes(id),
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
  state.disabled = ['compile']
  state.pending = false
  state.error = false
  vi.clearAllMocks()
})
it('lets root re-enable a disabled feature and preserves management access', () => {
  render(<StudioFeatureSettings />)
  const toggle = screen.getByRole('switch', {
    name: 'featureToggles.features.compile',
  })
  expect(toggle.getAttribute('aria-checked')).toBe('false')
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
      .every(
        (input) =>
          input.getAttribute('aria-disabled') === 'true' || input.disabled,
      ),
  ).toBe(true)
})

it('groups controls into workspace and extensions with save status', () => {
  render(<StudioFeatureSettings />)
  expect(
    screen.getByRole('region', { name: 'featureToggles.groups.workspace' }),
  ).toBeTruthy()
  expect(
    screen.getByRole('region', { name: 'featureToggles.groups.extensions' }),
  ).toBeTruthy()
  expect(screen.getByRole('status').textContent).toContain(
    'featureToggles.saved',
  )
})
it('shows a retry action and disables toggles when loading fails', () => {
  state.error = true
  render(<StudioFeatureSettings />)
  expect(screen.getByRole('alert')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'featureToggles.retry' }))
  expect(state.refetch).toHaveBeenCalledOnce()
  expect(
    screen
      .getAllByRole<HTMLButtonElement>('switch')
      .every(
        (input) =>
          input.getAttribute('aria-disabled') === 'true' || input.disabled,
      ),
  ).toBe(true)
})
it('lets root switch remote resource imports from the workspace group', () => {
  render(<StudioFeatureSettings />)
  const workspace = screen.getByRole('region', {
    name: 'featureToggles.groups.workspace',
  })
  const toggle = within(workspace).getByRole('switch', {
    name: 'featureToggles.features.remoteResources',
  })
  fireEvent.click(toggle)
  expect(state.mutate).toHaveBeenCalledWith({ remoteResources: false })
})
it('locks scheduled sync off while remote resources are off', () => {
  state.disabled = ['remoteResources', 'watches']
  render(<StudioFeatureSettings />)
  const toggle = screen.getByRole('switch', {
    name: 'featureToggles.features.watches',
  })
  expect(toggle.getAttribute('aria-checked')).toBe('false')
  expect(
    toggle.getAttribute('aria-disabled') === 'true' ||
      (toggle as HTMLButtonElement).disabled,
  ).toBe(true)
  expect(screen.getByText('featureToggles.requires')).toBeTruthy()
})
it('leaves scheduled sync editable while remote resources are on', () => {
  render(<StudioFeatureSettings />)
  const toggle = screen.getByRole('switch', {
    name: 'featureToggles.features.watches',
  })
  expect(toggle.getAttribute('aria-checked')).toBe('true')
  expect(toggle.getAttribute('aria-disabled')).not.toBe('true')
  expect(screen.queryByText('featureToggles.requires')).toBeNull()
})

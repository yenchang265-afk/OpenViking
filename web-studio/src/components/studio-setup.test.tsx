// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StudioSetup } from './studio-setup'

const mocks = vi.hoisted(() => ({
  verify: vi.fn(),
  complete: vi.fn(),
}))
vi.mock('react-i18next', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('#/lib/connection/onboarding', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  markStudioSetupPending: vi.fn(),
  verifyStudioSetup: mocks.verify,
  completeStudioSetup: mocks.complete,
}))
afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
})
beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

const openSource = {
  serviceSelection: 'opensource',
  baseUrl: 'http://127.0.0.1:1933',
  apiKey: 'saved-user-key',
  adminApiKey: 'saved-root-key',
  accountId: 'team',
  userId: 'alice',
}

function saveProfiles(activeId: string, profiles: unknown[]) {
  localStorage.setItem(
    'ov_console_connection_profiles',
    JSON.stringify({ activeId, profiles }),
  )
}

const url = () =>
  screen.getByLabelText<HTMLInputElement>('settings:fields.baseUrl')
const key = () =>
  screen.getByLabelText<HTMLInputElement>('settings:fields.userApiKey')
const verifyButton = () =>
  screen.getByRole<HTMLButtonElement>('button', { name: 'verify' })

it('connects on a single screen without a workspace chooser', () => {
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url()).toBeTruthy()
  expect(key()).toBeTruthy()
  expect(screen.queryByRole('combobox')).toBeNull()
  expect(screen.queryByRole('radio')).toBeNull()
  expect(screen.queryByRole('button', { name: 'next' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'back' })).toBeNull()
  expect(screen.queryByText('workspace')).toBeNull()
})

it('prefills the active open-source address without its credentials', () => {
  saveProfiles('active', [
    {
      id: 'other',
      name: 'Other',
      connection: { ...openSource, baseUrl: 'https://other.test/ov' },
    },
    { id: 'active', name: 'Active', connection: openSource },
  ])
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe('http://127.0.0.1:1933')
  expect(key().value).toBe('')
  expect(key().autocomplete).toBe('new-password')
  fireEvent.click(screen.getByRole('button', { name: 'advanced' }))
  expect(
    screen.getByLabelText<HTMLInputElement>('settings:fields.rootApiKey').value,
  ).toBe('')
  expect(
    screen.getByLabelText<HTMLInputElement>('settings:fields.account').value,
  ).toBe('team')
})

it('ignores saved hosted connections', () => {
  saveProfiles('hosted', [
    {
      id: 'hosted',
      name: 'Hosted',
      connection: {
        ...openSource,
        serviceSelection: 'volcengine',
        baseUrl: 'https://hosted.test/ov',
      },
    },
  ])
  render(<StudioSetup onComplete={vi.fn()} />)
  // The hosted address is not reused; the dev-server default applies instead.
  expect(url().value).toBe('http://127.0.0.1:1933')
})

it('defaults to the serving origin when deployed under a base path', () => {
  vi.stubEnv('BASE_URL', '/studio/')
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe(window.location.origin)
})

it('prefills the local server under the dev server', () => {
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe('http://127.0.0.1:1933')
})

it('leaves the address empty for a production build served at the root', () => {
  vi.stubEnv('DEV', false)
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe('')
})

it('defaults to the configured server address over the serving origin', () => {
  vi.stubEnv('BASE_URL', '/studio/')
  vi.stubEnv('VITE_OV_BASE_URL', ' https://api.test/ov/ ')
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe('https://api.test/ov')
})

it('defaults to the configured server address when Studio is hosted separately', () => {
  vi.stubEnv('VITE_OV_BASE_URL', 'https://api.test/ov')
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe('https://api.test/ov')
})

it('falls back to the serving origin when the configured address is invalid', () => {
  vi.stubEnv('BASE_URL', '/studio/')
  vi.stubEnv('VITE_OV_BASE_URL', 'not a url')
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe(window.location.origin)
})

it('prefers the active saved address over the configured one', () => {
  vi.stubEnv('VITE_OV_BASE_URL', 'https://api.test/ov')
  saveProfiles('active', [
    { id: 'active', name: 'Active', connection: openSource },
  ])
  render(<StudioSetup onComplete={vi.fn()} />)
  expect(url().value).toBe('http://127.0.0.1:1933')
})

it('requires a valid address before verifying', () => {
  render(<StudioSetup onComplete={vi.fn()} />)
  fireEvent.change(url(), { target: { value: '' } })
  expect(verifyButton().disabled).toBe(true)
  fireEvent.change(url(), { target: { value: 'ftp://invalid.test' } })
  expect(verifyButton().disabled).toBe(true)
  expect(screen.getByText('studio:profiles.invalidUrl')).toBeTruthy()
  fireEvent.change(url(), { target: { value: 'http://service.test' } })
  expect(verifyButton().disabled).toBe(false)
})

it('enters only after verification, invalidates it on edits, and persists on entry', async () => {
  const done = vi.fn()
  mocks.verify.mockImplementation(async (draft) => draft)
  render(<StudioSetup onComplete={done} />)
  fireEvent.change(url(), { target: { value: 'http://service.test' } })
  fireEvent.click(verifyButton())
  await screen.findByRole('status')
  expect(done).not.toHaveBeenCalled()
  expect(mocks.complete).not.toHaveBeenCalled()
  fireEvent.change(key(), { target: { value: 'changed' } })
  expect(screen.queryByRole('status')).toBeNull()
  fireEvent.click(verifyButton())
  await screen.findByRole('status')
  fireEvent.click(screen.getByRole('button', { name: 'enter' }))
  expect(mocks.complete).toHaveBeenCalledWith(
    expect.objectContaining({
      baseUrl: 'http://service.test',
      apiKey: 'changed',
      serviceSelection: 'opensource',
    }),
    'studio:providers.opensource',
    undefined,
  )
  expect(done).toHaveBeenCalledOnce()
})

it('updates the saved profile that matches the verified connection', async () => {
  saveProfiles('active', [{ id: 'active', name: 'Active', connection: openSource }])
  mocks.verify.mockImplementation(async (draft) => draft)
  render(<StudioSetup onComplete={vi.fn()} />)
  fireEvent.change(key(), { target: { value: 'saved-user-key' } })
  fireEvent.click(verifyButton())
  await screen.findByRole('status')
  fireEvent.click(screen.getByRole('button', { name: 'enter' }))
  expect(mocks.complete).toHaveBeenCalledWith(
    expect.objectContaining({ apiKey: 'saved-user-key' }),
    'studio:providers.opensource',
    'active',
  )
})

it('keeps the user in setup on verification failure', async () => {
  mocks.verify.mockRejectedValueOnce(new Error('Forbidden'))
  const done = vi.fn()
  render(<StudioSetup onComplete={done} />)
  fireEvent.change(url(), { target: { value: 'http://service.test' } })
  fireEvent.click(verifyButton())
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toContain('Forbidden'),
  )
  expect(done).not.toHaveBeenCalled()
})

it('keeps advanced fields out of keyboard navigation while collapsed and preserves their values', () => {
  render(<StudioSetup onComplete={vi.fn()} />)
  const toggle = screen.getByRole('button', { name: 'advanced' })
  const fields = document.getElementById('setup-advanced-fields')
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  expect(fields?.hasAttribute('inert')).toBe(true)
  fireEvent.click(toggle)
  expect(toggle.getAttribute('aria-expanded')).toBe('true')
  expect(fields?.hasAttribute('inert')).toBe(false)
  fireEvent.change(screen.getByLabelText('settings:fields.account'), {
    target: { value: 'team' },
  })
  fireEvent.click(toggle)
  expect(fields?.hasAttribute('inert')).toBe(true)
  fireEvent.click(toggle)
  expect(
    screen.getByLabelText<HTMLInputElement>('settings:fields.account').value,
  ).toBe('team')
})

it('loads the logo from the deployment base path', () => {
  vi.stubEnv('BASE_URL', '/studio/')
  const { container } = render(<StudioSetup onComplete={vi.fn()} />)
  expect(container.querySelector('img')?.getAttribute('src')).toBe(
    '/studio/ov-logo.png',
  )
})

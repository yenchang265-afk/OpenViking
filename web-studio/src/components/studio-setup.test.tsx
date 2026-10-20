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
vi.mock('./setup-identity-directory', () => ({
  SetupIdentityDirectory: ({
    onSelect,
  }: {
    onSelect: (identity: { accountId: string; userId: string }) => void
  }) => (
    <button
      type="button"
      onClick={() => onSelect({ accountId: 'team', userId: 'alice' })}
    >
      choose-directory-user
    </button>
  ),
}))
vi.mock('#/lib/connection/onboarding', async (original) => ({
  ...(await original<Record<string, unknown>>()),
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
  saveProfiles('active', [
    {
      id: 'active',
      name: 'Active',
      connection: { ...openSource, adminApiKey: '' },
    },
  ])
  mocks.verify.mockImplementation(async (draft) => draft)
  render(<StudioSetup onComplete={vi.fn()} />)
  fireEvent.change(key(), { target: { value: 'rotated-user-key' } })
  fireEvent.click(verifyButton())
  await screen.findByRole('status')
  fireEvent.click(screen.getByRole('button', { name: 'enter' }))
  expect(mocks.complete).toHaveBeenCalledWith(
    expect.objectContaining({ apiKey: 'rotated-user-key' }),
    'studio:providers.opensource',
    'active',
  )
})

it.each([
  ['a root key alone', { adminApiKey: 'new-root-key' }],
  ['only one of the saved keys', { apiKey: 'saved-user-key' }],
])(
  'adds a new profile instead of dropping saved keys when given %s',
  async (_label, keys: { apiKey?: string; adminApiKey?: string }) => {
    saveProfiles('active', [
      { id: 'active', name: 'Active', connection: openSource },
    ])
    mocks.verify.mockImplementation(async (draft) => draft)
    render(<StudioSetup onComplete={vi.fn()} />)
    if (keys.apiKey) fireEvent.change(key(), { target: { value: keys.apiKey } })
    if (keys.adminApiKey) {
      fireEvent.click(screen.getByRole('button', { name: 'advanced' }))
      fireEvent.change(
        screen.getByLabelText<HTMLInputElement>('settings:fields.rootApiKey'),
        { target: { value: keys.adminApiKey } },
      )
    }
    fireEvent.click(verifyButton())
    await screen.findByRole('status')
    fireEvent.click(screen.getByRole('button', { name: 'enter' }))
    // Same address and identity as the saved profile, but reusing it would
    // overwrite a key the user did not re-enter.
    expect(mocks.complete).toHaveBeenCalledWith(
      expect.objectContaining({ accountId: 'team', userId: 'alice' }),
      'studio:providers.opensource',
      undefined,
    )
  },
)

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

it('cancels an in-flight verification without replacing the saved workspace', async () => {
  const onCancel = vi.fn()
  const onComplete = vi.fn()
  localStorage.setItem('ov_studio_setup', 'complete')
  mocks.verify.mockImplementationOnce(() => new Promise(() => {}))
  render(
    <StudioSetup
      onComplete={onComplete}
      onCancel={onCancel}
      canReturnToWorkspace
    />,
  )
  fireEvent.change(url(), { target: { value: 'https://other.test' } })
  fireEvent.click(verifyButton())
  await waitFor(() => expect(mocks.verify).toHaveBeenCalled())
  const signal = mocks.verify.mock.calls[0][1] as AbortSignal
  fireEvent.click(screen.getByRole('button', { name: 'cancel' }))
  expect(signal.aborted).toBe(true)
  expect(onCancel).toHaveBeenCalledOnce()
  expect(onComplete).not.toHaveBeenCalled()
  expect(mocks.complete).not.toHaveBeenCalled()
  expect(localStorage.getItem('ov_studio_setup')).toBe('complete')
})

it('offers an exit on first use without requiring a valid address', () => {
  const onCancel = vi.fn()
  render(<StudioSetup onComplete={vi.fn()} onCancel={onCancel} />)
  fireEvent.click(screen.getByRole('button', { name: 'exit' }))
  expect(onCancel).toHaveBeenCalledOnce()
  expect(mocks.verify).not.toHaveBeenCalled()
})

it('opens the account/user picker only after Verify and rejects a mismatched user key', async () => {
  mocks.verify.mockImplementationOnce(async (draft) => draft)
  render(<StudioSetup onComplete={vi.fn()} />)
  fireEvent.change(url(), { target: { value: 'https://service.test' } })
  fireEvent.click(screen.getByRole('button', { name: 'advanced' }))
  fireEvent.change(screen.getByLabelText('settings:fields.rootApiKey'), {
    target: { value: 'root-secret' },
  })
  expect(screen.queryByText('choose-directory-user')).toBeNull()
  fireEvent.click(verifyButton())
  fireEvent.click(await screen.findByText('choose-directory-user'))
  expect(key().value).toBe('')
  expect(screen.queryByRole('button', { name: 'enter' })).toBeNull()
  mocks.verify.mockImplementationOnce(async (draft) => ({
    ...draft,
    accountId: 'other',
    userId: 'bob',
  }))
  fireEvent.change(key(), { target: { value: 'wrong-user-key' } })
  fireEvent.click(verifyButton())
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toContain(
      'directoryIdentityMismatch',
    ),
  )
  expect(screen.queryByRole('button', { name: 'enter' })).toBeNull()
})

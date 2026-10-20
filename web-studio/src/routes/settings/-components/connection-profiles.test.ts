// @vitest-environment jsdom
import * as React from 'react'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ConnectionProfile } from '#/lib/connection/profiles'
import {
  ConnectionProfilesList,
  groupedConnectionProfiles,
} from './connection-profiles'

const connectionState = vi.hoisted(() => ({
  profiles: [] as ConnectionProfile[],
  activeProfileId: 'active',
  saveProfile: vi.fn(),
  activateProfile: vi.fn(),
  deleteProfile: vi.fn(),
}))
const verify = vi.hoisted(() => vi.fn())
const directoryConnections = vi.hoisted(
  () => [] as Array<{ serviceSelection: string; baseUrl: string }>,
)
vi.mock('#/lib/connection/onboarding', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  verifyStudioSetup: verify,
}))
vi.mock('#/components/setup-identity-directory', () => ({
  SetupIdentityDirectory: ({
    connection,
    onSelect,
  }: {
    connection: { serviceSelection: string; baseUrl: string }
    onSelect: (identity: { accountId: string; userId: string }) => void
  }) => {
    directoryConnections.push(connection)
    return React.createElement(
      'button',
      {
        type: 'button',
        onClick: () => onSelect({ accountId: 'team', userId: 'bob' }),
      },
      'Select Bob',
    )
  },
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    to,
    children,
    ...props
  }: {
    to: string
    children: React.ReactNode
  }) => React.createElement('a', { href: to, ...props }, children),
}))

vi.mock('#/hooks/use-app-connection', () => ({
  useAppConnection: () => connectionState,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const hosted = (
  id: string,
  accountId: string,
  userId = 'wld2',
  apiKey = 'key',
): ConnectionProfile => ({
  id,
  name: id,
  connection: {
    serviceSelection: 'volcengine',
    baseUrl: 'https://api.vikingdb.cn-beijing.volces.com/openviking',
    apiKey,
    adminApiKey: '',
    accountId,
    userId,
  },
})

beforeEach(() => {
  vi.clearAllMocks()
  directoryConnections.length = 0
  verify.mockReset()
  connectionState.profiles = []
  connectionState.activeProfileId = 'active'
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('groups identical connections without losing any saved profile', () => {
  const profiles = [
    hosted('duplicate', 'study'),
    hosted('active', 'study'),
    hosted('other-user', 'study', 'alice'),
    hosted('other-space', 'production'),
  ]
  expect(
    groupedConnectionProfiles(profiles, 'active').map((group) =>
      group.map((profile) => profile.id),
    ),
  ).toEqual([['active', 'duplicate'], ['other-user'], ['other-space']])
})

it('keeps unverified default identities separate when their keys differ', () => {
  connectionState.profiles = [
    hosted('active', 'default', 'default', 'first-key'),
    hosted('other', 'default', 'default', 'second-key'),
  ]

  expect(
    groupedConnectionProfiles(
      connectionState.profiles,
      connectionState.activeProfileId,
    ).map((group) => group.map((profile) => profile.id)),
  ).toEqual([['active'], ['other']])

  render(React.createElement(ConnectionProfilesList))
  expect(screen.getAllByRole('button', { name: 'profiles.edit' })).toHaveLength(
    2,
  )
  fireEvent.click(
    screen.getAllByRole('button', { name: 'profiles.activate' })[1],
  )
  expect(connectionState.activateProfile).toHaveBeenCalledWith('other')
})

it('compacts default/default and shows other hosted account/user identities', () => {
  connectionState.profiles = [
    hosted('personal', 'default', 'default'),
    hosted('enterprise-alice', 'study', 'alice'),
    hosted('enterprise-bob', 'study', 'bob'),
  ]

  render(React.createElement(ConnectionProfilesList))

  expect(screen.getByText('[default]')).toBeTruthy()
  expect(screen.queryByText('[default/default]')).toBeNull()
  expect(screen.getByText('[study/alice]')).toBeTruthy()
  expect(screen.getByText('[study/bob]')).toBeTruthy()
})

it('lets every record in an identical connection group be managed', () => {
  connectionState.profiles = [
    hosted('duplicate', 'default', 'default'),
    hosted('active', 'default', 'default'),
  ]

  const { container } = render(React.createElement(ConnectionProfilesList))
  const group = container.querySelector('details')
  expect(group).not.toBeNull()
  expect(group?.open).toBe(false)
  expect(within(group!).getByText('profiles.title · 2')).toBeTruthy()
  expect(
    within(group!.querySelector('summary')!).getByText('[default]'),
  ).toBeTruthy()

  fireEvent.click(group!.querySelector('summary')!)
  expect(group?.open).toBe(true)
  expect(within(group!).queryAllByText('[default]')).toHaveLength(3)
  expect(within(group!).queryByText('[default/default]')).toBeNull()
  expect(
    within(group!).getAllByRole('button', { name: 'profiles.edit' }),
  ).toHaveLength(2)
  expect(
    within(group!).getAllByRole('button', { name: 'profiles.delete' }),
  ).toHaveLength(2)
  fireEvent.click(
    within(group!).getAllByRole('button', { name: 'profiles.activate' })[1],
  )
  expect(connectionState.activateProfile).toHaveBeenCalledWith('duplicate')
})

it('edits a legacy hosted profile as an open-source connection', () => {
  connectionState.profiles = [
    hosted('active', 'default'),
    hosted('old', 'study'),
  ]

  render(React.createElement(ConnectionProfilesList))
  fireEvent.click(screen.getAllByRole('button', { name: 'profiles.edit' })[1])
  expect(screen.queryByLabelText('serviceType')).toBeNull()
  fireEvent.change(screen.getByLabelText('profiles.fields.baseUrl'), {
    target: { value: 'http://192.0.2.1:1933' },
  })
  fireEvent.change(screen.getByLabelText('profiles.fields.adminApiKey'), {
    target: { value: 'root-key' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'profiles.save' }))

  expect(connectionState.saveProfile).toHaveBeenCalledWith(
    expect.objectContaining({
      id: 'old',
      connection: expect.objectContaining({
        serviceSelection: 'opensource',
        baseUrl: 'http://192.0.2.1:1933',
        adminApiKey: 'root-key',
        accountId: 'study',
      }),
    }),
  )
})

it('lists identities for a re-pointed legacy hosted profile as open source', () => {
  connectionState.profiles = [hosted('active', 'default')]

  render(React.createElement(ConnectionProfilesList))
  fireEvent.click(screen.getByRole('button', { name: 'profiles.edit' }))
  fireEvent.change(screen.getByLabelText('profiles.fields.baseUrl'), {
    target: { value: 'http://192.0.2.1:1933' },
  })
  fireEvent.change(screen.getByLabelText('profiles.fields.adminApiKey'), {
    target: { value: 'root-key' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'onboarding:verify' }))

  expect(directoryConnections.at(-1)).toEqual(
    expect.objectContaining({
      serviceSelection: 'opensource',
      baseUrl: 'http://192.0.2.1:1933',
    }),
  )
})

it('shows only the address and user key for an official hosted address', () => {
  connectionState.profiles = [hosted('active', 'default')]

  render(React.createElement(ConnectionProfilesList))
  fireEvent.click(screen.getByRole('button', { name: 'profiles.edit' }))
  expect(screen.getByLabelText('profiles.fields.baseUrl')).toBeTruthy()
  expect(screen.getByLabelText('profiles.fields.apiKey')).toBeTruthy()
  expect(screen.queryByLabelText('profiles.fields.adminApiKey')).toBeNull()
  expect(screen.queryByLabelText('profiles.fields.accountId')).toBeNull()
  expect(screen.queryByLabelText('profiles.fields.userId')).toBeNull()

  fireEvent.change(screen.getByLabelText('profiles.fields.baseUrl'), {
    target: { value: 'http://192.0.2.1:1933' },
  })
  expect(screen.getByLabelText('profiles.fields.adminApiKey')).toBeTruthy()
})

it('routes adding a profile to the connection wizard without creating a modal draft', () => {
  render(React.createElement(ConnectionProfilesList))
  expect(
    screen.getByRole('link', { name: 'profiles.add' }).getAttribute('href'),
  ).toBe('/config')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(connectionState.saveProfile).not.toHaveBeenCalled()
})

it('preserves a saved hosted proxy address when editing its name', () => {
  const profile = hosted('proxy', 'team', 'alice')
  profile.connection.baseUrl = 'https://hosted-proxy.example/openviking'
  connectionState.profiles = [profile]
  render(React.createElement(ConnectionProfilesList))
  fireEvent.click(screen.getByRole('button', { name: 'profiles.edit' }))
  expect(screen.getByDisplayValue(profile.connection.baseUrl)).toBeTruthy()
  fireEvent.change(screen.getByLabelText('profiles.name'), {
    target: { value: 'Renamed' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'profiles.save' }))
  expect(connectionState.saveProfile).toHaveBeenCalledWith({
    ...profile,
    name: 'Renamed',
  })
  expect(verify).not.toHaveBeenCalled()
})

function selectDirectoryUser() {
  const profile = hosted('active', 'team', 'alice', 'alice-key')
  profile.connection.serviceSelection = 'opensource'
  profile.connection.baseUrl = 'https://service.example'
  profile.connection.adminApiKey = 'root-key'
  connectionState.profiles = [profile]
  render(React.createElement(ConnectionProfilesList))
  fireEvent.click(screen.getByRole('button', { name: 'profiles.edit' }))
  fireEvent.click(screen.getByRole('button', { name: 'onboarding:verify' }))
  fireEvent.click(screen.getByRole('button', { name: 'Select Bob' }))
  return {
    ...profile,
    connection: { ...profile.connection, userId: 'bob', apiKey: '' },
  }
}

it.each([
  { accountId: 'other-team', userId: 'bob' },
  { accountId: 'team', userId: 'alice' },
])(
  'rejects a key for $accountId/$userId and then saves a matching key',
  async (identity) => {
    const expected = selectDirectoryUser()
    const key = screen.getByLabelText('profiles.fields.apiKey')
    expect((key as HTMLInputElement).value).toBe('')
    verify.mockResolvedValueOnce({ ...expected.connection, ...identity })
    fireEvent.change(key, { target: { value: 'alice-key' } })
    fireEvent.click(screen.getByRole('button', { name: 'profiles.save' }))
    await screen.findByText('onboarding:directoryIdentityMismatch')
    expect(connectionState.saveProfile).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeTruthy()
    verify.mockResolvedValueOnce({ ...expected.connection, apiKey: 'bob-key' })
    fireEvent.change(key, { target: { value: 'bob-key' } })
    fireEvent.click(screen.getByRole('button', { name: 'profiles.save' }))
    await waitFor(() =>
      expect(connectionState.saveProfile).toHaveBeenCalledWith({
        ...expected,
        connection: { ...expected.connection, apiKey: 'bob-key' },
      }),
    )
  },
)

it('saves a directory selection with no data key for management without probing data access', () => {
  const expected = selectDirectoryUser()
  fireEvent.click(screen.getByRole('button', { name: 'profiles.save' }))
  expect(connectionState.saveProfile).toHaveBeenCalledWith(expected)
  expect(verify).not.toHaveBeenCalled()
})

it.each(['edit', 'cancel'])(
  'ignores verification results after %s',
  async (action) => {
    const expected = selectDirectoryUser()
    let resolve!: (value: unknown) => void
    verify.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        }),
    )
    fireEvent.change(screen.getByLabelText('profiles.fields.apiKey'), {
      target: { value: 'bob-key' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'profiles.save' }))
    if (action === 'edit') {
      fireEvent.change(screen.getByLabelText('profiles.name'), {
        target: { value: 'Changed' },
      })
    } else {
      fireEvent.click(screen.getByRole('button', { name: 'profiles.cancel' }))
    }
    await act(async () =>
      resolve({ ...expected.connection, apiKey: 'bob-key' }),
    )
    expect(connectionState.saveProfile).not.toHaveBeenCalled()
  },
)

it('retains the draft and redacts keys when verification fails', async () => {
  selectDirectoryUser()
  verify.mockRejectedValue(new Error('Denied bob-key using root-key'))
  fireEvent.change(screen.getByLabelText('profiles.fields.apiKey'), {
    target: { value: 'bob-key' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'profiles.save' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain('Denied')
  expect(alert.textContent).not.toContain('bob-key')
  expect(alert.textContent).not.toContain('root-key')
  expect(connectionState.saveProfile).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog')).toBeTruthy()
})

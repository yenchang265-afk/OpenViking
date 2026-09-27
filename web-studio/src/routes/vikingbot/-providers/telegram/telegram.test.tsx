// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { AllowedUsersSettings } from './allowed-users-settings'
import { parseAllowList, formatAllowList } from './allow-list'
import { TelegramSetup } from './telegram-setup'
import { TokenRotation } from './token-rotation'
import { getProvider, upcomingProviders } from '../registry'
import type { Connection } from '../../-api'
import en from '#/i18n/locales/en/vikingbot'

const api = vi.hoisted(() => ({
  createConnection: vi.fn(),
  updateConnectionSettings: vi.fn(),
  rotateCredentials: vi.fn(),
  getBotUsers: vi.fn(),
}))
vi.mock('../../-api', () => api)
vi.mock('#/hooks/use-app-connection', () => ({
  useAppConnection: () => ({ identityScopeKey: 'scope' }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) => {
      const text = key
        .split('.')
        .reduce<unknown>(
          (node, part) => (node as Record<string, unknown> | undefined)?.[part],
          en,
        )
      return String(text ?? key).replace(
        /\{\{(\w+)\}\}/g,
        (_, name: string) => values?.[name] ?? '',
      )
    },
  }),
}))

const TOKEN = '123456789:' + 'A'.repeat(35)
const connection: Connection = {
  id: 'c',
  type: 'telegram',
  app_id: '123456789',
  bot_name: 'Viking',
  bot_username: 'viking_bot',
  enabled: true,
  step: 0,
  revision: 3,
  identity_user: 'bot-user',
  settings: { allow_from: ['alice_01', '42'] },
  status: { state: 'connected' },
}

function wrap(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('allow list', () => {
  it('splits on commas and whitespace and drops duplicates', () => {
    expect(parseAllowList(' @alice, 42\n@alice  bobby7 ,')).toEqual([
      '@alice',
      '42',
      'bobby7',
    ])
  })
  it('shows usernames with @ and IDs as-is', () => {
    expect(formatAllowList(['alice_01', '42'])).toEqual(['@alice_01', '42'])
  })
})

it('registers Telegram as an available provider', () => {
  expect(getProvider('telegram')?.Setup).toBe(TelegramSetup)
  expect(upcomingProviders).not.toContain('Telegram')
})

it('requires a token, an allowed user and a runtime user before connecting', async () => {
  api.getBotUsers.mockResolvedValue([{ user_id: 'bot-user', available: true }])
  api.createConnection.mockResolvedValue(connection)
  const changed = vi.fn()
  wrap(<TelegramSetup onChange={changed} onClose={vi.fn()} />)
  const connect = screen.getByRole<HTMLButtonElement>('button', {
    name: en.telegram.connect,
  })
  fireEvent.change(screen.getByLabelText(en.telegram.token), {
    target: { value: ` ${TOKEN} ` },
  })
  await screen.findByRole('option', { name: 'bot-user' })
  expect(connect.disabled).toBe(true)
  fireEvent.change(screen.getByLabelText(en.telegram.allowFrom), {
    target: { value: '@alice_01, 42' },
  })
  expect(connect.disabled).toBe(false)
  fireEvent.click(connect)
  await waitFor(() => expect(changed).toHaveBeenCalledWith(connection))
  expect(api.createConnection).toHaveBeenCalledWith({
    type: 'telegram',
    credentials: { token: TOKEN },
    user_id: 'bot-user',
    settings: { allow_from: ['@alice_01', '42'] },
  })
})

it('shows the connected bot link, allowlist and connection error', () => {
  wrap(
    <TelegramSetup
      connection={{
        ...connection,
        status: { state: 'connecting', last_error: 'Cannot connect' },
      }}
      onChange={vi.fn()}
      onClose={vi.fn()}
    />,
  )
  expect(
    screen.getByRole('link', { name: /@viking_bot/ }).getAttribute('href'),
  ).toBe('https://t.me/viking_bot')
  expect(screen.getByText('@alice_01, 42')).toBeTruthy()
  expect(screen.getByRole('alert').textContent).toBe('Cannot connect')
  expect(api.getBotUsers).not.toHaveBeenCalled()
})

it('saves an edited allowlist against the connection revision', async () => {
  api.updateConnectionSettings.mockResolvedValue(connection)
  const saved = vi.fn()
  wrap(<AllowedUsersSettings connection={connection} onSaved={saved} />)
  fireEvent.click(
    screen.getByRole('button', { name: en.telegram.allowedUsers }),
  )
  const field = screen.getByLabelText<HTMLTextAreaElement>(
    en.telegram.allowFrom,
  )
  expect(field.value).toBe('@alice_01\n42')
  const save = screen.getByRole<HTMLButtonElement>('button', {
    name: en.telegram.save,
  })
  expect(save.disabled).toBe(true)
  fireEvent.change(field, { target: { value: '' } })
  expect(save.disabled).toBe(true)
  fireEvent.change(field, { target: { value: '@alice_01\n@bobby7' } })
  fireEvent.click(save)
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1))
  expect(api.updateConnectionSettings).toHaveBeenCalledWith(connection, {
    allow_from: ['@alice_01', '@bobby7'],
  })
})

it('keeps the dialog open and shows the error when a token is rejected', async () => {
  api.rotateCredentials.mockRejectedValueOnce(
    new Error('This token belongs to a different Telegram bot'),
  )
  const saved = vi.fn()
  wrap(<TokenRotation connection={connection} onSaved={saved} />)
  fireEvent.click(screen.getByRole('button', { name: en.telegram.rotate }))
  fireEvent.change(screen.getByLabelText(en.telegram.token), {
    target: { value: TOKEN },
  })
  fireEvent.click(screen.getByRole('button', { name: en.telegram.saveToken }))
  expect((await screen.findByRole('alert')).textContent).toContain(
    'different Telegram bot',
  )
  expect(saved).not.toHaveBeenCalled()
  expect(api.rotateCredentials).toHaveBeenCalledWith(
    connection,
    { token: TOKEN },
    'bot-user',
  )
})

import type { ComponentType } from 'react'
import type { Connection } from '../-api'
import { AllowedUsersSettings } from './telegram/allowed-users-settings'
import { TelegramSetup } from './telegram/telegram-setup'
import { TokenRotation } from './telegram/token-rotation'

type ConnectionEditorProps = {
  connection: Connection
  onSaved: () => void
}

// Each supported platform owns its setup and credential UI.
export type Provider = {
  label: string
  addLabel: string
  Setup: ComponentType<{
    connection?: Connection
    onChange: (connection: Connection) => void
    onClose: () => void
  }>
  Credentials?: ComponentType<ConnectionEditorProps>
  Settings: ComponentType<ConnectionEditorProps>
  summary: (connection: Connection) => string
}

export const providers: Record<string, Provider> = {
  telegram: {
    label: 'telegram.label',
    addLabel: 'telegram.add',
    Setup: TelegramSetup,
    Credentials: TokenRotation,
    Settings: AllowedUsersSettings,
    summary: () => 'telegram.summary',
  },
}
export const upcomingProviders = ['Slack', 'DingTalk', 'Discord']
export function getProvider(type?: string) {
  return type && Object.hasOwn(providers, type) ? providers[type] : undefined
}

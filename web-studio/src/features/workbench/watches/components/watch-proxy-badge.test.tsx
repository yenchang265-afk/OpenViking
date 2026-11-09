// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WatchProxyBadge } from '#/features/workbench/watches/components/watch-proxy-badge'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { host?: string }) =>
      options?.host ? `${key}:${options.host}` : key,
  }),
}))

afterEach(cleanup)

describe('WatchProxyBadge', () => {
  it('renders nothing for a direct route', () => {
    const { container } = render(
      <WatchProxyBadge proxyHost={null} viaProxy={false} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('names the proxy host for root users', () => {
    render(<WatchProxyBadge proxyHost="proxy.corp:8080" viaProxy />)
    expect(screen.getByText('proxy.badge').getAttribute('title')).toBe(
      'proxy.hostHint:proxy.corp:8080',
    )
  })

  it('shows a generic hint when the host is withheld', () => {
    render(<WatchProxyBadge proxyHost={null} viaProxy />)
    expect(screen.getByText('proxy.badge').getAttribute('title')).toBe(
      'proxy.hint',
    )
  })
})

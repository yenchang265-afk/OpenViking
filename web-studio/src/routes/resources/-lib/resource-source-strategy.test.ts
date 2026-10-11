import { describe, expect, it } from 'vitest'

import {
  buildRemoteSourceRequestOptions,
  getRemoteResourceCapabilities,
} from './resource-source-strategy'
import type { RemoteSourceOptionState } from './resource-source-strategy'

const DEFAULT_STATE: RemoteSourceOptionState = {
  git: {
    authMode: 'public',
    refMode: 'branch',
    refValue: '',
    proxy: '',
    supportsHttpAuth: false,
    supportsProxy: false,
    token: '',
    username: 'oauth2',
  },
  watchEnabled: false,
  web: {
    allowExternalLinks: false,
    depth: '1',
    excludePaths: '',
    includePaths: '',
    maxPages: '50',
    mode: 'auto',
    skipDownloadLinks: true,
  },
}

describe('remote resource source strategy', () => {
  it('declares TOS as an exact, connector-only, non-watchable source', () => {
    expect(getRemoteResourceCapabilities('tos')).toEqual({
      exactDestination: true,
      nativeOptions: false,
      watch: false,
    })
    expect(buildRemoteSourceRequestOptions('tos', DEFAULT_STATE)).toEqual({
      add_type: 'tos',
    })
  })

  it('forwards recursive web limits for server validation', () => {
    const state: RemoteSourceOptionState = {
      ...DEFAULT_STATE,
      web: {
        ...DEFAULT_STATE.web,
        depth: '-1',
        mode: 'recursive',
      },
    }

    expect(buildRemoteSourceRequestOptions('webPage', state)).toEqual({
      args: {
        allow_external_links: false,
        depth: -1,
        exclude_paths: undefined,
        include_paths: undefined,
        max_pages: 50,
        site: false,
        skip_download_links: true,
      },
    })
  })

  it('builds site filters as top-level comma-delimited patterns', () => {
    const state: RemoteSourceOptionState = {
      ...DEFAULT_STATE,
      web: {
        ...DEFAULT_STATE.web,
        excludePaths: '/archive\n/private',
        includePaths: '/docs, /zh/',
        mode: 'site',
      },
    }

    expect(buildRemoteSourceRequestOptions('webPage', state)).toEqual({
      args: {
        max_pages: 50,
        site: true,
      },
      exclude: '/archive,/private',
      include: '/docs,/zh/',
    })
  })

  it('does not build token authentication for a non-HTTPS Git source', () => {
    const state: RemoteSourceOptionState = {
      ...DEFAULT_STATE,
      git: {
        ...DEFAULT_STATE.git,
        authMode: 'token',
        token: 'secret-token',
      },
    }

    expect(buildRemoteSourceRequestOptions('git', state)).toEqual({ args: {} })
  })

  it('sends an Azure DevOps PAT and proxy together in auth_config', () => {
    const state: RemoteSourceOptionState = {
      ...DEFAULT_STATE,
      git: {
        ...DEFAULT_STATE.git,
        authMode: 'token',
        proxy: ' http://proxy.corp.example:8080 ',
        supportsHttpAuth: true,
        supportsProxy: true,
        token: ' azure-pat ',
        username: '',
      },
    }

    expect(buildRemoteSourceRequestOptions('git', state)).toEqual({
      args: {
        auth_config: {
          proxy: 'http://proxy.corp.example:8080',
          token: 'azure-pat',
          username: 'oauth2',
        },
      },
    })
  })

  it('sends a proxy without credentials for a public repository', () => {
    const state: RemoteSourceOptionState = {
      ...DEFAULT_STATE,
      git: {
        ...DEFAULT_STATE.git,
        proxy: 'socks5h://proxy.example:1080',
        supportsProxy: true,
        token: 'stale-token',
      },
    }

    expect(buildRemoteSourceRequestOptions('git', state)).toEqual({
      args: { auth_config: { proxy: 'socks5h://proxy.example:1080' } },
    })
  })

  it('does not send a proxy for an SSH Git source', () => {
    const state: RemoteSourceOptionState = {
      ...DEFAULT_STATE,
      git: { ...DEFAULT_STATE.git, proxy: 'http://proxy.example:8080' },
    }

    expect(buildRemoteSourceRequestOptions('git', state)).toEqual({ args: {} })
  })
})

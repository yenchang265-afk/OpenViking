import { describe, expect, it } from 'vitest'

import {
  detectRemoteResourceKind,
  stripGitUrlUsername,
} from './resource-source'

describe('detectRemoteResourceKind', () => {
  it.each([
    ['https://github.com/volcengine/OpenViking', 'git'],
    ['git@github.com:volcengine/OpenViking.git', 'git'],
    ['https://gitlab.com/group/repo.git', 'git'],
    ['https://git.example.com/group/repo.git', 'git'],
    ['https://dev.azure.com/org/project/_git/repo', 'git'],
    ['https://org@dev.azure.com/org/project/_git/repo', 'git'],
    ['https://tfs.corp.example/tfs/DefaultCollection/Project/_git/repo', 'git'],
    ['https://example.com/sitemap.xml', 'webFeed'],
    ['https://example.com/feed.atom', 'webFeed'],
    ['https://example.com/guide.pdf', 'remoteFile'],
    ['https://example.com/docs/getting-started', 'webPage'],
    ['tos://bucket/docs', 'tos'],
    ['custom://workspace/source', 'unknown'],
    ['', 'unknown'],
  ] as const)('detects %s as %s', (source, expected) => {
    expect(detectRemoteResourceKind(source)).toBe(expected)
  })

  it('does not classify a GitHub blob URL as a repository', () => {
    expect(
      detectRemoteResourceKind(
        'https://github.com/volcengine/OpenViking/blob/main/README.md',
      ),
    ).toBe('remoteFile')
  })

  it('does not classify an Azure DevOps file browser URL as a repository', () => {
    expect(
      detectRemoteResourceKind(
        'https://dev.azure.com/org/project/_git/repo?path=/README.md',
      ),
    ).toBe('webPage')
    expect(
      detectRemoteResourceKind(
        'https://tfs.corp.example/tfs/Collection/Project/_git/repo?path=/README.md',
      ),
    ).toBe('webPage')
  })
})

describe('stripGitUrlUsername', () => {
  it('drops the organization username from an Azure DevOps clone URL', () => {
    expect(
      stripGitUrlUsername('https://org@dev.azure.com/org/My%20Project/_git/repo'),
    ).toBe('https://dev.azure.com/org/My%20Project/_git/repo')
  })

  it.each([
    'https://dev.azure.com/org/project/_git/repo',
    'https://user:secret@git.example.com/org/repo.git',
    'git@ssh.dev.azure.com:v3/org/project/repo',
    'ssh://git@git.example.com/org/repo.git',
    'not a url',
  ])('leaves %s unchanged', (source) => {
    expect(stripGitUrlUsername(source)).toBe(source)
  })
})

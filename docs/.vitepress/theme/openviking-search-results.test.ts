import assert from 'node:assert/strict'
import test from 'node:test'

import {
  enrichSearchResultsWithLocalTitles,
  localizeSearchResultTitles
} from './openviking-search-results.ts'

test('uses the localized docs index title for Chinese remote results', () => {
  const results = enrichSearchResultsWithLocalTitles(
    [
      {
        relativePath: 'agent-integrations/08-community-plugins.md',
        snippet: '這是一份面向 OpenViking 使用者的社群外掛參考文件。',
        title: 'Community Plugins',
        url: '/zh/agent-integrations/08-community-plugins'
      }
    ],
    [
      {
        locale: 'zh',
        path: 'zh/agent-integrations/08-community-plugins.md',
        text: '社群外掛',
        title: '社群外掛',
        url: '/zh/agent-integrations/08-community-plugins'
      }
    ],
    'zh'
  )

  assert.equal(results[0].title, '社群外掛')
})

test('keeps remote results when local title lookup fails', async () => {
  const remoteResults = [
    {
      relativePath: 'agent-integrations/08-community-plugins.md',
      snippet: 'remote snippet',
      title: 'Community Plugins',
      url: '/zh/agent-integrations/08-community-plugins'
    }
  ]

  const results = await localizeSearchResultTitles(
    remoteResults,
    'zh',
    async () => {
      throw new Error('local index unavailable')
    }
  )

  assert.deepEqual(results, remoteResults)
})

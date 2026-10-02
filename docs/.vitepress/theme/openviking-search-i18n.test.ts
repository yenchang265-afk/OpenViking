import assert from 'node:assert/strict'
import test from 'node:test'

import { searchCopyForLocale } from './openviking-search-i18n.ts'

test('returns Chinese search UI copy for zh docs', () => {
  const copy = searchCopyForLocale('zh')

  assert.equal(copy.trigger, '搜尋文件')
  assert.equal(copy.compactTrigger, '搜索')
  assert.equal(copy.inputLabel, '搜尋 Business Data Platform 文件')
  assert.equal(copy.modes.semantic.label, '語義搜尋')
  assert.equal(copy.modes.keyword.placeholder, '搜尋文件中的精確詞句')
  assert.equal(copy.empty.noResults, '未找到相關結果。')
  assert.equal(copy.notice('timeout', 2), 'Business Data Platform 搜尋超時。正在顯示本地文件結果。')
  assert.equal(copy.notice('rate_limited', 0), 'Business Data Platform 搜尋請求過多。未找到本地結果。')
})

test('keeps English search UI copy as the default locale', () => {
  const copy = searchCopyForLocale('en')

  assert.equal(copy.trigger, 'Search docs')
  assert.equal(copy.compactTrigger, 'Search')
  assert.equal(copy.inputLabel, 'Search Business Data Platform docs')
  assert.equal(copy.modes.semantic.label, 'Semantic')
  assert.equal(copy.empty.initial, 'Type a query to search the current language docs.')
})

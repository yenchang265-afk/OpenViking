import { describe, expect, it } from 'vitest'

import { resources, supportedLanguages, toSupportedLanguage } from './resources'

describe('i18n resources', () => {
  it('only ships English and Traditional Chinese', () => {
    expect(supportedLanguages).toEqual(['en', 'zh-TW'])
  })

  it.each(['zh', 'zh-CN', 'zh-cn', 'zh-Hans', 'zh-HK', 'zh-TW'])(
    'maps %s to zh-TW',
    (lng) => {
      expect(toSupportedLanguage(lng)).toBe('zh-TW')
    },
  )

  it.each(['en', 'en-US', 'fr'])('leaves %s unchanged', (lng) => {
    expect(toSupportedLanguage(lng)).toBe(lng)
  })
})

function flatten(value: unknown, prefix = ''): Record<string, string> {
  if (typeof value === 'string') return { [prefix]: value }
  return Object.assign(
    {},
    ...Object.entries(value as Record<string, unknown>).map(([key, child]) =>
      flatten(child, prefix ? `${prefix}.${key}` : key),
    ),
  )
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{-?\s*([^},\s]+)[^}]*\}\}/g)]
    .map((match) => match[1])
    .sort()
}

describe('all Studio translation resources', () => {
  const english = flatten(resources.en)
  const chinese = flatten(resources['zh-TW'])

  it('registers matching keys in both languages', () => {
    expect(Object.keys(chinese).sort()).toEqual(Object.keys(english).sort())
  })

  it('has no empty translations or mismatched interpolation variables', () => {
    for (const [key, text] of Object.entries(english)) {
      expect(text.trim(), key).not.toBe('')
      expect(chinese[key].trim(), key).not.toBe('')
      expect(placeholders(chinese[key] ?? ''), key).toEqual(placeholders(text))
    }
  })
})

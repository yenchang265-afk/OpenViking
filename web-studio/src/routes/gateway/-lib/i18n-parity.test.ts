import { describe, expect, it } from 'vitest'

import en from '#/i18n/locales/en'
import zhTW from '#/i18n/locales/zh-TW'

function flatten(value: unknown, prefix = ''): Record<string, string> {
  if (typeof value === 'string') return { [prefix]: value }
  return Object.entries(value as Record<string, unknown>).reduce(
    (entries, [key, child]) => ({
      ...entries,
      ...flatten(child, prefix ? `${prefix}.${key}` : key),
    }),
    {},
  )
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{(\w+)\}\}/g)].map((match) => match[1]).sort()
}

describe('gateway translations', () => {
  const english = flatten(en.gateway)
  const chinese = flatten(zhTW.gateway)

  it('have the same keys in English and Chinese', () => {
    expect(Object.keys(chinese).sort()).toEqual(Object.keys(english).sort())
  })

  it('use the same interpolation values and no empty strings', () => {
    for (const [key, text] of Object.entries(english)) {
      expect(text, key).not.toBe('')
      expect(chinese[key], key).not.toBe('')
      expect(placeholders(chinese[key] ?? ''), key).toEqual(placeholders(text))
    }
  })

  it('label the sidebar entry in both languages', () => {
    expect(en.appShell.footer.gateway).toBe('Business Data Platform Gateway')
    expect(zhTW.appShell.footer.gateway).toBe('Business Data Platform 閘道器')
  })

  it('summarize compaction and tool counts with their values', () => {
    for (const locale of [en, zhTW]) {
      const { summary } = locale.gateway.profiles
      expect(placeholders(summary.compactionOn)).toEqual(['percent'])
      for (const key of ['toolsEnabled_one', 'toolsEnabled_other'] as const) {
        expect(placeholders(summary[key])).toEqual(['count'])
      }
    }
  })
})

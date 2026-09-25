import { describe, expect, it } from 'vitest'

import { supportedLanguages, toSupportedLanguage } from './resources'

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

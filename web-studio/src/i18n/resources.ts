import en from './locales/en'
import zhTW from './locales/zh-TW'

export const defaultLanguage = 'en' as const

export const resources = {
  en,
  'zh-TW': zhTW,
} as const

export type SupportedLanguage = keyof typeof resources

export const supportedLanguages = Object.keys(resources) as SupportedLanguage[]

// Chinese UI is Traditional only: map zh, zh-CN, zh-HK, … (including a
// previously cached zh-CN) to zh-TW.
export function toSupportedLanguage(lng: string): string {
  return lng.toLowerCase().startsWith('zh') ? 'zh-TW' : lng
}

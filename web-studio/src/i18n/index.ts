import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import {
  defaultLanguage,
  resources,
  supportedLanguages,
  toSupportedLanguage,
} from './resources'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    defaultNS: 'common',
    detection: {
      convertDetectedLanguage: toSupportedLanguage,
    },
    fallbackLng: defaultLanguage,
    interpolation: {
      escapeValue: false,
    },
    ns: Object.keys(resources[defaultLanguage]),
    resources,
    returnNull: false,
    supportedLngs: supportedLanguages,
  })

const syncDocumentLanguage = (lng: string) => {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lng
  }
}

syncDocumentLanguage(i18n.resolvedLanguage ?? defaultLanguage)
i18n.on('languageChanged', syncDocumentLanguage)

export default i18n

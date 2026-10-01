import type { SearchLocale, SearchMode } from './openviking-search-results'

export type RemoteSearchFailureReason = 'rate_limited' | 'timeout' | 'unavailable'

type ModeCopy = {
  label: string
  placeholder: string
}

type SearchCopy = {
  compactTrigger: string
  dialogLabel: string
  empty: {
    initial: string
    loading: string
    noResults: string
  }
  inputLabel: string
  modeLabel: string
  modeOptionsLabel: string
  modes: Record<SearchMode, ModeCopy>
  notice: (reason: RemoteSearchFailureReason, localResultCount: number) => string
  trigger: string
}

const searchCopy: Record<SearchLocale, SearchCopy> = {
  en: {
    compactTrigger: 'Search',
    dialogLabel: 'OpenViking docs search',
    empty: {
      initial: 'Type a query to search the current language docs.',
      loading: 'Searching...',
      noResults: 'No results found.'
    },
    inputLabel: 'Search OpenViking docs',
    modeLabel: 'Search mode',
    modeOptionsLabel: 'Search mode options',
    modes: {
      file: {
        label: 'File',
        placeholder: 'Find docs by path or filename'
      },
      keyword: {
        label: 'Keyword',
        placeholder: 'Search exact words in the docs'
      },
      semantic: {
        label: 'Semantic',
        placeholder: 'Ask a question about the docs'
      }
    },
    notice: (reason, localResultCount) => {
      const prefix =
        reason === 'rate_limited'
          ? 'OpenViking search is rate limited.'
          : reason === 'timeout'
            ? 'OpenViking search timed out.'
            : 'OpenViking search is unavailable.'

      return localResultCount > 0
        ? `${prefix} Showing local docs results.`
        : `${prefix} No local results found.`
    },
    trigger: 'Search docs'
  },
  zh: {
    compactTrigger: '搜索',
    dialogLabel: 'OpenViking 文件搜尋',
    empty: {
      initial: '輸入關鍵詞，搜尋當前語言的文件。',
      loading: '搜索中...',
      noResults: '未找到相關結果。'
    },
    inputLabel: '搜尋 OpenViking 文件',
    modeLabel: '搜索模式',
    modeOptionsLabel: '搜尋模式選項',
    modes: {
      file: {
        label: '文件搜索',
        placeholder: '按路徑或檔名查詢文件'
      },
      keyword: {
        label: '關鍵詞搜尋',
        placeholder: '搜尋文件中的精確詞句'
      },
      semantic: {
        label: '語義搜尋',
        placeholder: '詢問文件內容'
      }
    },
    notice: (reason, localResultCount) => {
      const prefix =
        reason === 'rate_limited'
          ? 'OpenViking 搜尋請求過多。'
          : reason === 'timeout'
            ? 'OpenViking 搜尋超時。'
            : 'OpenViking 搜尋暫不可用。'

      return localResultCount > 0
        ? `${prefix}正在顯示本地文件結果。`
        : `${prefix}未找到本地結果。`
    },
    trigger: '搜尋文件'
  }
}

export function searchCopyForLocale(locale: SearchLocale) {
  return searchCopy[locale] ?? searchCopy.en
}

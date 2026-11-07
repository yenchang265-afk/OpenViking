import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getContentDownload } from '#/shared/api/ov-client'
import { resolveMarkdownAssetTarget } from '../lib/markdown-assets'
import type { EditorImage } from '../lib/editor-images'

const PREVIEW_CSP =
  "default-src 'none'; img-src blob: https: http:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"

/** A separate opaque origin plus CSP prevents edited HTML from executing code. */
export function HtmlEditPreview({
  content,
  uri,
  images,
}: {
  content: string
  uri: string
  images: EditorImage[]
}) {
  const { t } = useTranslation('resources')
  const [document, setDocument] = useState('')
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const urls: string[] = []
    const dom = new DOMParser().parseFromString(content, 'text/html')
    dom
      .querySelectorAll('base, meta[http-equiv="refresh" i]')
      .forEach((element) => element.remove())
    const csp = dom.createElement('meta')
    csp.httpEquiv = 'Content-Security-Policy'
    csp.content = PREVIEW_CSP
    dom.head.prepend(csp)
    setDocument('')
    const render = async () => {
      await Promise.all(
        Array.from(dom.querySelectorAll('img')).map(async (element) => {
          const src = element.getAttribute('src') ?? ''
          element.removeAttribute('srcset')
          const staged = images.find((image) => image.path === src)
          if (staged) {
            element.src = staged.previewUrl
            return
          }
          const target = resolveMarkdownAssetTarget(src, uri)
          if (target.kind !== 'viking') return
          element.removeAttribute('src')
          try {
            const response = await getContentDownload({
              query: { uri: target.value },
              responseType: 'blob',
              throwOnError: true,
              signal: controller.signal,
            })
            if (!active) return
            const url = URL.createObjectURL(response.data as Blob)
            urls.push(url)
            element.src = url
          } catch {
            /* Preserve alt text when an image cannot be loaded. */
          }
        }),
      )
      if (active)
        setDocument('<!doctype html>\n' + dom.documentElement.outerHTML)
    }
    void render()
    return () => {
      active = false
      controller.abort()
      urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [content, uri, images])
  return (
    <iframe
      title={t('filePreview.editor.htmlPreview')}
      sandbox=""
      referrerPolicy="no-referrer"
      srcDoc={document}
      className="h-full min-h-64 w-full rounded border bg-white"
    />
  )
}

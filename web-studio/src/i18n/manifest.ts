export function syncManifestLanguage(language: string) {
  const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]')
  if (!link) return
  const url = new URL(link.href, document.baseURI)
  if (
    url.origin !== window.location.origin ||
    !/\/manifest(?:\.zh-TW)?\.json$/.test(url.pathname)
  )
    return
  url.pathname = url.pathname.replace(
    /manifest(?:\.zh-TW)?\.json$/,
    language === 'zh-TW' ? 'manifest.zh-TW.json' : 'manifest.json',
  )
  if (link.href !== url.href) link.href = url.href
}

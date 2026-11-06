// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { HtmlEditPreview } from './html-edit-preview'
import { getContentDownload } from '#/shared/api/ov-client'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('#/shared/api/ov-client', () => ({ getContentDownload: vi.fn() }))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
it('renders user HTML in an opaque sandbox with a restrictive CSP', async () => {
  render(
    <HtmlEditPreview
      uri="viking://resources/demo/index.html"
      images={[]}
      content={
        '<base href="https://example.com"><meta http-equiv="refresh" content="0;url=https://example.com"><script>parent.alert(1)</script><h1>Preview</h1>'
      }
    />,
  )
  const frame = screen.getByTitle<HTMLIFrameElement>(
    'filePreview.editor.htmlPreview',
  )
  await waitFor(() => expect(frame.srcdoc).toContain('<h1>Preview</h1>'))
  expect(frame.getAttribute('sandbox')).toBe('')
  expect(frame.srcdoc).toContain("default-src 'none'")
  expect(frame.srcdoc).not.toContain('<base')
  expect(frame.srcdoc).not.toContain('http-equiv="refresh"')
  expect(frame.getAttribute('referrerpolicy')).toBe('no-referrer')
})
it('uses local staged previews and authenticated downloads for stored relative images', async () => {
  const revoke = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: () => 'blob:download',
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: revoke,
  })
  vi.mocked(getContentDownload).mockResolvedValue({
    data: new Blob(['image']),
  } as never)
  const { unmount } = render(
    <HtmlEditPreview
      uri="viking://resources/demo/index.html"
      images={[
        {
          path: 'assets/new.png',
          previewUrl: 'blob:staged',
          uri: '',
          alt: '',
          base64: '',
        },
      ]}
      content={
        '<img src="assets/new.png"><img src="./stored%23shot.png" srcset="other.png 2x">'
      }
    />,
  )
  const frame = screen.getByTitle<HTMLIFrameElement>(
    'filePreview.editor.htmlPreview',
  )
  await waitFor(() => expect(frame.srcdoc).toContain('blob:download'))
  expect(frame.srcdoc).toContain('blob:staged')
  expect(frame.srcdoc).not.toContain('srcset=')
  expect(getContentDownload).toHaveBeenCalledWith(
    expect.objectContaining({
      query: { uri: 'viking://resources/demo/stored#shot.png' },
      responseType: 'blob',
    }),
  )
  unmount()
  expect(revoke).toHaveBeenCalledWith('blob:download')
})

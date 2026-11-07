// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import {
  stageEditorImage,
  saveEditorImages,
  MAX_EDITOR_IMAGE_BYTES,
} from './editor-images'

const request = vi.hoisted(() => vi.fn())
vi.mock('#/shared/api/ov-client', () => ({
  deleteFs: vi.fn(),
  ovClient: { client: { post: request } },
  getOvResult: async (value: unknown) => value,
}))
afterEach(() => vi.clearAllMocks())
const uri = 'viking://resources/demo/note.md'
it('rejects unsupported, oversized, empty, and disguised images', async () => {
  await expect(
    stageEditorImage(
      uri,
      new File(['svg'], 'x.svg', { type: 'image/svg+xml' }),
    ),
  ).rejects.toThrow()
  await expect(
    stageEditorImage(uri, new File([], 'x.png', { type: 'image/png' })),
  ).rejects.toThrow()
  const tooLarge = new File(['x'], 'x.png', { type: 'image/png' })
  Object.defineProperty(tooLarge, 'size', { value: MAX_EDITOR_IMAGE_BYTES + 1 })
  await expect(stageEditorImage(uri, tooLarge)).rejects.toThrow()
  const disguised = new File(['text'], 'x.png', { type: 'image/png' })
  Object.defineProperty(disguised, 'arrayBuffer', {
    value: async () => new TextEncoder().encode('text').buffer,
  })
  await expect(stageEditorImage(uri, disguised)).rejects.toThrow()
})
it('stages validated bytes under a unique sibling path without writing remotely', async () => {
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:preview' })
  const image = new File(['png'], 'My [shot].png', { type: 'image/png' })
  Object.defineProperty(image, 'arrayBuffer', {
    value: async () =>
      Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]).buffer,
  })
  const result = await stageEditorImage(uri, image)
  expect(result.path).toMatch(/^assets\/.+\.png$/)
  expect(result.uri).toBe('viking://resources/demo/' + result.path)
  expect(result.alt).toBe('My shot')
  expect(request).not.toHaveBeenCalled()
  await saveEditorImages(uri, [result])
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({
      url: '/api/v1/content/batch-write',
      body: expect.objectContaining({
        root_uri: 'viking://resources/demo',
        operations: [
          expect.objectContaining({
            uri: result.uri,
            content_base64: result.base64,
          }),
        ],
      }),
    }),
  )
  vi.unstubAllGlobals()
})

import { beforeEach, expect, it, vi } from 'vitest'
import { saveFileContent } from './api'

const write = vi.hoisted(() => vi.fn())
vi.mock('#/shared/api/ov-client/index', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  postContentWrite: write,
}))
beforeEach(() => {
  write.mockReset()
  write.mockResolvedValue({
    data: { status: 'ok', result: {} },
    status: 200,
    headers: {},
  })
})
it('checks the hash of the original bytes when saving an edited draft', async () => {
  await saveFileContent(
    'viking://resources/demo/note.md',
    'edited draft',
    'abc',
  )
  expect(write).toHaveBeenCalledWith({
    body: {
      uri: 'viking://resources/demo/note.md',
      content: 'edited draft',
      mode: 'replace',
      wait: false,
      expected_content_sha256:
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    },
  })
})
it('preserves the existing write contract for callers without an editor baseline', async () => {
  await saveFileContent('viking://resources/demo/note.md', 'edited draft')
  expect(write).toHaveBeenCalledWith({
    body: {
      uri: 'viking://resources/demo/note.md',
      content: 'edited draft',
      mode: 'replace',
      wait: false,
    },
  })
})

import { describe, expect, it } from 'vitest'

import { isEmptyFile } from './upload'

describe('isEmptyFile', () => {
  it.each([
    ['empty', ''],
    ['spaces and newlines', '  \n\n'],
    ['every ASCII whitespace byte', ' \t\n\v\f\r'],
  ])('treats a %s file as empty', async (_label, text) => {
    expect(await isEmptyFile(new File([text], 'a.md'))).toBe(true)
  })

  it.each([
    ['text', '# Title'],
    ['text after whitespace', '\n\n x'],
    ['a NUL byte', '\0'],
    ['a non-breaking space', ' '],
  ])('keeps a file with %s', async (_label, text) => {
    expect(await isEmptyFile(new File([text], 'a.md'))).toBe(false)
  })

  it('leaves large files to the server', async () => {
    const spaces = new File([' '.repeat(64 * 1024 + 1)], 'big.md')
    expect(await isEmptyFile(spaces)).toBe(false)
  })
})

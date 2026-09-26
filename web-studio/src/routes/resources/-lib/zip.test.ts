import { describe, expect, it } from 'vitest'

import { crc32, createStoredZip } from './zip'

type ParsedEntry = { name: string; crc: number; data: Uint8Array }

function readCentralDirectory(bytes: Uint8Array): ParsedEntry[] {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const eocd = bytes.byteLength - 22
  expect(view.getUint32(eocd, true)).toBe(0x06054b50)
  const count = view.getUint16(eocd + 10, true)
  let offset = view.getUint32(eocd + 16, true)
  const entries: ParsedEntry[] = []
  for (let i = 0; i < count; i++) {
    expect(view.getUint32(offset, true)).toBe(0x02014b50)
    const crc = view.getUint32(offset + 16, true)
    const size = view.getUint32(offset + 20, true)
    const nameLength = view.getUint16(offset + 28, true)
    const extraLength = view.getUint16(offset + 30, true)
    const commentLength = view.getUint16(offset + 32, true)
    const localOffset = view.getUint32(offset + 42, true)
    const name = new TextDecoder().decode(
      bytes.subarray(offset + 46, offset + 46 + nameLength),
    )
    expect(view.getUint32(localOffset, true)).toBe(0x04034b50)
    const localNameLength = view.getUint16(localOffset + 26, true)
    const localExtraLength = view.getUint16(localOffset + 28, true)
    const dataStart = localOffset + 30 + localNameLength + localExtraLength
    entries.push({ name, crc, data: bytes.slice(dataStart, dataStart + size) })
    offset += 46 + nameLength + extraLength + commentLength
  }
  return entries
}

describe('crc32', () => {
  it('matches the reference checksum', () => {
    expect(crc32(new TextEncoder().encode('hello'))).toBe(0x3610a686)
    expect(crc32(new Uint8Array())).toBe(0)
  })
})

describe('createStoredZip', () => {
  it('stores entries that can be read back from the central directory', async () => {
    const encoder = new TextEncoder()
    const blob = createStoredZip([
      { path: 'docs/a.md', data: encoder.encode('alpha') },
      { path: 'docs/子目錄/b.md', data: encoder.encode('beta') },
    ])

    const bytes = new Uint8Array(await blob.arrayBuffer())
    const entries = readCentralDirectory(bytes)

    expect(entries.map((entry) => entry.name)).toEqual([
      'docs/a.md',
      'docs/子目錄/b.md',
    ])
    expect(new TextDecoder().decode(entries[0].data)).toBe('alpha')
    expect(new TextDecoder().decode(entries[1].data)).toBe('beta')
    expect(entries[0].crc).toBe(crc32(encoder.encode('alpha')))
  })

  it('produces a valid empty archive', async () => {
    const bytes = new Uint8Array(await createStoredZip([]).arrayBuffer())
    expect(bytes.byteLength).toBe(22)
    expect(readCentralDirectory(bytes)).toEqual([])
  })
})

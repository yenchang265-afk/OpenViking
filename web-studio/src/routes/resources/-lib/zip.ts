// Minimal ZIP writer (STORE method, no compression) used to upload a picked
// folder as a single archive; the server's ZipParser restores the tree.

export type ZipEntry = {
  path: string
  data: Uint8Array<ArrayBuffer>
}

const LOCAL_HEADER_SIGNATURE = 0x04034b50
const CENTRAL_HEADER_SIGNATURE = 0x02014b50
const END_OF_CENTRAL_DIRECTORY_SIGNATURE = 0x06054b50
const ZIP_VERSION = 20
const UTF8_FLAG = 0x0800
const MAX_ZIP32_ENTRIES = 0xffff

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    }
    table[n] = c >>> 0
  }
  return table
})()

export function crc32(data: Uint8Array): number {
  let crc = 0xffffffff
  for (const byte of data) {
    crc = CRC32_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

function toDosDateTime(date: Date): { time: number; date: number } {
  const year = Math.max(date.getFullYear(), 1980)
  return {
    time:
      (date.getHours() << 11) |
      (date.getMinutes() << 5) |
      Math.floor(date.getSeconds() / 2),
    date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
  }
}

export function createStoredZip(
  entries: ZipEntry[],
  modifiedAt: Date = new Date(),
): Blob {
  if (entries.length > MAX_ZIP32_ENTRIES) {
    throw new Error(
      `ZIP archives support at most ${MAX_ZIP32_ENTRIES} entries.`,
    )
  }

  const encoder = new TextEncoder()
  const dos = toDosDateTime(modifiedAt)
  const parts: BlobPart[] = []
  const centralRecords: Uint8Array<ArrayBuffer>[] = []
  let offset = 0

  for (const entry of entries) {
    const name = encoder.encode(entry.path)
    const crc = crc32(entry.data)
    const size = entry.data.byteLength

    const local = new Uint8Array(30 + name.byteLength)
    const localView = new DataView(local.buffer)
    localView.setUint32(0, LOCAL_HEADER_SIGNATURE, true)
    localView.setUint16(4, ZIP_VERSION, true)
    localView.setUint16(6, UTF8_FLAG, true)
    localView.setUint16(8, 0, true)
    localView.setUint16(10, dos.time, true)
    localView.setUint16(12, dos.date, true)
    localView.setUint32(14, crc, true)
    localView.setUint32(18, size, true)
    localView.setUint32(22, size, true)
    localView.setUint16(26, name.byteLength, true)
    localView.setUint16(28, 0, true)
    local.set(name, 30)

    const central = new Uint8Array(46 + name.byteLength)
    const centralView = new DataView(central.buffer)
    centralView.setUint32(0, CENTRAL_HEADER_SIGNATURE, true)
    centralView.setUint16(4, ZIP_VERSION, true)
    centralView.setUint16(6, ZIP_VERSION, true)
    centralView.setUint16(8, UTF8_FLAG, true)
    centralView.setUint16(10, 0, true)
    centralView.setUint16(12, dos.time, true)
    centralView.setUint16(14, dos.date, true)
    centralView.setUint32(16, crc, true)
    centralView.setUint32(20, size, true)
    centralView.setUint32(24, size, true)
    centralView.setUint16(28, name.byteLength, true)
    centralView.setUint32(42, offset, true)
    central.set(name, 46)

    parts.push(local, entry.data)
    centralRecords.push(central)
    offset += local.byteLength + size
  }

  const centralSize = centralRecords.reduce(
    (total, record) => total + record.byteLength,
    0,
  )
  const end = new Uint8Array(22)
  const endView = new DataView(end.buffer)
  endView.setUint32(0, END_OF_CENTRAL_DIRECTORY_SIGNATURE, true)
  endView.setUint16(8, entries.length, true)
  endView.setUint16(10, entries.length, true)
  endView.setUint32(12, centralSize, true)
  endView.setUint32(16, offset, true)

  return new Blob([...parts, ...centralRecords, end], {
    type: 'application/zip',
  })
}

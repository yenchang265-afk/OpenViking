import i18n from '#/i18n/core'
import { deleteFs, getOvResult, ovClient } from '#/shared/api/ov-client'

export const MAX_EDITOR_IMAGE_BYTES = 10 * 1024 * 1024
const IMAGE_TYPES: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/gif': 'gif',
  'image/webp': 'webp',
}

export interface EditorImage {
  uri: string
  path: string
  alt: string
  base64: string
  previewUrl: string
}

export function supportsEditorImages(uri: string): boolean {
  return uri.startsWith('viking://resources/')
}

/** Stage images locally; cancelling the editor never creates orphan files. */
export async function stageEditorImage(
  uri: string,
  file: File,
): Promise<EditorImage> {
  const extension = IMAGE_TYPES[file.type]
  if (
    !supportsEditorImages(uri) ||
    !extension ||
    !file.size ||
    file.size > MAX_EDITOR_IMAGE_BYTES
  ) {
    throw new Error(i18n.t('resources:filePreview.editor.imageTypes'))
  }
  const buffer = new Uint8Array(await file.arrayBuffer())
  const signature = Array.from(buffer.slice(0, 12))
  const valid =
    extension === 'png'
      ? signature.slice(0, 8).join(',') === '137,80,78,71,13,10,26,10'
      : extension === 'jpg'
        ? signature[0] === 255 && signature[1] === 216 && signature[2] === 255
        : extension === 'gif'
          ? String.fromCharCode(...buffer.slice(0, 6)).match(/^GIF8[79]a$/)
          : String.fromCharCode(...buffer.slice(0, 4)) === 'RIFF' &&
            String.fromCharCode(...buffer.slice(8, 12)) === 'WEBP'
  if (!valid) throw new Error(i18n.t('resources:filePreview.editor.imageTypes'))
  let binary = ''
  for (let i = 0; i < buffer.length; i += 8192) {
    binary += String.fromCharCode(...buffer.subarray(i, i + 8192))
  }
  const path = `assets/${crypto.randomUUID()}.${extension}`
  return {
    uri: `${uri.slice(0, uri.lastIndexOf('/') + 1)}${path}`,
    path,
    alt: file.name.replace(/\.[^.]+$/, '').replace(/[[\]\\\r\n]/g, ''),
    base64: btoa(binary),
    previewUrl: URL.createObjectURL(file),
  }
}

/** Upload before writing the referencing document; retries use the same unique paths. */
export async function saveEditorImages(
  documentUri: string,
  images: EditorImage[],
): Promise<void> {
  if (!images.length) return
  await getOvResult(
    ovClient.client.post({
      url: '/api/v1/content/batch-write',
      body: {
        root_uri: documentUri.slice(0, documentUri.lastIndexOf('/')),
        operations: images.map((image) => ({
          uri: image.uri,
          content_base64: image.base64,
          mode: 'upsert',
        })),
        wait: false,
        processing_mode: 'semantic_and_vectors',
      },
    }),
  )
}

/** Best-effort rollback of unique assets belonging to a cancelled, unsaved draft. */
export async function discardEditorImages(
  images: EditorImage[],
): Promise<void> {
  await Promise.allSettled(
    images.map((image) => getOvResult(deleteFs({ query: { uri: image.uri } }))),
  )
}

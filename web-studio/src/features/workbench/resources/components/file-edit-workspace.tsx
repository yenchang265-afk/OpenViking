import {
  forwardRef,
  lazy,
  Suspense,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '#/shared/ui/button'
import { CodeEditor } from '#/shared/components/code-editor'
import type { CodeEditorHandle } from '#/shared/components/code-editor'
import { fetchFsList } from '../lib/api'
import type { VikingFsEntry } from '#/shared/types/viking-fs'
import { richMarkdownBody } from '../lib/rich-markdown'
import {
  saveEditorImages,
  discardEditorImages,
  MAX_EDITOR_IMAGE_BYTES,
  stageEditorImage,
  supportsEditorImages,
} from '../lib/editor-images'
import type { EditorImage } from '../lib/editor-images'

const EDIT_MODES = ['source', 'split', 'rich'] as const

const RichMarkdownEditor = lazy(() => import('./rich-markdown-editor'))

export interface FileEditHandle extends CodeEditorHandle {
  saveAssets: () => Promise<void>
  markSaved: () => void
  retainAssets: () => void
}

export const FileEditWorkspace = forwardRef<
  FileEditHandle,
  {
    uri: string
    filename: string
    initialContent: string
    markdown: boolean
    isDark: boolean
    saving: boolean
    onChange: (content: string) => void
    renderPreview: (content: string, images: EditorImage[]) => ReactNode
  }
>(function FileEditWorkspace(
  {
    uri,
    filename,
    initialContent,
    markdown,
    isDark,
    saving,
    onChange,
    renderPreview,
  },
  ref,
) {
  const { t } = useTranslation('resources')
  const [draft, setDraft] = useState(initialContent)
  const draftRef = useRef(initialContent)
  const [mode, setMode] = useState<'source' | 'split' | 'rich'>('source')
  const [richSeed, setRichSeed] = useState(initialContent)
  const [images, setImages] = useState<EditorImage[]>([])
  const imagesRef = useRef<EditorImage[]>([])
  const [staging, setStaging] = useState(false)
  const sourceRef = useRef<CodeEditorHandle>(null)
  const richRef = useRef<CodeEditorHandle>(null)
  const pickerRef = useRef<HTMLInputElement>(null)
  const mounted = useRef(true)
  const stagedBusy = useRef(false)
  const committed = useRef(false)
  const documentWriteAttempted = useRef(false)
  const attemptedImages = useRef<EditorImage[]>([])
  const [library, setLibrary] = useState<VikingFsEntry[] | null>(null)
  const [libraryBusy, setLibraryBusy] = useState(false)
  const [imageAlt, setImageAlt] = useState('')
  const openLibrary = async () => {
    setLibraryBusy(true)
    try {
      const directory = uri.slice(0, uri.lastIndexOf('/') + 1)
      const lists = await Promise.allSettled([
        fetchFsList(directory),
        fetchFsList(directory + 'assets/'),
      ])
      const entries = lists.flatMap((result) =>
        result.status === 'fulfilled' ? result.value.entries : [],
      )
      setLibrary(
        entries.filter(
          (entry) =>
            !entry.isDir && /\.(png|jpe?g|gif|webp)$/i.test(entry.name),
        ),
      )
      if (lists.every((result) => result.status === 'rejected'))
        toast.error(t('filePreview.editor.libraryFailed'))
    } finally {
      if (mounted.current) setLibraryBusy(false)
    }
  }
  const rich = richMarkdownBody(draft)
  const html = /\.html?$/i.test(filename)
  const canInsert = supportsEditorImages(uri) && (markdown || html)
  const update = (content: string) => {
    draftRef.current = content
    setDraft(content)
    onChange(content)
  }
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      if (!committed.current && !documentWriteAttempted.current)
        void discardEditorImages(attemptedImages.current)
      imagesRef.current.forEach((image) =>
        URL.revokeObjectURL(image.previewUrl),
      )
    }
  }, [])
  const currentContent = () =>
    (mode === 'rich' ? richRef : sourceRef).current?.getContent() ??
    draftRef.current
  useImperativeHandle(ref, () => ({
    getContent: currentContent,
    insertText: (text) =>
      (mode === 'rich' ? richRef : sourceRef).current?.insertText(text),
    retainAssets: () => {
      documentWriteAttempted.current = true
    },
    markSaved: () => {
      committed.current = true
      void discardEditorImages(
        attemptedImages.current.filter(
          (image) => !currentContent().includes(image.path),
        ),
      )
    },
    saveAssets: async () => {
      if (stagedBusy.current) throw new Error(t('filePreview.editor.imageBusy'))
      const used = imagesRef.current.filter((image) =>
        currentContent().includes(image.path),
      )
      attemptedImages.current = [
        ...new Map(
          [...attemptedImages.current, ...used].map((image) => [
            image.path,
            image,
          ]),
        ).values(),
      ]
      await saveEditorImages(uri, used)
    },
  }))
  const insertImages = async (files: File[]) => {
    if (saving || stagedBusy.current || !canInsert || !files.length) return
    stagedBusy.current = true
    setStaging(true)
    try {
      for (const file of files) {
        const stagedBytes = imagesRef.current.reduce(
          (total, image) => total + image.base64.length * 0.75,
          0,
        )
        if (stagedBytes + file.size > MAX_EDITOR_IMAGE_BYTES)
          throw new Error(t('filePreview.editor.imageTotal'))
        const image = await stageEditorImage(uri, file)
        if (!mounted.current) {
          URL.revokeObjectURL(image.previewUrl)
          return
        }
        imagesRef.current = [...imagesRef.current, image]
        setImages(imagesRef.current)
        if (mode === 'rich') {
          richRef.current?.insertText(
            `![${imageAlt.replace(/[[\]\\\r\n]/g, '') || image.alt}](${image.path})`,
          )
        } else {
          const text = markdown
            ? `![${imageAlt.replace(/[[\]\\\r\n]/g, '') || image.alt}](${image.path})`
            : `<img src="${image.path}" alt="${(imageAlt || image.alt).replace(/[&"<>]/g, '')}">`
          sourceRef.current?.insertText(text)
        }
      }
    } catch (error) {
      toast.error(t('filePreview.editor.imageFailed'), {
        description:
          error instanceof Error && error.message === 'INVALID_EDITOR_IMAGE'
            ? t('filePreview.editor.imageTypes')
            : String(error),
      })
    } finally {
      stagedBusy.current = false
      if (mounted.current) setStaging(false)
    }
  }
  return (
    <div
      className="flex h-full min-h-0 flex-col gap-2"
      onPasteCapture={(event) => {
        const files = Array.from(event.clipboardData.files).filter((file) =>
          file.type.startsWith('image/'),
        )
        if (canInsert && files.length) {
          event.preventDefault()
          event.stopPropagation()
          void insertImages(files)
        }
      }}
      onDragOver={(event) => {
        if (canInsert && event.dataTransfer.types.includes('Files'))
          event.preventDefault()
      }}
      onDropCapture={(event) => {
        if (!canInsert || !event.dataTransfer.files.length) return
        event.preventDefault()
        event.stopPropagation()
        void insertImages(Array.from(event.dataTransfer.files))
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        {(markdown || html) &&
          EDIT_MODES.filter((value) => markdown || value !== 'rich').map(
            (value) => (
              <Button
                key={value}
                size="sm"
                variant={mode === value ? 'secondary' : 'ghost'}
                disabled={saving || staging || (value === 'rich' && !rich)}
                title={
                  value === 'rich' && !rich
                    ? t('filePreview.editor.richUnsupported')
                    : undefined
                }
                onClick={() => {
                  const content = currentContent()
                  update(content)
                  if (value === 'rich') setRichSeed(content)
                  setMode(value)
                }}
              >
                {t(`filePreview.editor.${value}`)}
              </Button>
            ),
          )}
        {canInsert && (
          <>
            <Button
              size="sm"
              variant="outline"
              disabled={saving || staging}
              onClick={() => pickerRef.current?.click()}
            >
              {t(
                staging
                  ? 'filePreview.editor.imageBusy'
                  : 'filePreview.editor.insertImage',
              )}
            </Button>
            <input
              ref={pickerRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              className="hidden"
              aria-label={t('filePreview.editor.insertImage')}
              disabled={saving || staging}
              onChange={(event) => {
                void insertImages(Array.from(event.target.files ?? []))
                event.target.value = ''
              }}
            />
          </>
        )}
        {canInsert && (
          <>
            <Button
              size="sm"
              variant="ghost"
              disabled={saving || staging || libraryBusy}
              onClick={() => void openLibrary()}
            >
              {t('filePreview.editor.existingImage')}
            </Button>
            <input
              className="rounded border bg-background px-2 py-1 text-sm"
              aria-label={t('filePreview.editor.alt')}
              placeholder={t('filePreview.editor.alt')}
              value={imageAlt}
              disabled={saving || staging}
              onChange={(event) => setImageAlt(event.target.value)}
            />
          </>
        )}
        <span className="text-xs text-muted-foreground" role="status">
          {t(
            draft === initialContent
              ? 'filePreview.editor.saved'
              : 'filePreview.editor.unsaved',
          )}
        </span>
      </div>
      {library !== null && (
        <div className="max-h-36 shrink-0 overflow-auto rounded border p-2">
          <Button size="sm" variant="ghost" onClick={() => setLibrary(null)}>
            {t('filePreview.cancel')}
          </Button>
          {library.length === 0 && (
            <p className="text-xs">{t('filePreview.editor.noImages')}</p>
          )}
          {library.map((entry) => (
            <Button
              key={entry.uri}
              size="sm"
              variant="ghost"
              disabled={saving || staging}
              onClick={() => {
                const path = encodeURI(entry.uri)
                  .replace(/#/g, '%23')
                  .replace(/\(/g, '%28')
                  .replace(/\)/g, '%29')
                const alt = imageAlt.replace(/[[\]\\\r\n]/g, '')
                const text = markdown
                  ? `![${alt}](${path})`
                  : `<img src="${path}" alt="${alt.replace(/[&"<>]/g, '')}">`
                ;(mode === 'rich' ? richRef : sourceRef).current?.insertText(
                  text,
                )
                setLibrary(null)
              }}
            >
              {entry.name}
            </Button>
          ))}
        </div>
      )}
      {markdown && !rich && (
        <p className="text-xs text-muted-foreground">
          {t('filePreview.editor.richUnsupported')}
        </p>
      )}
      <div
        className={`grid min-h-0 flex-1 gap-3 ${mode === 'split' ? 'md:grid-cols-2' : ''}`}
      >
        <div className="min-h-0 overflow-auto">
          {mode === 'rich' ? (
            <Suspense fallback={<p>{t('filePreview.loadingEditor')}</p>}>
              <RichMarkdownEditor
                ref={richRef}
                initialContent={richSeed}
                readOnly={saving}
                onChange={update}
                getImageUrl={(path) =>
                  imagesRef.current.find((image) => image.path === path)
                    ?.previewUrl
                }
                uri={uri}
              />
            </Suspense>
          ) : (
            <CodeEditor
              ref={sourceRef}
              initialContent={draft}
              filename={filename}
              isDark={isDark}
              readOnly={saving}
              onChange={update}
            />
          )}
        </div>
        {mode === 'split' && (
          <div className="min-h-0 overflow-auto rounded-md border p-3">
            {renderPreview(draft, images)}
          </div>
        )}
      </div>
    </div>
  )
})

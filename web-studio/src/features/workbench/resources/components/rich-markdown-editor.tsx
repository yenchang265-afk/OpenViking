import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { Markdown } from '@tiptap/markdown'
import { useTranslation } from 'react-i18next'
import { getContentDownload } from '#/shared/api/ov-client'
import type { CodeEditorHandle } from '#/shared/components/code-editor'
import { Button } from '#/shared/ui/button'
import { resolveMarkdownAssetTarget } from '../lib/markdown-assets'
import { richMarkdownBody } from '../lib/rich-markdown'

export default forwardRef<
  CodeEditorHandle,
  {
    initialContent: string
    readOnly: boolean
    onChange: (content: string) => void
    getImageUrl: (path: string) => string | undefined
    uri: string
  }
>(function RichMarkdownEditor(
  { initialContent, readOnly, onChange, getImageUrl, uri },
  ref,
) {
  const { t } = useTranslation('resources')
  const parsed = richMarkdownBody(initialContent)!
  const imageUrlRef = useRef(getImageUrl)
  imageUrlRef.current = getImageUrl
  const contentRef = useRef(initialContent)
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Markdown,
      Image.extend({
        addNodeView() {
          return ({ node }) => {
            const dom = document.createElement('img')
            dom.alt = String(node.attrs.alt ?? '')
            dom.className = 'max-w-full rounded-md'
            let alive = true
            let objectUrl: string | null = null
            const path = String(node.attrs.src ?? '')
            const staged = imageUrlRef.current(path)
            if (staged) dom.src = staged
            else {
              let target: string | null = null
              try {
                const resolved = resolveMarkdownAssetTarget(path, uri)
                target = resolved.kind === 'viking' ? resolved.value : null
              } catch {
                /* Invalid paths remain unrendered. */
              }
              if (target) {
                void getContentDownload({
                  query: { uri: target },
                  responseType: 'blob',
                  throwOnError: true,
                })
                  .then((response) => {
                    if (!alive) return
                    objectUrl = URL.createObjectURL(response.data as Blob)
                    dom.src = objectUrl
                  })
                  .catch(() => {
                    dom.alt = t('filePreview.imageFailed')
                  })
              } else if (/^https?:\/\//i.test(path)) dom.src = path
            }
            return {
              dom,
              destroy: () => {
                alive = false
                if (objectUrl) URL.revokeObjectURL(objectUrl)
              },
            }
          }
        },
      }),
    ],
    content: parsed.body,
    contentType: 'markdown',
    editable: !readOnly,
    editorProps: {
      attributes: {
        class:
          'prose prose-sm dark:prose-invert max-w-none min-h-full p-3 outline-none',
        'aria-label': t('filePreview.editor.rich'),
      },
    },
    onUpdate: ({ editor: instance }) => {
      contentRef.current = parsed.prefix + instance.getMarkdown()
      onChange(contentRef.current)
    },
  })
  // useEditor updates options, but editable is an explicit editor state.
  useEffect(() => {
    editor?.setEditable(!readOnly, false)
  }, [editor, readOnly])
  useImperativeHandle(ref, () => ({
    getContent: () => contentRef.current,
    insertText: (text) => {
      editor
        ?.chain()
        .focus()
        .insertContent(text, { contentType: 'markdown' })
        .run()
    },
  }))
  const actions = [
    ['bold', () => editor?.chain().focus().toggleBold().run()],
    ['italic', () => editor?.chain().focus().toggleItalic().run()],
    [
      'heading',
      () => editor?.chain().focus().toggleHeading({ level: 2 }).run(),
    ],
    ['bulletList', () => editor?.chain().focus().toggleBulletList().run()],
    ['orderedList', () => editor?.chain().focus().toggleOrderedList().run()],
    ['codeBlock', () => editor?.chain().focus().toggleCodeBlock().run()],
    ['undo', () => editor?.chain().focus().undo().run()],
    ['redo', () => editor?.chain().focus().redo().run()],
  ] as const
  return (
    <div className="flex h-full min-h-0 flex-col rounded-md border">
      <div className="flex flex-wrap gap-1 border-b p-1">
        {actions.map(([label, action]) => (
          <Button
            key={label}
            size="sm"
            variant="ghost"
            disabled={readOnly || !editor}
            onClick={action}
          >
            {t(`filePreview.editor.${label}`)}
          </Button>
        ))}
        <Button
          size="sm"
          variant="ghost"
          disabled={readOnly || !editor}
          onClick={() => {
            const href = window.prompt(
              t('filePreview.editor.linkUrl'),
              String(editor?.getAttributes('link').href ?? ''),
            )
            if (href === null) return
            if (!href.trim()) editor?.chain().focus().unsetLink().run()
            else if (/^(https?:\/\/|mailto:)/i.test(href))
              editor?.chain().focus().setLink({ href }).run()
          }}
        >
          {t('filePreview.editor.link')}
        </Button>
      </div>
      <EditorContent editor={editor} className="min-h-0 flex-1 overflow-auto" />
    </div>
  )
})

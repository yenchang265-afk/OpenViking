# File editing

Open a text resource and choose **Edit**. The editor supports search, folding,
syntax highlighting, undo, fullscreen, and Ctrl/Cmd+S. Markdown supports Source,
Split preview, and Rich text modes. HTML supports Source and Split preview.

Rich text provides headings, bold, italic, lists, links, and code blocks. Leading
YAML frontmatter stays outside the rich editor and is preserved byte for byte.
Opening rich mode without editing does not rewrite Markdown. Documents containing
HTML, comments (including memory metadata), reference links, tables, task lists,
math, Mermaid, and other detected extension syntax remain in source mode.

Markdown and HTML resource documents can insert PNG, JPEG, GIF, and WebP images
using a file picker, paste, or drag and drop. Use **Image description** for alt
text or **Existing image** to select an image beside the document or in its
`assets` folder. Uploads are limited to 10 MiB total per draft and validated by
MIME type and signature. Memory namespaces cannot store binary image uploads.

New images are staged in the browser until Save. The server stores them under
unique `assets/<uuid>.<extension>` paths before writing the document. Previews use
local object URLs or authenticated downloads; saved documents contain durable
paths. Failed saves preserve the draft. Cancelling performs best-effort removal
of uploaded assets when the document write has not been attempted. After a
document write is attempted, assets are retained because a lost response can
follow a successful commit. Batch writes are not atomic, and failed saves can
leave unused images; retaining them avoids breaking a committed document.

Navigation, closing, and page unloading protect unsaved drafts. Saving sends an
optional `expected_content_sha256` to `/api/v1/content/write`. The backend checks
the original content hash while holding the file write lease and returns a
conflict if the original changed or was deleted. The editor shows the current
server version for comparison. Merge it into the draft and choose **I have merged
the latest changes** before retrying. Concurrent changes after that comparison
are checked again. Deploy the matching frontend and backend together; this uses
Web Crypto and requires HTTPS or localhost.

HTML preview runs in an iframe with an opaque sandbox origin and a restrictive
Content Security Policy. Scripts, forms, external frames, and base URLs are
blocked. Local images are fetched with the authenticated client.

PDF and Office files retain their existing preview/download behavior. This editor
does not provide Office document conversion or real-time collaborative editing.

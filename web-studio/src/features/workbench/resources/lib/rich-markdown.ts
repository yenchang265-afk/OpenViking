/** Rich mode is opt-in and restricted to syntax its schema can preserve. */
export function richMarkdownBody(
  content: string,
): { prefix: string; body: string } | null {
  const frontmatter =
    /^(?:\uFEFF)?---[^\S\r\n]*\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)[^\S\r\n]*(?:\r?\n|$)/.exec(
      content,
    )
  const prefix = frontmatter?.[0] ?? ''
  const body = content.slice(prefix.length)
  // HTML/comments (including MEMORY_FIELDS), reference links, directives and
  // extension syntax stay in source mode rather than silently losing content.
  if (
    /<[!/?a-zA-Z]|^\s*\[[^\]]+\]:|\]\[[^\]]*\]|\[\^|^\s*:::|\$\$|~~|^\s*\||^\s*[-*+] \[[ xX]\]|^\s*[^\n]+\n\s*: |\\\(|\$[^\n$]+\$|^\s*```mermaid/m.test(
      body,
    )
  )
    return null
  return { prefix, body }
}

import fs from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Deliberately checks files, not translated heading anchors or external URLs.
// Run from any directory: node docs/scripts/check-docs-consistency.mjs
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
function pages(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const filename = path.join(directory, entry.name)
    return entry.isDirectory() ? pages(filename) : filename.endsWith('.md') ? [filename] : []
  })
}
const localized = ['en', 'zh'].map((locale) => pages(path.join(root, locale)))
const repoRoot = path.dirname(root)
// Include component guides and README files that are outside the VitePress site.
const tracked = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z'], { cwd: repoRoot, encoding: 'utf8' })
  .split('\0').filter((file) => /\.(?:md|mdx|rst)$/i.test(file))
  .map((file) => path.join(repoRoot, file))
  .filter((file) => fs.existsSync(file))
const allFiles = [...new Set([...tracked, ...localized.flat()])]
const localizedFiles = new Set(localized.flat())
const errors = []
const skipped = []
let jsonCount = 0
let linkCount = 0
for (const [index, files] of localized.entries()) {
  const locale = ['en', 'zh'][index]
  const other = ['zh', 'en'][index]
  for (const file of files) {
    const relative = path.relative(path.join(root, locale), file)
    if (!fs.existsSync(path.join(root, other, relative))) errors.push(`${locale}/${relative}: missing ${other} page`)
  }
}
for (const file of allFiles) {
  const source = fs.readFileSync(file, 'utf8')
  const label = path.relative(repoRoot, file)
  const isSitePage = file.startsWith(root + path.sep)
  const lineAt = (offset) => source.slice(0, offset).split('\n').length
  // Mask fences before checking links; example payloads are not page links.
  const prose = source.replace(/^([ \t]*)(`{3,}|~{3,})([^\n]*)\n([\s\S]*?)^\1\2[ \t]*$/gm,
    (block, indent, fence, info, body, offset) => {
      const language = info.trim().split(/\s/)[0]
      if (localizedFiles.has(file) && (language === 'json' || language === 'jsonc')) {
        try {
          JSON.parse(body)
          jsonCount++
        } catch (error) {
          // Legacy JSON-labelled examples sometimes deliberately contain comments
          // or unquoted ellipses. Report these as illustrative, never valid JSON.
          const unquoted = body.replace(/"(?:\\.|[^"\\])*"/g, '""')
          const reason = language === 'jsonc' ? 'explicit JSONC'
            : /\/\/|\/\*/.test(unquoted) ? 'comments in a json fence'
              : /\.\.\.|…|<[^>]+>/.test(unquoted) ? 'illustrative placeholders' : null
          if (reason) skipped.push({ location: `${label}:${lineAt(offset)}`, reason })
          else errors.push(`${label}:${lineAt(offset)}: invalid JSON: ${error.message}`)
        }
      }
      return block.replace(/[^\n]/g, ' ')
    })
  const links = [...prose.matchAll(/!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+["'][^\n]*?["'])?\s*\)/g)]
  const definitions = [...prose.matchAll(/^ {0,3}\[[^\]\n]+\]:\s*(<[^>]+>|\S+)/gm)]
  for (const match of [...links, ...definitions]) {
    const href = match[1].replace(/^<|>$/g, '')
    if (/^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(href)) continue
    const pathname = href.split(/[?#]/)[0]
    if (!pathname || /[{}]/.test(pathname)) continue
    let decoded
    try { decoded = decodeURIComponent(pathname) } catch { errors.push(`${label}:${lineAt(match.index)}: invalid URL ${href}`); continue }
    const target = decoded.startsWith('/') ? path.join(isSitePage ? root : repoRoot, decoded) : path.resolve(path.dirname(file), decoded)
    const candidates = [target, `${target}.md`, `${target}.mdx`, `${target}.rst`, path.join(target, 'index.md'), path.join(target, 'index.mdx')]
    if (target.endsWith('.html')) candidates.push(target.slice(0, -5) + '.md')
    // VitePress serves public assets from the site root.
    if (isSitePage && decoded.startsWith('/')) candidates.push(path.join(root, 'images', decoded))
    linkCount++
    if (!candidates.some((candidate) => fs.existsSync(candidate))) errors.push(`${label}:${lineAt(match.index)}: missing link target ${href}`)
  }
}
console.log(`Checked ${localized[0].length} English and ${localized[1].length} Chinese pages, ${jsonCount} strict JSON blocks, ${linkCount} local links across ${allFiles.length} repository documents.`)
console.log(`Skipped strict JSON parsing for ${skipped.length} JSONC / illustrative blocks (use --verbose to list).`)
for (const reason of [...new Set(skipped.map((item) => item.reason))]) {
  console.log(`  ${reason}: ${skipped.filter((item) => item.reason === reason).length} (not validated as JSON)`)
}
if (process.argv.includes('--verbose')) console.log(skipped.map((item) => `${item.location}: ${item.reason}`).join('\n'))
if (errors.length) {
  console.error(errors.join('\n'))
  process.exitCode = 1
} else console.log('Documentation consistency checks passed.')

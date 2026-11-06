import { describe, expect, it } from 'vitest'
import { renderMarkdown, resolveDocPath } from '../src/lib/markdown'

describe('markdown rendering', () => {
  it('renders headings, lists, tables and fenced code', () => {
    const html = renderMarkdown('# 标题\n\n- 一\n- 二\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n```ts\nconst x = 1\n```')
    expect(html).toContain('<h1>标题</h1>')
    expect(html).toContain('<ul><li>一</li><li>二</li></ul>')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>A</th>')
    expect(html).toContain('<pre><code>const x = 1</code></pre>')
  })

  it('escapes raw HTML and blocks javascript links', () => {
    const html = renderMarkdown('<script>alert(1)</script>\n\n[坏链接](javascript:alert(1))')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
    expect(html).toContain('坏链接')
    expect(html).not.toContain('href="javascript:')
  })

  it('renders images as links instead of auto-loading media', () => {
    const html = renderMarkdown('![截图](https://example.com/a.png)')
    expect(html).not.toContain('<img')
    expect(html).toContain('href="https://example.com/a.png"')
    expect(html).toContain('截图')
  })

  it('keeps normal web and relative links as anchors', () => {
    const html = renderMarkdown('[项目](https://example.com) [索引](docs/INDEX.md)')
    expect(html).toContain('href="https://example.com"')
    expect(html).toContain('href="docs/INDEX.md"')
  })
})

describe('document link resolution', () => {
  it('resolves project-relative Markdown against the current file', () => {
    expect(resolveDocPath('Works/A/README.md', '../B/NOTES.md')).toEqual({ kind: 'doc', path: 'Works/B/NOTES.md' })
    expect(resolveDocPath('INDEX.md', 'TEAM.md')).toEqual({ kind: 'doc', path: 'TEAM.md' })
  })

  it('treats absolute and external paths without pretending the page can open them', () => {
    expect(resolveDocPath('INDEX.md', 'C:/Users/remo/Doc.md').kind).toBe('absolute')
    expect(resolveDocPath('INDEX.md', '/mnt/c/notes.md').kind).toBe('absolute')
    expect(resolveDocPath('INDEX.md', 'https://example.com').kind).toBe('external')
    expect(resolveDocPath('INDEX.md', '#section').kind).toBe('anchor')
  })

  it('treats non-document relative paths as copyable locations', () => {
    expect(resolveDocPath('INDEX.md', 'assets/logo.png').kind).toBe('absolute')
  })
})

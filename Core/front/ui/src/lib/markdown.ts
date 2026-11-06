export type LinkKind = 'doc' | 'external' | 'absolute' | 'anchor'

export interface LinkTarget {
  kind: LinkKind
  path: string
}

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  } as Record<string, string>)[char])
}

function safeHref(href: string): string {
  const value = href.trim()
  if (/^(https?:|mailto:|#)/i.test(value)) return value
  if (/^javascript:/i.test(value)) return ''
  return value
}

function inline(text: string): string {
  let out = ''
  let index = 0
  const pattern = /(`[^`]+`)|(!?\[[^\]]*\]\([^)]*\))|(https?:\/\/[^\s<>()]+)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(~~[^~]+~~)/g
  for (const match of text.matchAll(pattern)) {
    out += escapeHtml(text.slice(index, match.index))
    const token = match[0]
    if (token.startsWith('`')) {
      out += '<code>' + escapeHtml(token.slice(1, -1)) + '</code>'
    } else if (token.startsWith('![')) {
      const alt = token.slice(2, token.indexOf(']'))
      const href = safeHref(token.slice(token.indexOf('(') + 1, -1))
      out += href ? `<a href="${escapeHtml(href)}" rel="noopener noreferrer">${escapeHtml(alt || href)}</a>` : escapeHtml(alt)
    } else if (token.startsWith('[')) {
      const label = token.slice(1, token.indexOf(']'))
      const href = safeHref(token.slice(token.indexOf('(') + 1, -1))
      out += href
        ? `<a href="${escapeHtml(href)}" rel="noopener noreferrer">${escapeHtml(label)}</a>`
        : escapeHtml(label)
    } else if (/^https?:/.test(token)) {
      out += `<a href="${escapeHtml(token)}" rel="noopener noreferrer">${escapeHtml(token)}</a>`
    } else if (token.startsWith('**')) {
      out += '<strong>' + inline(token.slice(2, -2)) + '</strong>'
    } else if (token.startsWith('~~')) {
      out += '<del>' + inline(token.slice(2, -2)) + '</del>'
    } else if (token.startsWith('*')) {
      out += '<em>' + inline(token.slice(1, -1)) + '</em>'
    }
    index = (match.index || 0) + token.length
  }
  out += escapeHtml(text.slice(index))
  return out
}

function isTableSeparator(line: string): boolean {
  return /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes('-')
}

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
}

export function renderMarkdown(source: string): string {
  const lines = source.replace(/\r\n?/g, '\n').split('\n')
  const html: string[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) {
      index += 1
      continue
    }

    const fence = line.match(/^```\s*([\w+-]*)\s*$/)
    if (fence) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !/^```/.test(lines[index])) {
        code.push(lines[index])
        index += 1
      }
      index += 1
      html.push('<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>')
      continue
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      const level = heading[1].length
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      index += 1
      continue
    }

    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      html.push('<hr>')
      index += 1
      continue
    }

    if (/^\s*>/.test(line)) {
      const quote: string[] = []
      while (index < lines.length && /^\s*>/.test(lines[index])) {
        quote.push(lines[index].replace(/^\s*>\s?/, ''))
        index += 1
      }
      html.push('<blockquote>' + renderMarkdown(quote.join('\n')) + '</blockquote>')
      continue
    }

    if (line.includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const header = cells(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(cells(lines[index]))
        index += 1
      }
      html.push('<table><thead><tr>' + header.map(cell => `<th>${inline(cell)}</th>`).join('') + '</tr></thead><tbody>' +
        rows.map(row => '<tr>' + row.map(cell => `<td>${inline(cell)}</td>`).join('') + '</tr>').join('') +
        '</tbody></table>')
      continue
    }

    const listItem = line.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/)
    if (listItem) {
      const ordered = /\d+\./.test(listItem[2])
      const tag = ordered ? 'ol' : 'ul'
      const items: string[] = []
      while (index < lines.length) {
        const current = lines[index]
        const match = current.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/)
        if (!match) break
        const indent = match[1].length
        if (indent >= 2 && items.length) items[items.length - 1] += '<br>' + inline(match[3])
        else items.push(inline(match[3]))
        index += 1
      }
      html.push(`<${tag}>` + items.map(item => `<li>${item}</li>`).join('') + `</${tag}>`)
      continue
    }

    const paragraph: string[] = []
    while (index < lines.length) {
      const current = lines[index]
      if (!current.trim()) break
      if (/^(#{1,6})\s+/.test(current) || /^```/.test(current) || /^\s*>/.test(current)) break
      if (current.match(/^(\s*)([-*+]|\d+\.)\s+/) || (current.includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1]))) break
      paragraph.push(current)
      index += 1
    }
    html.push('<p>' + paragraph.map(inline).join('<br>') + '</p>')
  }

  return html.join('\n')
}

export function resolveDocPath(basePath: string, href: string): LinkTarget {
  const value = href.trim()
  if (!value) return { kind: 'anchor', path: '' }
  if (/^#/.test(value)) return { kind: 'anchor', path: value }
  if (/^(https?:|mailto:)/i.test(value)) return { kind: 'external', path: value }
  if (/^([a-zA-Z]:[\\/]|\\\\|\/)/.test(value)) return { kind: 'absolute', path: value }
  const baseParts = basePath.split('/').slice(0, -1)
  const parts = [...baseParts, ...value.split('/')]
  const normalized: string[] = []
  for (const part of parts) {
    if (!part || part === '.') continue
    if (part === '..') normalized.pop()
    else normalized.push(part)
  }
  const path = normalized.join('/')
  return { kind: /\.(md|markdown|txt|json)$/i.test(path) ? 'doc' : 'absolute', path }
}

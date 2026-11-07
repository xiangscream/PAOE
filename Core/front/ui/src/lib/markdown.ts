import MarkdownIt from '../../../vendor/markdown-it-15.0.3.mjs'

export type LinkKind = 'doc' | 'external' | 'absolute' | 'anchor'
export interface LinkTarget {kind:LinkKind;path:string;hash?:string}

// Share the already bundled parser with CAT. Documents may also link to local originals.
const markdown = MarkdownIt({html:false,linkify:true,breaks:true})
markdown.validateLink = (href:string) =>
  /^(https?:|mailto:|#)/i.test(href) || /^[a-z]:[\\/]/i.test(href) || !/^[a-z][a-z0-9+.-]*:/i.test(href)
markdown.renderer.rules.link_open = (tokens:any[], index:number, options:any, env:any, renderer:any) => {
  if (/^(https?:|mailto:)/i.test(tokens[index].attrGet('href') || '')) {
    tokens[index].attrSet('target','_blank')
    tokens[index].attrSet('rel','noopener noreferrer')
  }
  return renderer.renderToken(tokens,index,options)
}
markdown.renderer.rules.image = (tokens:any[], index:number) => {
  const token=tokens[index]
  const href=token.attrGet('src') || ''
  const label=token.content || href
  return '<a href="'+markdown.utils.escapeHtml(href)+'">'+markdown.utils.escapeHtml(label)+'</a>'
}
markdown.renderer.rules.heading_open = (tokens:any[], index:number, options:any, env:any, renderer:any) => {
  const text=renderer.renderInlineAsText(tokens[index+1].children,options,env)
  const slug=text.trim().toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu,'').replace(/\s+/g,'-')
  const count=env.headings.get(slug) || 0
  env.headings.set(slug,count+1)
  tokens[index].attrSet('id',slug+(count?'-'+count:''))
  return renderer.renderToken(tokens,index,options)
}
export function renderMarkdown(source:string):string {
  const body=source.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/,'')
  return markdown.render(body,{headings:new Map<string,number>()})
}
export function resolveDocPath(basePath:string, href:string):LinkTarget {
  const value=decodeURI(href.trim()).replace(/\\/g,'/')
  if(!value || value.startsWith('#')) return {kind:'anchor',path:value}
  if(/^(https?:|mailto:)/i.test(value)) return {kind:'external',path:value}
  if(/^([a-z]:\/|\/)/i.test(value)) return {kind:'absolute',path:value}
  const [file, fragment]=value.split('#',2)
  const parts=basePath.split('/').slice(0,-1)
  for(const part of file.split('/')) {
    if(!part || part==='.')continue
    if(part==='..') {
      if(!parts.length)return {kind:'absolute',path:value}
      parts.pop()
    } else parts.push(part)
  }
  const path=parts.join('/')
  return {kind:/\.(md|txt|json)$/i.test(path)?'doc':'absolute',path,...(fragment?{hash:fragment}:{})}
}

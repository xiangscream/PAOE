import MarkdownIt from './vendor/markdown-it-15.0.3.mjs';

// Room messages are text, never executable HTML or automatically fetched media.
const markdown = new MarkdownIt({html:false, linkify:true, breaks:true});
markdown.disable('image');
markdown.validateLink = url => /^https?:\/\//i.test(url);
markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index].attrSet('target', '_blank');
  tokens[index].attrSet('rel', 'noopener noreferrer');
  return renderer.renderToken(tokens, index, options);
};

function markedText(text, query) {
  const escape = markdown.utils.escapeHtml;
  if (!query) return escape(text);
  const pattern = new RegExp(query.replace(/[.*+?^$(){}|[\]\\]/g, '\\$&'), 'giu');
  const parts = [];
  let end = 0;
  for (const match of text.matchAll(pattern)) {
    parts.push(escape(text.slice(end, match.index)), '<mark>' + escape(match[0]) + '</mark>');
    end = match.index + match[0].length;
  }
  return parts.join('') + escape(text.slice(end));
}

markdown.renderer.rules.text = (tokens, index, options, env) => markedText(tokens[index].content, env.query);
markdown.renderer.rules.code_inline = (tokens, index, options, env) =>
  '<code>' + markedText(tokens[index].content, env.query) + '</code>';
markdown.renderer.rules.fence = (tokens, index, options, env) => {
  const language = tokens[index].info.trim().split(/\s+/)[0];
  const attribute = language ? ' class="language-' + markdown.utils.escapeHtml(language) + '"' : '';
  return '<pre><code' + attribute + '>' + markedText(tokens[index].content, env.query) + '</code></pre>\n';
};
markdown.renderer.rules.code_block = (tokens, index, options, env) =>
  '<pre><code>' + markedText(tokens[index].content, env.query) + '</code></pre>\n';

export const renderMessage = (body, query='') => markdown.render(body, {query:query.trim()});

export function findMessages(messages, query) {
  const needle = query.trim().toLocaleLowerCase();
  return needle ? messages.filter(message => message.body.toLocaleLowerCase().includes(needle)) : [];
}

export function messagePreview(body) {
  const parts = [];
  for (const token of markdown.parse(body, {})) {
    if (token.type === 'inline') {
      parts.push(token.children.map(child =>
        child.type === 'text' || child.type === 'code_inline' ? child.content :
        child.type === 'softbreak' || child.type === 'hardbreak' ? ' ' : '').join(''));
    } else if (token.type === 'fence' || token.type === 'code_block') {
      parts.push(token.content);
    }
  }
  const text = parts.join(' ').replace(/\s+/g, ' ').trim();
  return text.slice(0,160) + (text.length>160?'…':'');
}

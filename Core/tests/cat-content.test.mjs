import test from 'node:test';
import assert from 'node:assert/strict';
import {renderMessage, findMessages, messagePreview} from '../front/cat-content.mjs';

test('message formatting keeps literal code and the original text intact', () => {
  const source = '**结论**\n\n- 可以回复\n- 保留原文\n\n```js\nconst value = "<b>&";\n```';
  const html = renderMessage(source);
  assert.match(html, /<strong>结论<\/strong>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<pre><code class="language-js">/);
  assert.match(html, /&lt;b&gt;&amp;/);
  assert.equal(source.includes('const value = "<b>&";'), true);
});

test('raw HTML and dangerous protocols cannot become active room content', () => {
  const html = renderMessage('<img src=x onerror=alert(1)>\n\n[bad](javascript:alert(1))\n[local](file:///private.txt)\n[x](data:text/html,hello)');
  assert.doesNotMatch(html, /<img|href="(?:javascript|file|data):/i);
  assert.match(html, /&lt;img/);
});

test('web links use a separate tab and remote media never loads automatically', () => {
  const html = renderMessage('[来源](https://example.com/?a=1&b=2)\n\nhttps://example.org\n\n![图片](https://example.com/image.png)');
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /href="https:\/\/example.org"/);
  assert.doesNotMatch(html, /<img|<iframe|<script/i);
});

test('room search includes the full original body, preserves order and ignores an empty query', () => {
  const messages = [
    {id:'one',body:'第一段\n'.repeat(100)+'青柠 hidden NEEDLE'},
    {id:'two',body:'无匹配'},
    {id:'three',body:'needle 与青柠'},
  ];
  const original = structuredClone(messages);
  assert.deepEqual(findMessages(messages,'  NeEdLe ').map(m=>m.id), ['one','three']);
  assert.deepEqual(findMessages(messages,'青柠').map(m=>m.id), ['one','three']);
  assert.deepEqual(findMessages(messages,'  '), []);
  assert.deepEqual(findMessages(messages,'不存在'), []);
  assert.deepEqual(messages, original);
});

test('search highlighting escapes text and treats metacharacters as literal content', () => {
  const html = renderMessage('**青柠**\n\n`notes/青柠.md`\n\n```js\n青柠\n```','青柠');
  assert.equal((html.match(/<mark>青柠<\/mark>/g)||[]).length, 3);
  assert.match(renderMessage('a.*b and axxb','.*'), /a<mark>\.\*<\/mark>b and axxb/);
  const unsafe = renderMessage('<img src=x onerror=alert(1)>','<img');
  assert.doesNotMatch(unsafe, /<img/);
  assert.match(unsafe, /<mark>&lt;img<\/mark>/);
});

test('reply previews show readable text and code without Markdown control characters', () => {
  const body = '## 标题\n\n**重点** 和 [说明](https://example.com)\n\n`notes.md`';
  assert.equal(messagePreview(body), '标题 重点 和 说明 notes.md');
  assert.equal(messagePreview('长'.repeat(200)), '长'.repeat(160)+'…');
  assert.equal(body.includes('**重点**'), true);
});

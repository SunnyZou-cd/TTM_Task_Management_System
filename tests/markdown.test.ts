import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { applyMarkdownEdits, markdownLeaves, parseMarkdown } from '../src/shared/markdown-edit';
import { MarkdownView } from '../src/renderer/Markdown';

function leaves(source: string) { return markdownLeaves(parseMarkdown(source), source); }
function edit(source: string, original: string, next: string) {
  const leaf = leaves(source).find(leaf => leaf.value === original);
  if (!leaf) throw new Error(`Missing fixture leaf: ${original}`);
  return applyMarkdownEdits(source, new Map([[leaf.id, next]]));
}
describe('Markdown leaf edits preserve the surrounding source', () => {
  it('replaces multiple dirty ranges from the end while retaining headings, tasks, emphasis and link destinations', () => {
    const source = '# Title\n\n- [x] **First** and [second](https://example.org "keep")\n';
    const all = leaves(source);
    const changed = applyMarkdownEdits(source, new Map(all.filter(leaf => ['Title', 'First', 'second'].includes(leaf.value)).map(leaf => [leaf.id, `${leaf.value}!`])));
    expect(changed).toBe('# Title\\!\n\n- [x] **First\\!** and [second\\!](https://example.org "keep")\n');
    expect(leaves(changed).map(leaf => leaf.value)).toEqual(['Title!', 'First!', ' and ', 'second!']);
  });
  it('uses complete source ranges for decoded entities and escaped punctuation', () => {
    const source = '## A &amp; B \\*literal\\*\n\n**bold &copy;**';
    const changed = edit(source, 'A & B *literal*', 'A & B <tag>');
    expect(changed).toBe('## A \\& B \\<tag\\>\n\n**bold &copy;**');
    expect(leaves(changed)[0].value).toBe('A & B <tag>');
  });
  it('keeps new punctuation, edge whitespace and newlines inside the original bold leaf', () => {
    const source = '**old**';
    const text = ' *new*\n<script> &amp; ';
    const changed = edit(source, 'old', text);
    expect(changed.startsWith('**&#32;')).toBe(true);
    expect(changed.endsWith('&#32;**')).toBe(true);
    expect(leaves(changed)[0].value).toBe(text);
    expect(parseMarkdown(changed).children?.[0].children?.[0].type).toBe('strong');
  });
  it('escapes pipes in tables without changing cell count or task completion', () => {
    const source = '| Left | Right |\n| --- | --- |\n| value | ~~done~~ |\n\n- [ ] Task';
    const changed = edit(source, 'value', '[x] | ![image](https://host/pixel)');
    expect(leaves(changed).find(leaf => leaf.value.includes('pixel'))?.value).toBe('[x] | ![image](https://host/pixel)');
    expect(changed).toContain('- [ ] Task');
    expect(parseMarkdown(changed).children?.[0].children?.[1].children).toHaveLength(2);
  });
  it('retains inline code delimiters and decoded edge spaces', () => {
    expect(edit('``old``', 'old', 'new`value')).toBe('``new`value``');
    expect(leaves(edit('`old`', 'old', ' both '))[0].value).toBe(' both ');
    expect(() => edit('`old`', 'old', 'break`boundary')).toThrow(/反引号/);
  });
  it('preserves fenced code language, delimiters and multiline content', () => {
    const source = '```ts\nconst old = 1;\n```\n\nAfter';
    const changed = edit(source, 'const old = 1;', 'const next = 2;\nconsole.log(next);');
    expect(changed).toBe('```ts\nconst next = 2;\nconsole.log(next);\n```\n\nAfter');
    expect(() => edit(source, 'const old = 1;', 'safe\n```\n# escaped')).toThrow(/围栏/);
  });
  it('refuses structural deletion, stale ranges and indentation changes instead of silently losing source', () => {
    expect(() => edit('**old**', 'old', '')).toThrow(/改变原有格式/);
    expect(() => applyMarkdownEdits('new', new Map([['stale', 'draft']]))).toThrow(/位置已变化/);
    expect(() => edit('    old', 'old', 'new')).toThrow(/缩进/);
  });
  it('does not rewrite an unchanged decoded leaf and safely creates text in an empty note', () => {
    const source = '# A &amp; B';
    expect(edit(source, 'A & B', 'A & B')).toBe(source);
    expect(leaves(applyMarkdownEdits('', new Map([['empty', '# **plain**']])))[0].value).toBe('# **plain**');
  });
});
describe('Markdown display is inert', () => {
  it('shows raw HTML and image labels without executing HTML, loading media or enabling navigation', () => {
    const html = renderToStaticMarkup(createElement(MarkdownView, { value: '<script>alert(1)</script>\n\n<img src="https://host/pixel">\n\n![remote](https://host/image)\n\n[link](javascript:alert(1))' }));
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<img');
    expect(html).not.toContain('href=');
    expect(html).not.toContain('<button');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('[图片：remote]');
  });
  it('renders GFM lists, strikeout, tables, code and empty states', () => {
    const html = renderToStaticMarkup(createElement(MarkdownView, { value: '- [x] ~~done~~\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n```js\nlet a = 1;\n```' }));
    expect(html).toContain('已完成'); expect(html).toContain('<del>done</del>');
    expect(html).toContain('<table>'); expect(html).toContain('<pre>');
    expect(renderToStaticMarkup(createElement(MarkdownView, { value: '' }))).toContain('暂无内容');
  });
  it('renders title mode without block elements or interactive links', () => {
    const html = renderToStaticMarkup(createElement(MarkdownView, { value: '# **Title** [link](https://host)', inline: true }));
    expect(html).toContain('<strong>Title</strong>');
    expect(html).not.toMatch(/<(div|p|h1|a|button)[ >]/);
  });
});

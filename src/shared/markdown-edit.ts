import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';

export interface MarkdownNode {
  type: string;
  value?: string;
  children?: MarkdownNode[];
  position?: { start: { offset?: number }; end: { offset?: number } };
  [key: string]: unknown;
}
export interface MarkdownLeaf {
  id: string;
  type: 'text' | 'inlineCode' | 'code' | 'empty';
  value: string;
  start: number;
  end: number;
}
const parser = unified().use(remarkParse).use(remarkGfm);
export function parseMarkdown(source: string): MarkdownNode {
  return parser.parse(source) as unknown as MarkdownNode;
}
export function markdownLeaves(tree: MarkdownNode, source: string): MarkdownLeaf[] {
  const leaves: MarkdownLeaf[] = [];
  const visit = (node: MarkdownNode) => {
    const start = node.position?.start.offset;
    const end = node.position?.end.offset;
    if ((node.type === 'text' || node.type === 'inlineCode' || node.type === 'code') && start !== undefined && end !== undefined) {
      leaves.push({ id: `${start}:${end}:${node.type}`, type: node.type, value: node.value ?? '', start, end });
    }
    node.children?.forEach(visit);
  };
  visit(tree);
  if (!source.trim()) leaves.push({ id: 'empty', type: 'empty', value: '', start: 0, end: source.length });
  return leaves;
}
export class MarkdownEditError extends Error {
  constructor(message: string) { super(message); this.name = 'MarkdownEditError'; }
}

// Punctuation and edge spaces must remain literal even inside emphasis, tables and links.
export function escapeMarkdownText(value: string): string {
  return value.replace(/[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/g, '\\$&')
    .replace(/\r\n?|\n/g, '&#10;').replace(/\t/g, '&#9;')
    .replace(/^ +| +$/g, spaces => '&#32;'.repeat(spaces.length));
}
function replaceCode(source: string, leaf: MarkdownLeaf, value: string): string {
  const slice = source.slice(leaf.start, leaf.end);
  if (leaf.type === 'inlineCode') {
    const ticks = slice.match(/^`+/)?.[0];
    if (!ticks || value.includes('\n') || value.includes('\r') || value.includes(ticks)) {
      throw new MarkdownEditError('这段代码包含会改变反引号边界的文字，请在主界面编辑 Markdown 源文。');
    }
    const padded = (/^`|`$/.test(value) || /^ .* $/.test(value) && /[^ ]/.test(value)) ? ` ${value} ` : value;
    return `${ticks}${padded}${ticks}`;
  }
  const opening = slice.match(/^( {0,3})(`{3,}|~{3,})[^\r\n]*(\r?\n|$)/);
  if (!opening || opening[1]) {
    throw new MarkdownEditError('缩进代码块需要在主界面编辑 Markdown 源文，以保留原有缩进。');
  }
  const marker = opening[2];
  if (value.split(/\r?\n/).some(line => new RegExp(`^ {0,3}${marker[0] === '`' ? '`' : '~'}{${marker.length},}`).test(line))) {
    throw new MarkdownEditError('代码文字包含结束围栏，请在主界面编辑 Markdown 源文。');
  }
  const tail = slice.slice(opening[0].length);
  const closing = tail.match(new RegExp(`(?:^|\\r?\\n)( {0,3}${marker[0] === '`' ? '`' : '~'}{${marker.length},}[ \\t]*)$`));
  const ending = closing ? `${opening[3] || '\n'}${closing[1]}` : '';
  return opening[0] + value.replace(/\r\n?/g, '\n') + ending;
}
function structure(node: MarkdownNode): unknown {
  const { position: _position, children, value, ...rest } = node;
  return { ...rest, ...(['text', 'inlineCode', 'code'].includes(node.type) ? {} : value === undefined ? {} : { value }), ...(children ? { children: children.map(structure) } : {}) };
}

/** Replaces decoded leaf values against their complete original source ranges. */
export function applyMarkdownEdits(source: string, edits: ReadonlyMap<string, string>): string {
  const tree = parseMarkdown(source);
  const leaves = markdownLeaves(tree, source);
  const replacements: { start: number; end: number; text: string }[] = [];
  for (const [id, value] of edits) {
    const leaf = leaves.find(candidate => candidate.id === id);
    if (!leaf) throw new MarkdownEditError('文字位置已变化，本地草稿已保留。请先处理内容冲突。');
    if (value === leaf.value) continue;
    if (leaf.type === 'empty') return escapeMarkdownText(value);
    const text = leaf.type === 'text' ? escapeMarkdownText(value) : replaceCode(source, leaf, value);
    replacements.push({ start: leaf.start, end: leaf.end, text });
  }
  let result = source;
  for (const replacement of replacements.sort((a, b) => b.start - a.start)) {
    result = result.slice(0, replacement.start) + replacement.text + result.slice(replacement.end);
  }
  const nextTree = parseMarkdown(result);
  if (JSON.stringify(structure(tree)) !== JSON.stringify(structure(nextTree))) {
    throw new MarkdownEditError('这次修改会改变原有格式，本地草稿已保留。请在主界面编辑 Markdown 源文。');
  }
  const nextLeaves = markdownLeaves(nextTree, result);
  if (leaves.some((leaf, index) => nextLeaves[index]?.value !== (edits.get(leaf.id) ?? leaf.value))) {
    throw new MarkdownEditError('这次修改无法完整保留文字，本地草稿已保留。请在主界面编辑 Markdown 源文。');
  }
  return result;
}

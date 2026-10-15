import { Fragment, forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode } from 'react';
import { Square, SquareCheck } from 'lucide-react';
import { applyMarkdownEdits, markdownLeaves, parseMarkdown, type MarkdownLeaf, type MarkdownNode } from '../shared/markdown-edit';
import './markdown.css';

export interface MarkdownProps { value: string; inline?: boolean; className?: string; emptyText?: string }
export interface EditableMarkdownHandle { /** null = no change; throws on conflict or unsafe format changes. */ flush(): string | null }
export interface EditableMarkdownProps extends MarkdownProps { onChange(value: string): void; onDirty?(): void; ariaLabel?: string }

type LeafRenderer = (leaf: MarkdownLeaf) => ReactNode;
function renderTree(tree: MarkdownNode, source: string, inline: boolean, editable?: LeafRenderer): ReactNode {
  const leaves = new Map(markdownLeaves(tree, source).map(leaf => [leaf.id, leaf]));
  const render = (node: MarkdownNode, key: string): ReactNode => {
    const id = `${node.position?.start.offset}:${node.position?.end.offset}:${node.type}`;
    const leaf = leaves.get(id);
    const children = node.children?.map((child, index) => render(child, `${key}.${index}`));
    const text = leaf && editable ? editable(leaf) : node.value;
    if (inline && ['root', 'paragraph', 'heading', 'blockquote', 'list', 'listItem', 'table', 'tableRow', 'tableCell'].includes(node.type)) {
      return <Fragment key={key}>{children}{['paragraph', 'heading', 'listItem', 'tableCell', 'blockquote'].includes(node.type) && ' '}</Fragment>;
    }
    switch (node.type) {
      case 'root': return <Fragment key={key}>{children}</Fragment>;
      case 'text': return <Fragment key={key}>{text}</Fragment>;
      case 'paragraph': return <p key={key}>{children}</p>;
      case 'heading': { const Tag = `h${node.depth}` as 'h1'; return <Tag key={key}>{children}</Tag>; }
      case 'strong': return <strong key={key}>{children}</strong>;
      case 'emphasis': return <em key={key}>{children}</em>;
      case 'delete': return <del key={key}>{children}</del>;
      case 'inlineCode': return <code key={key}>{text}</code>;
      case 'code': return inline ? <code key={key}>{text}</code> : <pre key={key}><code>{text}</code></pre>;
      case 'blockquote': return <blockquote key={key}>{children}</blockquote>;
      case 'list': return node.ordered ? <ol key={key} start={typeof node.start === 'number' ? node.start : undefined}>{children}</ol> : <ul key={key}>{children}</ul>;
      case 'listItem': return <li key={key} className={typeof node.checked === 'boolean' ? 'markdown-task' : undefined}>{typeof node.checked === 'boolean' && <span className="markdown-task-check" aria-label={node.checked ? '已完成' : '未完成'}>{node.checked ? <SquareCheck size={14}/> : <Square size={14}/>}</span>}{children}</li>;
      case 'link': case 'linkReference': return <span key={key} className="markdown-link" title={typeof node.url === 'string' ? node.url : 'Markdown 链接'}>{children}</span>;
      case 'image': case 'imageReference': return <span key={key} className="markdown-image" title="图片不自动加载">[图片：{String(node.alt || '无说明')}]</span>;
      case 'html': return <span key={key} className="markdown-html">{node.value}</span>;
      case 'break': return inline ? ' ' : <br key={key}/>;
      case 'thematicBreak': return inline ? ' ' : <hr key={key}/>;
      case 'table': return <div key={key} className="markdown-table-scroll"><table><tbody>{children}</tbody></table></div>;
      case 'tableRow': return <tr key={key}>{children}</tr>;
      case 'tableCell': return <td key={key}>{children}</td>;
      case 'definition': return null;
      default: return <Fragment key={key}>{children ?? node.value}</Fragment>;
    }
  };
  return render(tree, 'root');
}
export function MarkdownView({ value, inline = false, className = '', emptyText = '暂无内容' }: MarkdownProps) {
  const tree = useMemo(() => parseMarkdown(value), [value]);
  const Tag = inline ? 'span' : 'div';
  return <Tag className={`markdown ${inline ? 'markdown-inline' : ''} ${className}`}>{value.trim() ? renderTree(tree, value, inline) : <span className="markdown-empty">{emptyText}</span>}</Tag>;
}

export const EditableMarkdown = forwardRef<EditableMarkdownHandle, EditableMarkdownProps>(function EditableMarkdown({ value, onChange, onDirty, inline = false, className = '', ariaLabel = 'Markdown 文字', emptyText = '点击添加文字' }, ref) {
  const [source, setSource] = useState(value);
  const [error, setError] = useState('');
  const sourceRef = useRef(source);
  const received = useRef(value);
  const currentValue = useRef(value); currentValue.current = value;
  const drafts = useRef(new Map<string, string>());
  const elements = useRef(new Map<string, HTMLElement>());
  const callbacks = useRef({ onChange, onDirty }); callbacks.current = { onChange, onDirty };
  const syncExternal = useCallback(() => {
    const next = currentValue.current;
    if (next === received.current) return;
    if (next === sourceRef.current) { received.current = next; return; }
    if (drafts.current.size) throw new Error('其他窗口或同步更新了这条内容。本地草稿已保留，请先处理冲突再关闭。');
    received.current = next; sourceRef.current = next; setSource(next);
  }, []);
  useEffect(() => { try { syncExternal(); setError(''); } catch (reason) { setError((reason as Error).message); } }, [value, syncExternal]);
  const flush = useCallback(() => {
    try {
      syncExternal();
      if (!drafts.current.size) return null;
      const next = applyMarkdownEdits(sourceRef.current, drafts.current);
      const changed = next !== sourceRef.current;
      sourceRef.current = next; drafts.current.clear(); setSource(next); setError('');
      if (changed) callbacks.current.onChange(next);
      return changed ? next : null;
    } catch (reason) { setError((reason as Error).message); throw reason; }
  }, [syncExternal]);
  useImperativeHandle(ref, () => ({ flush }), [flush]);
  const tree = useMemo(() => parseMarkdown(source), [source]);
  const record = (leaf: MarkdownLeaf, element: HTMLElement) => {
    const text = element.textContent ?? '';
    if (text === leaf.value) drafts.current.delete(leaf.id); else drafts.current.set(leaf.id, text);
    callbacks.current.onDirty?.();
  };
  const renderLeaf = (leaf: MarkdownLeaf) => <span key={leaf.id} ref={element => { if (element) elements.current.set(leaf.id, element); else elements.current.delete(leaf.id); }} className={`markdown-leaf ${leaf.type === 'code' ? 'markdown-code-leaf' : ''}`} contentEditable suppressContentEditableWarning role="textbox" aria-label={ariaLabel} aria-multiline={leaf.type === 'code'} data-placeholder={leaf.type === 'empty' ? emptyText : undefined} spellCheck={leaf.type === 'text' || leaf.type === 'empty'} onInput={event => record(leaf, event.currentTarget)} onBlur={() => { try { flush(); } catch { /* Alert and draft remain visible. */ } }} onKeyDown={event => { if (event.key === 'Enter' && leaf.type !== 'code') event.preventDefault(); if ((event.ctrlKey || event.metaKey) && ['b', 'i', 'u', 'k'].includes(event.key.toLowerCase())) event.preventDefault(); }} onBeforeInput={event => { const input = event.nativeEvent as InputEvent; if (input.inputType.startsWith('format') || leaf.type !== 'code' && ['insertParagraph', 'insertLineBreak'].includes(input.inputType)) event.preventDefault(); }} onPaste={event => {
    event.preventDefault();
    const plain = event.clipboardData.getData('text/plain').replace(/\r\n?/g, '\n');
    const text = leaf.type === 'code' ? plain : plain.replace(/\n/g, ' ');
    // insertText keeps the browser undo stack while refusing pasted HTML.
    document.execCommand('insertText', false, text); record(leaf, event.currentTarget);
  }} onDrop={event => event.preventDefault()}>{leaf.value}</span>;
  const Tag = inline ? 'span' : 'div';
  return <Tag className={`markdown markdown-editable ${inline ? 'markdown-inline' : ''} ${className}`} data-edit-error={error ? true : undefined}>{source.trim() ? renderTree(tree, source, inline, renderLeaf) : renderLeaf(markdownLeaves(tree, source)[0])}{error && <span className="markdown-edit-error" role="alert">{error}</span>}</Tag>;
});

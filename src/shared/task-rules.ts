import type { TaskRecurrence } from './types';

export function validCalendarDate(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value);
}
export function validDueTime(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value));
}
export function validTags(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 30 && value.every(tag => typeof tag === 'string' && tag.trim().length > 0 && tag.length <= 40);
}
export function validRecurrence(value: unknown): value is TaskRecurrence | null {
  if (value === null) return true;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const rule = value as TaskRecurrence;
  return Object.keys(value).every(key => key === 'frequency' || key === 'interval') && ['daily', 'weekly', 'monthly'].includes(rule.frequency) && Number.isInteger(rule.interval) && rule.interval >= 1 && rule.interval <= 365;
}

/** Read explicit Obsidian task metadata without guessing ordinary dates in prose. */
export function parseTaskMetadata(title: string): { dueDate?: string; tags: string[] } {
  const markedDate = title.match(/(?:📅|📆|🗓️?)\s*(\d{4}-\d{2}-\d{2})(?!\d)/)?.[1];
  const tags: string[] = [];
  for (const match of title.matchAll(/(?:^|\s)#([\p{L}\p{N}_/-]+)/gu)) tags.push(match[1]);
  for (const match of title.matchAll(/\[\[([^\]|#]+)(?:[^\]]*)\]\]/g)) {
    const name = match[1].split('/').pop()?.replace(/\.md$/i, '').trim(); if (name) tags.push(name);
  }
  return { ...(markedDate && validCalendarDate(markedDate) ? { dueDate: markedDate } : {}), tags: [...new Set(tags.filter(tag => tag.length <= 40))].slice(0, 30) };
}

/** Calendar arithmetic deliberately avoids elapsed local hours across DST. */
export function occurrenceDate(anchor: string, recurrence: TaskRecurrence, index: number): string {
  if (!anchor || !validCalendarDate(anchor) || !validRecurrence(recurrence) || !Number.isSafeInteger(index) || index < 0) throw new Error('循环日期无效');
  const date = new Date(`${anchor}T00:00:00.000Z`);
  if (recurrence.frequency === 'monthly') {
    const day = date.getUTCDate();
    date.setUTCDate(1);
    date.setUTCMonth(date.getUTCMonth() + index * recurrence.interval);
    const end = new Date(date.getTime()); end.setUTCMonth(end.getUTCMonth() + 1); end.setUTCDate(0);
    date.setUTCDate(Math.min(day, end.getUTCDate()));
  } else date.setUTCDate(date.getUTCDate() + index * recurrence.interval * (recurrence.frequency === 'weekly' ? 7 : 1));
  if (!Number.isFinite(date.getTime()) || date.getUTCFullYear() > 9999) throw new Error('循环日期超出范围');
  return date.toISOString().slice(0, 10);
}

/** Missed schedules backfill only the latest 30 due occurrences, never an unbounded history. */
export function dueOccurrences(anchor: string, dueTime: string | null, recurrence: TaskRecurrence, now = new Date()): { dueDate: string; index: number }[] {
  if (!anchor || !validCalendarDate(anchor) || !validDueTime(dueTime) || !validRecurrence(recurrence) || !Number.isFinite(now.getTime())) throw new Error('循环日期无效');
  const today = `${String(now.getFullYear()).padStart(4, '0')}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const clock = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  let latest: number;
  if (recurrence.frequency === 'monthly') {
    latest = Math.floor(((now.getFullYear() - Number(anchor.slice(0, 4))) * 12 + now.getMonth() + 1 - Number(anchor.slice(5, 7))) / recurrence.interval);
  } else latest = Math.floor((Date.parse(today) - Date.parse(anchor)) / 86400000 / recurrence.interval / (recurrence.frequency === 'weekly' ? 7 : 1));
  if (latest < 1) return [];
  const latestDate = occurrenceDate(anchor, recurrence, latest);
  if (latestDate > today || (latestDate === today && clock < (dueTime ?? '00:00'))) latest--;
  const result: { dueDate: string; index: number }[] = [];
  for (let index = Math.max(1, latest - 29); index <= latest; index++) result.push({ dueDate: occurrenceDate(anchor, recurrence, index), index });
  return result;
}

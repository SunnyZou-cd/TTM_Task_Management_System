import type { Item } from '../shared/types';
export function dateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
export function taskStats(items: Item[], today: string) {
  const tasks = items.filter(item => item.kind === 'task' && !item.deletedAt);
  const completed = tasks.filter(item => item.completed).length;
  return { total: tasks.length, completed, remaining: tasks.length-completed,
    percentage: tasks.length ? Math.round(completed/tasks.length*100) : 0,
    overdue: tasks.filter(item => !item.completed && item.dueDate && item.dueDate < today).length,
    today: tasks.filter(item => !item.completed && item.dueDate === today).length,
    undated: tasks.filter(item => !item.completed && !item.dueDate).length };
}
export function monthDays(year: number, month: number) {
  const first = new Date(year, month, 1, 12);
  const offset = (first.getDay()+6)%7;
  const count = new Date(year, month+1, 0, 12).getDate();
  return Array.from({length: Math.ceil((offset+count)/7)*7}, (_, index) => {
    const date = new Date(year, month, index-offset+1, 12);
    return { key: dateKey(date), day: date.getDate(), inMonth: date.getMonth() === month };
  });
}

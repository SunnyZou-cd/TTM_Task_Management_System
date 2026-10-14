import { describe, expect, it } from 'vitest';
import type { Item } from '../src/shared/types';
import { monthDays, taskStats } from '../src/renderer/management-logic';
function item(patch: Partial<Item> = {}): Item { return {id:'task',ownerId:null,kind:'task',title:'任务',body:'',dueDate:null,completed:false,color:'sage',createdAt:'2026-10-14T00:00:00Z',updatedAt:'2026-10-14T00:00:00Z',deletedAt:null,deviceId:'test',...patch}; }
describe('management views use current task data', () => {
 it('excludes notes/deleted tasks and does not treat completed overdue dates as outstanding', () => {
  expect(taskStats([item({dueDate:'2026-10-13'}),item({dueDate:'2026-10-14'}),item({completed:true,dueDate:'2026-10-10'}),item(),item({kind:'note'}),item({deletedAt:'2026-10-14T01:00:00Z'})], '2026-10-14')).toEqual({total:4,completed:1,remaining:3,percentage:25,overdue:1,today:1,undated:1});
 });
 it('has a defined zero progress for an empty workspace', () => {expect(taskStats([], '2026-10-14').percentage).toBe(0);});
 it('places leap February on Monday-first complete weeks without skipping month boundaries', () => {
  const days=monthDays(2028,1);expect(days[0].key).toBe('2028-01-31');expect(days.filter(day=>day.inMonth)).toHaveLength(29);expect(days.at(-1)?.key).toBe('2028-03-05');expect(days.length%7).toBe(0);
 });
 it('keeps year rollover date keys correct', () => {expect(monthDays(2027,0)[0].key).toBe('2026-12-28');});
});

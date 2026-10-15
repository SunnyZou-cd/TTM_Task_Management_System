import { describe, expect, it } from 'vitest';
import { dueOccurrences, occurrenceDate, parseTaskMetadata, validDueTime, validRecurrence, validTags } from '../src/shared/task-rules';

describe('calendar schedules and task metadata', () => {
  it('checks clock times, tags, and interval shapes', () => {
    expect(validDueTime('23:59')).toBe(true); expect(validDueTime('24:00')).toBe(false); expect(validDueTime('9:30')).toBe(false);
    expect(validTags(['研究', 'project-a'])).toBe(true); expect(validTags([''])).toBe(false); expect(validTags('tag')).toBe(false);
    for (const rule of [{ frequency: 'hourly', interval: 1 }, { frequency: 'daily', interval: 0 }, { frequency: 'daily', interval: 1.5 }, { frequency: 'daily', interval: 366 }, { frequency: 'daily', interval: 1, extra: true }]) expect(validRecurrence(rule)).toBe(false);
  });
  it('uses calendar days and intervals across years', () => {
    expect(occurrenceDate('2026-12-31', { frequency: 'daily', interval: 2 }, 1)).toBe('2027-01-02');
    expect(occurrenceDate('2026-12-31', { frequency: 'weekly', interval: 2 }, 1)).toBe('2027-01-14');
  });
  it('clamps month ends without permanently drifting the day', () => {
    const rule = { frequency: 'monthly', interval: 1 } as const;
    expect(occurrenceDate('2026-01-31', rule, 1)).toBe('2026-02-28');
    expect(occurrenceDate('2026-01-31', rule, 2)).toBe('2026-03-31');
    expect(occurrenceDate('2024-01-31', rule, 1)).toBe('2024-02-29');
  });
  it('waits until the local wall clock reaches the scheduled time', () => {
    const rule = { frequency: 'daily', interval: 1 } as const;
    expect(dueOccurrences('2026-10-13', '09:30', rule, new Date(2026, 9, 14, 9, 29))).toEqual([]);
    expect(dueOccurrences('2026-10-13', '09:30', rule, new Date(2026, 9, 14, 9, 30))).toEqual([{ dueDate: '2026-10-14', index: 1 }]);
    expect(dueOccurrences('2026-10-13', null, rule, new Date(2026, 9, 14, 0))).toHaveLength(1);
  });
  it('bounds missed history to 30 instances and skips future schedules', () => {
    const rule = { frequency: 'daily', interval: 1 } as const;
    const result = dueOccurrences('2016-01-01', null, rule, new Date(2026, 9, 14));
    expect(result).toHaveLength(30); expect(result[0].dueDate).toBe('2026-09-15'); expect(result.at(-1)?.dueDate).toBe('2026-10-14');
    expect(dueOccurrences('2027-01-01', null, rule, new Date(2026, 9, 14))).toEqual([]);
  });
  it('checks month-end time before generating the next instance', () => {
    const rule = { frequency: 'monthly', interval: 1 } as const;
    expect(dueOccurrences('2026-01-31', '12:00', rule, new Date(2026, 1, 28, 11))).toEqual([]);
    expect(dueOccurrences('2026-01-31', '12:00', rule, new Date(2026, 1, 28, 12))).toEqual([{ dueDate: '2026-02-28', index: 1 }]);
  });
  it('extracts explicit dates, hashtags, and Projects links without prose date guesses', () => {
    expect(parseTaskMetadata('交作业 📅 2026-08-30 #物理 #物理 [[Projects/Physics Lab|实验]]')).toEqual({ dueDate: '2026-08-30', tags: ['物理', 'Physics Lab'] });
    expect(parseTaskMetadata('记录 2026-08-30 📆 2026-02-30')).toEqual({ tags: [] });
    expect(parseTaskMetadata('准备 🗓️ 2026-10-14 [[Projects/Study.md]]')).toEqual({ dueDate: '2026-10-14', tags: ['Study'] });
  });
});

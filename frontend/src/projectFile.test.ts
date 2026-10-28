import { describe, expect, it } from 'vitest';
import { emptyProject, isStale, normalizeProject, safeFileName } from './projectFile';
import type { RunResult } from './types';

const run = (code: string): RunResult => ({
  status: 'done', startedAt: '', durationMs: 1, code, stdout: '', stderr: '', outputTruncated: false,
  error: null, partial: false, notice: null, graph: { nodes: [], edges: [], notes: [], dropped: 0 },
});

describe('проект', () => {
  it('нормализация подставляет значения по умолчанию', () => {
    const p = normalizeProject({});
    expect(p.name).toBe('Без названия');
    expect(p.code).toBe('');
    expect(p.run).toBeNull();
    expect(p.id).toMatch(/^proj-[0-9a-f]{10}$/);
  });

  it('повреждённый результат запуска отбрасывается', () => {
    expect(normalizeProject({ code: 'a = 1', run: { status: 'done' } as unknown as RunResult }).run).toBeNull();
  });

  it('схема устаревает, как только код отличается от запущенного', () => {
    const p = normalizeProject({ code: 'a = 1', run: run('a = 1') });
    expect(isStale(p)).toBe(false);
    expect(isStale({ ...p, code: 'a = 2' })).toBe(true);
    expect(isStale({ ...p, code: 'a = 1 ' })).toBe(true);
    expect(isStale({ ...p, run: null })).toBe(false); // запуска не было — устаревать нечему
  });

  it('новый проект содержит запускаемый пример', () => {
    expect(emptyProject().code).toContain('import numpy')
  });
});

describe('имена файлов', () => {
  it('убирает недопустимые символы Windows', () => {
    expect(safeFileName('a/b:c*?"<>|', 'py')).toBe('a_b_c______.py');
    expect(safeFileName('   ', 'md')).toBe('проект.md');
    expect(safeFileName('Булева маска', 'json')).toBe('Булева маска.json');
  });
});

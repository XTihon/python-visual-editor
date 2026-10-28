import type { Project, RunResult } from './types';

export function newId(prefix: string): string {
  const bytes = new Uint8Array(5);
  crypto.getRandomValues(bytes);
  return prefix + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

const str = (value: unknown, fallback = ''): string => (typeof value === 'string' ? value : fallback);

/** Приводит ответ сервера к Project, подставляя безопасные значения по умолчанию. */
export function normalizeProject(raw: Partial<Project>): Project {
  const run = raw.run;
  return {
    schemaVersion: 2,
    id: str(raw.id) || newId('proj-'),
    name: str(raw.name, 'Без названия').trim() || 'Без названия',
    code: str(raw.code),
    run: typeof run === 'object' && run !== null && typeof run.graph === 'object' ? (run as RunResult) : null,
    createdAt: str(raw.createdAt),
    updatedAt: str(raw.updatedAt),
    migratedFrom: raw.migratedFrom ?? null,
    original: raw.original ?? null,
  };
}

export function emptyProject(): Project {
  return normalizeProject({
    id: newId('proj-'),
    name: 'Без названия',
    code: 'import numpy as np\n\na = np.array([1, 2, 3])\nb = a * 2\nprint(b)\n',
  });
}

/** Схема устарела, если код изменён после запуска, по которому она построена. */
export function isStale(project: Project): boolean {
  return project.run !== null && project.run.code !== project.code;
}

export function safeFileName(name: string, extension: string): string {
  const cleaned = name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[. ]+$/g, '').trim() || 'проект';
  return `${cleaned.slice(0, 80)}.${extension}`;
}

export function downloadText(filename: string, text: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

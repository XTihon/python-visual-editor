import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api', () => ({
  api: {
    run: vi.fn(),
    loadProject: vi.fn(),
    loadExample: vi.fn(),
    listProjects: vi.fn(),
    listExamples: vi.fn(),
  },
}));

import { api } from './api';
import { emptyProject, normalizeProject } from './projectFile';
import { useStore } from './store';
import type { RunResult } from './types';

const fakeRun = (code: string): RunResult => ({
  status: 'done', startedAt: '', durationMs: 1, code, stdout: 'out\n', stderr: '', outputTruncated: false,
  error: null, partial: false, notice: null, graph: { nodes: [], edges: [], notes: [], dropped: 0 },
});

/** Промис запуска, который тест завершает вручную. */
function pendingRun() {
  let resolve!: (result: RunResult) => void;
  vi.mocked(api.run).mockReturnValue(new Promise<RunResult>((r) => (resolve = r)));
  return resolve;
}

beforeEach(() => {
  vi.mocked(api.run).mockReset();
  useStore.setState({ project: emptyProject(), dirty: false, running: false, selectedNodeId: null, banner: null });
});

describe('запуск и смена проекта', () => {
  it('без смены проекта результат записывается в запущенный проект', async () => {
    const resolve = pendingRun();
    const code = useStore.getState().project.code;
    const running = useStore.getState().run();
    expect(useStore.getState().running).toBe(true);
    resolve(fakeRun(code));
    await running;
    const s = useStore.getState();
    expect(s.project.run?.stdout).toBe('out\n');
    expect(s.dirty).toBe(true);
    expect(s.running).toBe(false);
  });

  it('результат запуска A не попадает в проект B, открытый во время выполнения', async () => {
    const other = normalizeProject({ id: 'proj-b', name: 'B', code: 'b = 2\n' });
    vi.mocked(api.loadProject).mockResolvedValue(other);
    const resolve = pendingRun();

    const running = useStore.getState().run();
    await useStore.getState().openProject('proj-b'); // меню остаётся доступным во время запуска
    expect(useStore.getState().project.id).toBe('proj-b');
    resolve(fakeRun('a = 1\n'));
    await running;

    const s = useStore.getState();
    expect(s.project.id).toBe('proj-b');
    expect(s.project.run).toBeNull();
    expect(s.dirty).toBe(false); // B не помечен изменённым, Ctrl+S не запишет чужой результат
    expect(s.running).toBe(false);
  });

  it('новый файл, открытый во время запуска, тоже не получает чужой результат', async () => {
    const resolve = pendingRun();
    const running = useStore.getState().run();
    useStore.getState().newProject();
    const freshId = useStore.getState().project.id;
    resolve(fakeRun('x'));
    await running;
    const s = useStore.getState();
    expect(s.project.id).toBe(freshId);
    expect(s.project.run).toBeNull();
    expect(s.running).toBe(false);
  });

  it('повторное открытие того же проекта (тот же id) тоже отбрасывает результат', async () => {
    const same = normalizeProject({ id: 'proj-same', name: 'S', code: 's = 1\n' });
    vi.mocked(api.loadProject).mockResolvedValue(same);
    await useStore.getState().openProject('proj-same');
    const resolve = pendingRun();
    const running = useStore.getState().run();
    await useStore.getState().openProject('proj-same');
    resolve(fakeRun('s = 1\n'));
    await running;
    expect(useStore.getState().project.run).toBeNull();
    expect(useStore.getState().dirty).toBe(false);
  });
});

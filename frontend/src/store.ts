import { create } from 'zustand';
import { api } from './api';
import { downloadText, emptyProject, isStale, normalizeProject, safeFileName } from './projectFile';
import { readStorage, writeStorage } from './storage';
import type { Project, ProjectSummary } from './types';

export type Theme = 'auto' | 'light' | 'dark';

interface Banner {
  kind: 'info' | 'error';
  text: string;
}

interface State {
  project: Project;
  dirty: boolean;
  /** результат показан из сохранённого файла и в этой сессии не запускался */
  fromSaved: boolean;
  running: boolean;
  selectedNodeId: string | null;
  consoleOpen: boolean;
  /** запрос показать строку в редакторе (tick нужен, чтобы повторный клик по той же строке срабатывал) */
  reveal: { line: number; tick: number } | null;
  theme: Theme;
  timeoutSec: number;
  banner: Banner | null;
  projects: ProjectSummary[];
  examples: { id: string; name: string }[];

  init: () => Promise<void>;
  setBanner: (banner: Banner | null) => void;
  setTheme: (theme: Theme) => void;
  setTimeoutSec: (value: number) => void;
  setConsoleOpen: (open: boolean) => void;
  selectNode: (id: string | null) => void;
  revealLine: (line: number) => void;

  setName: (name: string) => void;
  setCode: (code: string) => void;

  run: () => Promise<void>;
  stop: () => Promise<void>;

  newProject: () => void;
  save: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  openProject: (id: string) => Promise<void>;
  openExample: (id: string) => Promise<void>;
  importJson: (text: string) => Promise<void>;
  exportJson: () => void;
  exportPython: () => Promise<void>;
  exportMarkdown: () => Promise<void>;
}

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

export const useStore = create<State>((set, get) => {
  // Растёт при каждой смене проекта: результат запуска, начатого в прежнем проекте, не должен попасть в новый
  // (сравнение по project.id не годится — тот же проект можно открыть заново).
  let generation = 0;

  const adopt = (project: Project, dirty: boolean, fromSaved: boolean) => {
    generation += 1;
    set({
      project, dirty, fromSaved, selectedNodeId: null, banner: null,
      consoleOpen: project.run?.error != null,
    });
    writeStorage('lastProjectId', project.id);
  };

  const guard = (action: () => Promise<void>) =>
    action().catch((error) => set({ banner: { kind: 'error', text: messageOf(error) } }));

  return {
    project: emptyProject(),
    dirty: false,
    fromSaved: false,
    running: false,
    selectedNodeId: null,
    consoleOpen: false,
    reveal: null,
    theme: (readStorage('theme') as Theme) || 'auto',
    timeoutSec: Number(readStorage('timeoutSec')) || 30,
    banner: null,
    projects: [],
    examples: [],

    init: () =>
      guard(async () => {
        const [examples, projects] = await Promise.all([api.listExamples(), api.listProjects()]);
        set({ examples, projects });
        const lastId = readStorage('lastProjectId');
        if (lastId && projects.some((p) => p.id === lastId)) {
          adopt(normalizeProject(await api.loadProject(lastId)), false, true);
        } else {
          adopt(normalizeProject(await api.loadExample('mask-selection')), true, false);
        }
      }),

    setBanner: (banner) => set({ banner }),
    setTheme: (theme) => {
      writeStorage('theme', theme);
      set({ theme });
    },
    setTimeoutSec: (value) => {
      const timeoutSec = Math.min(300, Math.max(1, Math.round(value) || 30));
      writeStorage('timeoutSec', String(timeoutSec));
      set({ timeoutSec });
    },
    setConsoleOpen: (consoleOpen) => set({ consoleOpen }),
    selectNode: (selectedNodeId) => set({ selectedNodeId }),
    revealLine: (line) => set((s) => ({ reveal: { line, tick: (s.reveal?.tick ?? 0) + 1 } })),

    setName: (name) => set((s) => ({ project: { ...s.project, name }, dirty: true })),
    setCode: (code) => set((s) => (s.project.code === code ? s : { project: { ...s.project, code }, dirty: true })),

    run: async () => {
      if (get().running) return;
      const { project, timeoutSec } = get();
      const startedIn = generation;
      set({ running: true, banner: null, selectedNodeId: null });
      try {
        const result = await api.run({ code: project.code, timeoutSec });
        if (generation !== startedIn) return; // проект сменили, пока шёл запуск — результат отбрасываем
        set((s) => ({
          project: { ...s.project, run: result },
          dirty: true,
          fromSaved: false,
          consoleOpen: result.error ? true : s.consoleOpen,
        }));
      } catch (error) {
        set({ banner: { kind: 'error', text: messageOf(error) } });
      } finally {
        set({ running: false });
      }
    },

    stop: () => guard(async () => void (await api.stop())),

    newProject: () => adopt(emptyProject(), true, false),

    save: () =>
      guard(async () => {
        const saved = await api.saveProject(get().project);
        set((s) => ({
          project: { ...s.project, createdAt: saved.createdAt, updatedAt: saved.updatedAt },
          dirty: false,
          banner: { kind: 'info', text: `Сохранено: ${saved.name}` },
        }));
        writeStorage('lastProjectId', saved.id);
        await get().refreshProjects();
      }),

    refreshProjects: () => guard(async () => set({ projects: await api.listProjects() })),

    openProject: (id) =>
      guard(async () => {
        const project = normalizeProject(await api.loadProject(id));
        adopt(project, project.migratedFrom != null, true);
        if (project.migratedFrom != null) {
          set({ banner: { kind: 'info', text: 'Проект со старыми ячейками открыт как один файл. Оригинал сохранён; запустите код, чтобы построить схему.' } });
        }
      }),

    openExample: (id) =>
      guard(async () => adopt(normalizeProject(await api.loadExample(id)), true, false)),

    importJson: (text) =>
      guard(async () => {
        let raw: unknown;
        try {
          raw = JSON.parse(text);
        } catch {
          throw new Error('Файл не является корректным JSON.');
        }
        const project = normalizeProject(await api.importProject(raw));
        adopt(project, true, true);
        set({ banner: { kind: 'info', text: 'Проект импортирован как новый. Чтобы записать его в папку приложения, выберите «Сохранить».' } });
      }),

    exportJson: () => {
      const { project } = get();
      downloadText(safeFileName(project.name, 'json'), JSON.stringify(project, null, 2), 'application/json');
    },

    exportPython: () =>
      guard(async () => {
        const { project } = get();
        downloadText(safeFileName(project.name, 'py'), await api.exportPython(project), 'text/x-python');
      }),

    exportMarkdown: () =>
      guard(async () => {
        const { project } = get();
        downloadText(safeFileName(project.name, 'md'), await api.exportMarkdown(project), 'text/markdown');
      }),
  };
});

export const useStale = () => useStore((s) => isStale(s.project));

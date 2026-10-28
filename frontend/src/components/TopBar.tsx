import { useRef } from 'react';
import { useStore, type Theme } from '../store';
import { Menu, type MenuEntry } from './Menu';

const THEMES: [Theme, string][] = [['auto', 'Как в системе'], ['light', 'Светлая'], ['dark', 'Тёмная']];

export function TopBar() {
  const name = useStore((s) => s.project.name);
  const dirty = useStore((s) => s.dirty);
  const running = useStore((s) => s.running);
  const projects = useStore((s) => s.projects);
  const examples = useStore((s) => s.examples);
  const theme = useStore((s) => s.theme);
  const timeoutSec = useStore((s) => s.timeoutSec);
  const currentId = useStore((s) => s.project.id);
  const s = useStore.getState();
  const fileInput = useRef<HTMLInputElement>(null);

  const entries: MenuEntry[] = [
    { label: 'Новый файл', onClick: () => s.newProject() },
    { label: 'Сохранить', note: 'Ctrl+S', onClick: () => void s.save() },
    { kind: 'separator' },
    { kind: 'heading', label: 'Открыть' },
    ...(projects.length === 0 ? [{ kind: 'heading', label: 'сохранённых проектов пока нет' } as MenuEntry] : []),
    ...projects.map((p): MenuEntry => ({
      label: p.name,
      checked: p.id === currentId,
      note: p.updatedAt ? new Date(p.updatedAt).toLocaleDateString('ru-RU') : '',
      onClick: () => void s.openProject(p.id),
    })),
    { label: 'Импортировать из файла…', onClick: () => fileInput.current?.click() },
    { kind: 'separator' },
    { kind: 'heading', label: 'Примеры' },
    ...examples.map((e): MenuEntry => ({ label: e.name, onClick: () => void s.openExample(e.id) })),
    { kind: 'separator' },
    { kind: 'heading', label: 'Экспорт' },
    { label: 'Проект (.json)', onClick: () => s.exportJson() },
    { label: 'Код (.py)', onClick: () => void s.exportPython() },
    { label: 'Отчёт (.md)', onClick: () => void s.exportMarkdown() },
    { kind: 'separator' },
    { kind: 'heading', label: 'Тема' },
    ...THEMES.map(([value, label]): MenuEntry => ({ label, checked: theme === value, onClick: () => s.setTheme(value) })),
    { kind: 'separator' },
    { kind: 'heading', label: 'Настройки' },
    {
      kind: 'custom',
      node: (
        <label className="setting">
          Лимит времени, с
          <input
            type="number" min={1} max={300} value={timeoutSec}
            onChange={(e) => s.setTimeoutSec(Number(e.target.value))}
            aria-label="Лимит времени выполнения, секунд"
          />
        </label>
      ),
    },
  ];

  return (
    <header className="topbar">
      <input
        className="title"
        value={name}
        onChange={(e) => s.setName(e.target.value)}
        aria-label="Название проекта"
        spellCheck={false}
      />
      {dirty && <span className="dirty" title="Есть несохранённые изменения" aria-label="Есть несохранённые изменения" />}
      <span className="grow" />
      <button
        className={`run-btn${running ? ' stop' : ''}`}
        onClick={() => void (running ? s.stop() : s.run())}
        title={running ? 'Остановить программу' : 'Запустить (Ctrl+Enter)'}
      >
        {running ? '■ Остановить' : '▶ Запустить'}
      </button>
      <Menu label="⋯" ariaLabel="Меню" entries={entries} onOpen={() => void s.refreshProjects()} />
      <input
        ref={fileInput}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (file) await s.importJson(await file.text());
          if (fileInput.current) fileInput.current.value = '';
        }}
      />
    </header>
  );
}

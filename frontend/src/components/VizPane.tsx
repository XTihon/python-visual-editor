import { useState } from 'react';
import { isStale } from '../projectFile';
import { useStore } from '../store';
import { GraphView } from './GraphView';

export function VizPane() {
  const run = useStore((s) => s.project.run);
  const stale = useStore((s) => isStale(s.project));
  const fromSaved = useStore((s) => s.fromSaved);
  const [expanded, setExpanded] = useState(false);

  const notes = run?.graph.notes ?? [];
  const dropped = run?.graph.dropped ?? 0;
  const footer: string[] = [];
  if (run?.partial && run.notice) footer.push(run.notice);
  if (dropped > 0) footer.push(`Схема усечена: не показано значений — ${dropped}.`);
  if (fromSaved && run) footer.push(`Сохранённый результат · ${new Date(run.startedAt).toLocaleString('ru-RU')}`);

  return (
    <div className="viz">
      {stale && (
        <div className="strip" role="status">
          Схема устарела: код изменён после запуска. Запустите снова (Ctrl+Enter).
        </div>
      )}
      <div className="viz-main"><GraphView /></div>
      {(footer.length > 0 || notes.length > 0) && (
        <div className="viz-foot">
          {footer.map((t) => <span key={t}>{t}</span>)}
          {notes.length > 0 && (
            <button className="note-toggle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
              Ограничения анализа: {notes.length} {expanded ? '▾' : '▸'}
            </button>
          )}
          {expanded && <ul className="notes">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        </div>
      )}
    </div>
  );
}

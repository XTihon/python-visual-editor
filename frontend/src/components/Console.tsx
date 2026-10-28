import { useRef } from 'react';
import { isStale } from '../projectFile';
import { useStore } from '../store';

const CLOSED_HEIGHT = 30;

export function Console({ height, onHeight }: { height: number; onHeight: (h: number) => void }) {
  const open = useStore((s) => s.consoleOpen);
  const setOpen = useStore((s) => s.setConsoleOpen);
  const run = useStore((s) => s.project.run);
  const stale = useStore((s) => isStale(s.project));
  const running = useStore((s) => s.running);
  const revealLine = useStore((s) => s.revealLine);
  const drag = useRef<{ y: number; h: number } | null>(null);

  const error = run?.error ?? null;
  const outLines = run?.stdout ? run.stdout.split('\n').filter(Boolean).length : 0;
  const summary = running
    ? 'выполняется…'
    : error
      ? `ошибка${error.line ? `, строка ${error.line}` : ''}`
      : run
        ? outLines ? `вывод: ${outLines} ${outLines === 1 ? 'строка' : 'строк'}` : 'вывода нет'
        : '';

  return (
    <div className="console" style={{ height: open ? height : CLOSED_HEIGHT }}>
      {open && (
        <div
          className="console-grip"
          role="separator"
          aria-orientation="horizontal"
          onPointerDown={(e) => {
            drag.current = { y: e.clientY, h: height };
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => drag.current && onHeight(Math.max(80, Math.min(600, drag.current.h + drag.current.y - e.clientY)))}
          onPointerUp={() => (drag.current = null)}
        />
      )}
      <button className="console-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="chev">{open ? '▾' : '▸'}</span>
        <span>Консоль</span>
        <span className={`console-summary${error ? ' error' : ''}`}>{summary}</span>
        {stale && run && <span className="console-summary">· результат устарел</span>}
      </button>
      {open && (
        <div className="console-body">
          {!run && <div className="muted">Здесь появятся вывод print() и сообщения об ошибках.</div>}
          {error && (
            <div role="alert" className="console-error">
              <button className="error-line" onClick={() => error.line && revealLine(error.line)} disabled={!error.line}>
                {error.line ? `Строка ${error.line}` : 'Ошибка'} — {error.kind === 'exception' || error.kind === 'syntax' ? `${error.type}: ${error.message}` : error.message}
              </button>
              {(error.kind === 'exception' || error.kind === 'syntax') && <pre>{error.text}</pre>}
            </div>
          )}
          {run?.stdout && <pre className="console-out">{run.stdout}</pre>}
          {run?.stderr && <pre className="console-out stderr">{run.stderr}</pre>}
          {run?.outputTruncated && <div className="muted">Вывод слишком большой и обрезан по лимиту.</div>}
          {run && !error && !run.stdout && !run.stderr && <div className="muted">Программа ничего не вывела.</div>}
        </div>
      )}
    </div>
  );
}

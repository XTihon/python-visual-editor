import { useEffect, useRef, useState } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import { isStale } from '../projectFile';
import { useStore } from '../store';

type CodeEditorInstance = Parameters<OnMount>[0];
type Monaco = Parameters<OnMount>[1];

export function useMonacoTheme(): 'vs' | 'vs-dark' {
  const theme = useStore((s) => s.theme);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches);
  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  return theme === 'dark' || (theme === 'auto' && systemDark) ? 'vs-dark' : 'vs';
}

export function CodeEditor() {
  const code = useStore((s) => s.project.code);
  const run = useStore((s) => s.project.run);
  const stale = useStore((s) => isStale(s.project));
  const selectedNodeId = useStore((s) => s.selectedNodeId);
  const reveal = useStore((s) => s.reveal);
  const theme = useMonacoTheme();

  const editorRef = useRef<CodeEditorInstance | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const [ready, setReady] = useState(false);
  const nodeDeco = useRef<ReturnType<CodeEditorInstance['createDecorationsCollection']> | null>(null);
  const errorDeco = useRef<ReturnType<CodeEditorInstance['createDecorationsCollection']> | null>(null);

  const error = !stale ? run?.error ?? null : null;
  const selectedNode = !stale && selectedNodeId ? run?.graph.nodes.find((n) => n.id === selectedNodeId) : undefined;

  // Строка с ошибкой: красная подсветка, значок в поле и подчёркивание.
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel();
    if (!ready || !editor || !monaco || !model) return;
    const line = error?.line && error.line <= model.getLineCount() ? error.line : null;
    monaco.editor.setModelMarkers(model, 'vr-run', line && error
      ? [{
          severity: monaco.MarkerSeverity.Error,
          message: `${error.type}: ${error.message}`,
          startLineNumber: line, endLineNumber: line, startColumn: 1, endColumn: model.getLineMaxColumn(line),
        }]
      : []);
    errorDeco.current?.clear();
    errorDeco.current = editor.createDecorationsCollection(line
      ? [{ range: new monaco.Range(line, 1, line, 1), options: { isWholeLine: true, className: 'line-error', glyphMarginClassName: 'glyph-error' } }]
      : []);
  }, [ready, error, code]);

  // Выбранный блок схемы → его строки подсвечены в коде.
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel();
    if (!ready || !editor || !monaco || !model) return;
    const total = model.getLineCount();
    const ranges = (selectedNode?.lines ?? []).filter(([a]) => a <= total);
    nodeDeco.current?.clear();
    nodeDeco.current = editor.createDecorationsCollection(ranges.map(([a, b]) => ({
      range: new monaco.Range(a, 1, Math.min(b, total), 1),
      options: { isWholeLine: true, className: 'line-selected', linesDecorationsClassName: 'gutter-selected' },
    })));
    if (ranges.length) editor.revealLineInCenterIfOutsideViewport(ranges[0][0]);
  }, [ready, selectedNode]);

  // Клик по сообщению об ошибке в консоли → перейти к строке.
  useEffect(() => {
    const editor = editorRef.current;
    if (!ready || !editor || !reveal) return;
    editor.revealLineInCenterIfOutsideViewport(reveal.line);
    editor.setPosition({ lineNumber: reveal.line, column: 1 });
    editor.focus();
  }, [ready, reveal]);

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => void useStore.getState().run());
    editor.addCommand(monaco.KeyCode.F5, () => void useStore.getState().run());
    setReady(true);
  };

  return (
    <div className="code-editor">
      <Editor
        language="python"
        theme={theme}
        value={code}
        onChange={(value) => useStore.getState().setCode(value ?? '')}
        onMount={onMount}
        loading={<div className="empty">Загрузка редактора…</div>}
        options={{
          minimap: { enabled: false },
          lineNumbers: 'on',
          glyphMargin: true,
          folding: true,
          scrollBeyondLastLine: false,
          tabSize: 4,
          insertSpaces: true,
          detectIndentation: false,
          fontSize: 14,
          fontFamily: "'Cascadia Mono', 'Cascadia Code', Consolas, monospace",
          automaticLayout: true,
          renderLineHighlight: 'line',
          padding: { top: 10, bottom: 10 },
          overviewRulerLanes: 0,
          renderWhitespace: 'none',
          guides: { indentation: true },
          accessibilitySupport: 'off',
        }}
      />
    </div>
  );
}

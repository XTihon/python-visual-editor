import { useEffect, useState } from 'react';
import { Group, Panel, Separator, useDefaultLayout, type LayoutStorage } from 'react-resizable-panels';
import { CodeEditor } from './components/CodeEditor';
import { Console } from './components/Console';
import { TopBar } from './components/TopBar';
import { VizPane } from './components/VizPane';
import { readStorage, writeStorage } from './storage';
import { useStore } from './store';

// Раскладку панелей запоминаем в localStorage, но без падений, если он недоступен.
const layoutStorage: LayoutStorage = {
  getItem: (key) => readStorage(key),
  setItem: (key, value) => writeStorage(key, value),
};

function Banner() {
  const banner = useStore((s) => s.banner);
  const setBanner = useStore((s) => s.setBanner);
  useEffect(() => {
    if (banner?.kind !== 'info') return;
    const timer = setTimeout(() => setBanner(null), 4000);
    return () => clearTimeout(timer);
  }, [banner, setBanner]);
  if (!banner) return null;
  return (
    <div className={`banner ${banner.kind}`} role={banner.kind === 'error' ? 'alert' : 'status'}>
      <span>{banner.text}</span>
      <button onClick={() => setBanner(null)} aria-label="Закрыть сообщение">×</button>
    </div>
  );
}

export default function App() {
  const theme = useStore((s) => s.theme);
  const dirty = useStore((s) => s.dirty);
  const [consoleHeight, setConsoleHeight] = useState(Number(readStorage('consoleHeight')) || 220);
  const layout = useDefaultLayout({ id: 'layout-main', storage: layoutStorage });

  useEffect(() => {
    void useStore.getState().init();
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'auto') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        void useStore.getState().save();
      }
    };
    const onUnload = (event: BeforeUnloadEvent) => {
      if (useStore.getState().dirty) event.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('beforeunload', onUnload);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('beforeunload', onUnload);
    };
  }, [dirty]);

  return (
    <div className="app">
      <TopBar />
      <Banner />
      <Group className="main" orientation="horizontal" defaultLayout={layout.defaultLayout} onLayoutChanged={layout.onLayoutChanged}>
        <Panel id="editor" defaultSize="42%" minSize="25%">
          <div className="left">
            <CodeEditor />
            <Console
              height={consoleHeight}
              onHeight={(h) => {
                setConsoleHeight(h);
                writeStorage('consoleHeight', String(h));
              }}
            />
          </div>
        </Panel>
        <Separator className="sep" />
        <Panel id="viz" minSize="30%">
          <VizPane />
        </Panel>
      </Group>
    </div>
  );
}

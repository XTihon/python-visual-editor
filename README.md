# Python Visual Editor

A local web app for Windows: you write a **plain Python file**, run it with real CPython, and the right-hand panel shows which values appeared and how the data is connected: NumPy arrays with indices, matrices, boolean masks, `print()` output and dependency arrows. The interface is in Russian and works offline.

It is built for learning Python, NumPy and simple neural networks: it ties each line of code to the actual result it computed.

## Quick start (Windows, PowerShell)

Requires **Python 3.11+** and **Node.js 20+** (tested on Python 3.14 and Node 24).

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1   # once: environment, dependencies, build (needs internet)
.\start.ps1                                            # every time: start and open the browser
```

Default address: <http://127.0.0.1:8742>. Stop with `Ctrl+C` in the PowerShell window.
`start.ps1` options: `-Port 8800`, `-NoBrowser`, `-Dev` (Vite on port 5173).
After `setup.ps1` no internet is needed: the Monaco editor and fonts (system) ship with the app.

## How it works

On the left is the editor (line numbers, Python highlighting, indentation) and a collapsible console. On the right is the graph. On screen: the project name, the **▶ Run** button (**■ Stop** while running) and the **⋯** menu. Save, open, import, export, examples, theme and time limit are in the **⋯** menu. Shortcuts: `Ctrl+Enter` or `F5` to run, `Ctrl+S` to save.

```python
import numpy as np

a = np.array([2, 7, 4, 9])
mask = a > 5
result = a[mask]
print(result)
```

After running, you get the blocks `a`, `mask`, `result`, `output` and the arrows `a → mask`, `a → result`, `mask → result`, `result → output`. The elements of `a` selected by the mask (`7` and `9`) are highlighted automatically.

**Working with the graph.** Clicking a block highlights its line in the code, the block itself and the blocks and arrows **directly connected** to it (everything else is dimmed); click again or click the background to clear. The graph can be panned, zoomed with the wheel, and blocks can be dragged; the "frame" button at the bottom right resets the view. Mouse and keys in the graph do not affect typing in the editor.

**Layout.** The graph runs left to right by default (like n8n). If that makes cards smaller than the readability threshold (text < ≈11 px) while top to bottom would make them noticeably larger, top to bottom is used instead, which matches the reading order of the code. The direction is chosen once per run from the panel size and does not change when the panel is resized. Blocks on each level are centered on a shared axis, long unconnected rows wrap, and arrows that skip a level route around blocks. While the graph structure stays the same, re-running keeps your zoom, pan and dragged blocks; a new structure re-fits the view.

### Where values and links come from

The program runs **once**, as normal Python, **statement by statement** at the top level. After each statement the app compares the variables before and after:

- an assigned variable gets a new version (`a v1`, `a v2`…), an independent copy of the value at that moment;
- a variable changed **in place** (`a[0] = 99`, `lst.append(3)`, a change through an alias `b = a; b[0] = 1`) also gets a new version marked "changed in place"; earlier snapshots stay unchanged;
- an arrow `x → y` is drawn only if the statement that created `y` **literally reads** the name `x` (AST analysis). Expressions are not re-evaluated: intermediate values like `a > 5` inside `a[a > 5]` do not appear in the graph, only what the program stored in variables;
- imported modules, functions and classes are not shown as blocks.

### What is not analyzed

For **loops, `if`, `with`, `try`, `match`, `exec`/`eval`/`globals()`** the program runs normally and values are shown, but **links are not drawn**: the block gets a note "for loop: links not determined", and an "Analysis limits" counter appears at the bottom of the graph. Calling **your own function** draws arrows from its arguments, but the block is marked "links incomplete" (what the function reads inside is not tracked). Nested changes (`d['k'].append(1)`) do not create a separate version unless the top-level object changes.

After the code is edited, the graph stays on screen but is marked **stale** (dimmed, with a bar on top) until the next run. Code is not executed while typing.

Display limits: array preview is 100 elements (1D) or 16×16 (2D); a card shows the first 12 elements or 8×8; arrays with 3+ dimensions show only shape and dtype; the graph shows at most 80 values (the rest as "Graph truncated: N not shown").

## Projects and old files

A project is one Python file (`code`) plus the result of the last run, stored in `data\projects\*.json`. Projects in the old format (with cells) **open as continuous code in the original order** (the cell title becomes a `# Title` comment). The original is kept twice: a file copy in `data\projects\_originals\<id>.v1.json` and the full source inside the new project (the `original` field); learning notes from cells go into the "Original cells" section of the Markdown report. Old snapshots are not converted to the graph; the code needs to be run again.

Export: **.json** (project), **.py** (plain code file), **.md** (report: code, values, links, output, errors; handy to give to Claude Code or Codex).

## Note: the space key in the editor after a run

Previously, after the first run (when the graph appeared), spaces stopped working in the editor. The cause: by default React Flow catches the Space key at the window level as "enable hand mode" and cancels its default action, and it does not treat Monaco's input element (`div.native-edit-context` without `contenteditable`) as an input field. The unused global graph keys (`panActivationKeyCode`, `selectionKeyCode`, `multiSelectionKeyCode`, `zoomActivationKeyCode`) are now disabled in `GraphView.tsx`. If graph shortcuts are ever needed, enable them with the editor in mind (for example, the `nokey` class on the editor container).

## Limits and security

- **The worker process is not a sandbox.** Code runs in a separate Python process, but with your Windows user's rights: it can read and delete your files, access the network and start programs. Run only your own code. There is no memory limit.
- Each run is a new process with clean memory (like running a file); the next process is prepared in advance.
- The server listens only on `127.0.0.1`; `Host` and `Origin` are checked: other web pages (including DNS rebinding) get 403, and so do state-changing requests without an allowed `Origin`.
- Limits: run time 30 s by default (⋯ menu, maximum 300 s), output 100,000 characters, project name only `[A-Za-z0-9_-]`, project files cannot leave `data\projects`.
- On stop or timeout the whole process is terminated; values that appeared before that stay on the graph, and the error points to the line where execution stopped. Buffered `print()` output inside an unfinished statement is lost.
- Not supported: `input()` (raises `EOFError`), matplotlib plots, step-by-step debugging.

## Structure

```
backend/            FastAPI + Uvicorn (127.0.0.1), Python worker process
  app/analysis.py     statement analysis: what it reads and writes (source of links)
  app/tracer.py       statement-by-statement execution, value versions, edges, masks
  app/worker.py       worker process (protocol, output capture, errors with line numbers)
  app/sessions.py     start/stop, timeout, one run at a time, pre-warmed process
  app/snapshot.py     safe value description (truncation, independent copies)
  app/migration.py    cells → single file, keeping the original
  app/projects.py, exports.py, security.py, main.py
  app/examples/       three examples
  tests/              pytest (real Python, no mocks)
frontend/           React + TypeScript + Vite
  src/graph.ts        graph layout, mask highlighting, connected nodes (with tests)
  src/store.ts        state: run, stop, projects
  src/components/     CodeEditor (Monaco), GraphView (React Flow), Console, TopBar, Menu, VizPane
data/               projects and working folder (created automatically)
setup.ps1, start.ps1
```

## Stack and versions

Python: FastAPI 0.142.2, Uvicorn 0.54.0, Pydantic 2.13.5, NumPy 2.5.3.
UI: React 19.3.0, TypeScript 7.0.2, Vite 8.3.2, Monaco Editor 0.57.0, @xyflow/react (React Flow) 12.12.0, Zustand 5.0.15, react-resizable-panels 4.14.2.
Exact versions are pinned in `backend/requirements*.txt` and `frontend/package-lock.json`; `dompurify` (a Monaco dependency) is pinned to 3.4.16 via `overrides` (fix for an `npm audit` vulnerability).

## Tests

```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest      # analysis, value/link graph, run/stop, projects, migration, Origin
cd ..\frontend; npm test                                # layout, mask highlighting, staleness, project
cd ..\frontend; npm run build                           # type check and build
```

## API (reference)

`GET /api/status`, `POST /api/run`, `POST /api/stop`, `GET /api/projects`, `GET|PUT /api/projects/{id}`, `POST /api/projects/import` (any format → current), `POST /api/export/py|md`, `GET /api/examples[/{id}]`.

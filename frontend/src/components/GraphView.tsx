import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  Background, Controls, Handle, MarkerType, Position, ReactFlow, useNodesState,
  type Edge, type Node, type NodeProps, type Viewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  INLINE_ROWS, inlineCols, inlineCount1D, maskHighlight, pickLayout, relatedIds, shapeText, versionCounts,
  type Direction, type MaskHighlight,
} from '../graph';
import { isStale } from '../projectFile';
import { useStore } from '../store';
import type { DtypeKind, Graph, GraphNode, OutputNode, ValueInfo, ValueNode } from '../types';

const SPECIAL = /^-?(nan|inf)$/i;

function elClass(text: string, kind: DtypeKind, picked: boolean): string {
  const c = ['el'];
  if (kind === 'bool') c.push(text === 'True' ? 'is-true' : 'is-false');
  else if ((kind === 'float' || kind === 'complex') && SPECIAL.test(text)) c.push('is-special');
  if (kind === 'str' || kind === 'other') c.push('is-text');
  if (picked) c.push('picked');
  return c.join(' ');
}

function Array1D({ v, highlight }: { v: ValueInfo; highlight: MaskHighlight | null }) {
  const data = v.preview!.data as string[];
  const shown = data.slice(0, inlineCount1D(data));
  const total = v.shape?.[0] ?? data.length;
  const more = total - shown.length;
  return (
    <div className="arr" role="img" aria-label={`Массив: ${shown.join(', ')}${more > 0 ? ` и ещё ${more}` : ''}`}>
      <span className="br">[</span>
      {shown.map((text, i) => (
        <span key={i} className="cellwrap">
          <span className={elClass(text, v.dtypeKind ?? 'other', !!highlight?.picked(i))}>{text}</span>
          <span className="idx">{i}</span>
        </span>
      ))}
      {more > 0 && <span className="more">… ещё {more}</span>}
      <span className="br">]</span>
    </div>
  );
}

function Matrix({ v, highlight }: { v: ValueInfo; highlight: MaskHighlight | null }) {
  const data = v.preview!.data as string[][];
  const rows = data.slice(0, INLINE_ROWS);
  const cols = inlineCols(data);
  const [totalRows, totalCols] = v.shape ?? [rows.length, cols];
  return (
    <div className="matrix-wrap" role="img" aria-label={`Матрица ${shapeText(v.shape)}`}>
      <table className="matrix">
        <thead>
          <tr>
            <th />
            {Array.from({ length: cols }, (_, j) => <th key={j} className="idx">{j}</th>)}
            {totalCols > cols && <th className="idx">…</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <th className="idx">{i}</th>
              {row.slice(0, cols).map((text, j) => {
                const edge = `${j === 0 ? ' br-l' : ''}${j === cols - 1 && totalCols <= cols ? ' br-r' : ''}${i === 0 ? ' br-t' : ''}${i === rows.length - 1 && totalRows <= rows.length ? ' br-b' : ''}`;
                return <td key={j} className={elClass(text, v.dtypeKind ?? 'other', !!highlight?.picked(i, j)) + edge}>{text}</td>;
              })}
              {totalCols > cols && <td className="more">…</td>}
            </tr>
          ))}
          {totalRows > rows.length && (
            <tr><th className="idx">…</th><td className="more" colSpan={cols + 1}>ещё строк: {totalRows - rows.length}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ValueBody({ v, highlight }: { v: ValueInfo; highlight: MaskHighlight | null }) {
  if (v.preview && v.shape?.length === 1) return <Array1D v={v} highlight={highlight} />;
  if (v.preview && v.shape?.length === 2) return <Matrix v={v} highlight={highlight} />;
  if (v.note) return <div className="muted small">{v.note}</div>;
  return <div className="plain">{v.kind === 'str' ? JSON.stringify(v.repr) : v.repr}</div>;
}

interface ValueData extends Record<string, unknown> {
  node: ValueNode;
  versions: number;
  selected: boolean;
  related: boolean;
  dim: boolean;
  direction: Direction;
  highlight: MaskHighlight | null;
}
interface OutputData extends Record<string, unknown> {
  node: OutputNode;
  selected: boolean;
  related: boolean;
  dim: boolean;
  direction: Direction;
}
type ValueFlowNode = Node<ValueData, 'value'>;
type OutputFlowNode = Node<OutputData, 'outputBlock'>;

function ValueCard({ data }: NodeProps<ValueFlowNode>) {
  const { node, versions, selected, related, dim, highlight, direction } = data;
  const v = node.value;
  const isArray = !!v.preview || v.kind === 'ndarray' || v.kind === 'list';
  const compact = !isArray && v.repr.length <= 40 && v.kind !== 'str' && v.kind !== 'dict';
  const meta = [shapeText(v.shape), v.dtype ?? (v.kind === 'list' ? 'list' : '')].filter(Boolean).join(' · ');
  // выражение показываем, только если оно что-то добавляет к значению (не повторяет литерал вроде "тест")
  const repeatsValue = node.expr === v.repr || (v.kind === 'str' && (node.expr === JSON.stringify(v.repr) || node.expr === `'${v.repr}'`));
  const showExpr = !!node.expr && !repeatsValue;
  return (
    <div className={`card${selected ? ' selected' : ''}${related ? ' related' : ''}${dim ? ' dim' : ''}`}>
      <Handle type="target" position={direction === 'LR' ? Position.Left : Position.Top} isConnectable={false} />
      <div className="card-head">
        <span className="name">{node.name}</span>
        {versions > 1 && <span className="ver" title="Это значение переменной после строки кода, указанной ниже">v{node.version}</span>}
        {compact && <><span className="eq">=</span><span className="val">{v.repr}</span></>}
        {isArray && meta && <span className="meta">{meta}</span>}
        {selected && !isArray && <span className="meta">{v.type}</span>}
        <span className="line-tag" title="Строка кода">стр. {node.lines[0][0]}</span>
      </div>
      {showExpr && <div className="expr" title={node.expr ?? ''}>{node.expr}</div>}
      {!compact && <ValueBody v={v} highlight={highlight} />}
      {highlight && (
        <div className="foot picked-note">выделено маской {highlight.maskName}: {highlight.count}</div>
      )}
      {node.mutated && <div className="foot">изменён на месте</div>}
      {node.partial && <div className="foot" title="Значения внутри функции не отслеживаются">вызов функции {node.partial}: связи неполные</div>}
      {node.unsupported && <div className="foot" title="Значение получено обычным выполнением">{node.unsupported}: связи не определяются</div>}
      <Handle type="source" position={direction === 'LR' ? Position.Right : Position.Bottom} isConnectable={false} />
    </div>
  );
}

function OutputCard({ data }: NodeProps<OutputFlowNode>) {
  const { node, selected, related, dim, direction } = data;
  const lines = node.text.replace(/\n$/, '').split('\n');
  const shown = lines.slice(0, 10);
  return (
    <div className={`card output${selected ? ' selected' : ''}${related ? ' related' : ''}${dim ? ' dim' : ''}`}>
      <Handle type="target" position={direction === 'LR' ? Position.Left : Position.Top} isConnectable={false} />
      <div className="card-head">
        <span className="name">output</span>
        <span className="line-tag">стр. {node.lines.map(([a]) => a).join(', ')}</span>
      </div>
      <pre className="out-text">{shown.join('\n')}</pre>
      {lines.length > shown.length && <div className="foot">ещё строк: {lines.length - shown.length} (полный вывод — в консоли)</div>}
      {node.truncated && <div className="foot">вывод обрезан по лимиту</div>}
      {node.unsupported && <div className="foot">{node.unsupported}: связи не определяются</div>}
      <Handle type="source" position={direction === 'LR' ? Position.Right : Position.Bottom} isConnectable={false} />
    </div>
  );
}

// Имя «output» занято встроенным типом узла React Flow со своим стилем — поэтому outputBlock.
const nodeTypes = { value: ValueCard, outputBlock: OutputCard };

// Один набор параметров для первой подгонки и для кнопки «вписать»: вид совпадает.
const FIT_VIEW = { padding: 0.12, maxZoom: 1.3 };

/** Что сохраняется между запусками, пока структура схемы не изменилась: вид и перетащенные блоки. */
interface Memory {
  signature: string;
  viewport: Viewport | null;
  dragged: Map<string, { x: number; y: number }>;
}

const signatureOf = (graph: Graph) =>
  `${graph.nodes.map((n) => `${n.id}:${n.name}:${n.type === 'value' ? n.version : ''}`).join('|')}#${graph.edges.length}`;

interface LayoutState {
  graph: Graph;
  direction: Direction;
  positions: Map<string, { x: number; y: number }>;
  restore: Viewport | null;
}

export function GraphView() {
  const run = useStore((s) => s.project.run);
  const stale = useStore((s) => isStale(s.project));
  const selectedId = useStore((s) => s.selectedNodeId);
  const theme = useStore((s) => s.theme);
  const selectNode = useStore((s) => s.selectNode);

  const graph = run?.graph;
  const wrapRef = useRef<HTMLDivElement>(null);
  const memory = useRef<Memory>({ signature: '', viewport: null, dragged: new Map() });
  const [layout, setLayout] = useState<LayoutState | null>(null);

  // Раскладка и направление выбираются один раз на запуск по размеру области (при изменении размера панели схема не прыгает).
  useLayoutEffect(() => {
    if (!graph || graph.nodes.length === 0 || layout?.graph === graph) return;
    const box = wrapRef.current?.getBoundingClientRect();
    const signature = signatureOf(graph);
    if (signature !== memory.current.signature) memory.current = { signature, viewport: null, dragged: new Map() };
    setLayout({
      graph,
      ...pickLayout(graph, { w: box?.width || 900, h: box?.height || 800 }),
      restore: memory.current.viewport, // пользователь двигал схему, а структура та же — оставляем его вид
    });
  }, [graph, layout]);
  const ready = !!graph && layout?.graph === graph;

  const built = useMemo<(ValueFlowNode | OutputFlowNode)[]>(() => {
    if (!graph || !layout || layout.graph !== graph) return [];
    const counts = versionCounts(graph.nodes);
    const related = relatedIds(selectedId, graph.edges);
    return graph.nodes.map((node: GraphNode) => {
      const common = {
        selected: node.id === selectedId,
        related: related.has(node.id) && node.id !== selectedId,
        dim: !!selectedId && !related.has(node.id),
        direction: layout.direction,
      };
      const position = memory.current.dragged.get(node.id) ?? layout.positions.get(node.id)!;
      return node.type === 'output'
        ? { id: node.id, type: 'outputBlock' as const, position, data: { node, ...common } }
        : {
            id: node.id, type: 'value' as const, position,
            data: { node, versions: counts.get(node.name) ?? 1, highlight: maskHighlight(node.id, graph, selectedId), ...common },
          };
    });
  }, [graph, layout, selectedId]);

  const [nodes, setNodes, onNodesChange] = useNodesState<ValueFlowNode | OutputFlowNode>(built);
  useEffect(() => setNodes(built), [built, setNodes]);

  const edges = useMemo<Edge[]>(() => {
    if (!graph) return [];
    return graph.edges.map((e, i) => {
      const touches = e.source === selectedId || e.target === selectedId;
      return {
        id: `e${i}`, source: e.source, target: e.target, selectable: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: touches ? 'var(--accent)' : 'var(--edge)' },
        className: `${touches ? 'edge-active' : ''}${selectedId && !touches ? ' edge-dim' : ''}${e.mask ? ' edge-mask' : ''}`,
      };
    });
  }, [graph, selectedId]);

  if (!run) {
    return <div className="empty-state">Нажмите «▶ Запустить» — значения и связи между ними появятся здесь.</div>;
  }
  if (graph && graph.nodes.length === 0) {
    return <div className="empty-state">{run.error ? 'Программа не выполнила ни одной инструкции — подробности в консоли.' : 'Программа не создала переменных и вывода.'}</div>;
  }

  return (
    <div className={`graph${stale ? ' stale' : ''}`} ref={wrapRef}>
      {ready && (
        <ReactFlow
          key={run.startedAt}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeClick={(_, node) => selectNode(node.id === selectedId ? null : node.id)}
          onNodeDragStop={(_, node) => memory.current.dragged.set(node.id, node.position)}
          // event === null — программная подгонка вида; запоминаем только то, что сделал пользователь
          onMoveEnd={(event, viewport) => { if (event) memory.current.viewport = viewport; }}
          onPaneClick={() => selectNode(null)}
          nodesConnectable={false}
          deleteKeyCode={null}
          // Глобальные клавиши React Flow перехватывали ввод в редакторе (пробел включал режим «рука»):
          // схема ими не пользуется, поэтому они отключены.
          panActivationKeyCode={null}
          selectionKeyCode={null}
          multiSelectionKeyCode={null}
          zoomActivationKeyCode={null}
          fitView={!layout?.restore}
          defaultViewport={layout?.restore ?? undefined}
          fitViewOptions={FIT_VIEW}
          minZoom={0.15}
          colorMode={theme === 'auto' ? 'system' : theme}
          proOptions={{ hideAttribution: false }}
        >
          <Background gap={24} size={1} />
          <Controls showInteractive={false} position="bottom-right" fitViewOptions={FIT_VIEW} />
        </ReactFlow>
      )}
    </div>
  );
}

import type { Graph, GraphEdge, GraphNode, LineRange, ValueNode } from './types';

/** Сколько элементов карточка показывает сразу; остальное — «… ещё N». */
const INLINE_MAX_1D = 12;
export const INLINE_ROWS = 8;
const INLINE_MAX_COLS = 8;
const INLINE_WIDTH_BUDGET = 560; // карточка с широкими значениями (0.30000000000000004) показывает меньше элементов

/** Ширина ячейки массива в пикселях: так же считает CSS (min-width 38 + поля). */
export const cellWidth = (text: string) => Math.max(38, Math.round(text.length * 8.4 + 16)) + 2;

/** Сколько элементов одномерного массива показать в карточке. */
export function inlineCount1D(data: string[]): number {
  let width = 0;
  let count = 0;
  for (const text of data.slice(0, INLINE_MAX_1D)) {
    const w = cellWidth(text);
    if (count > 0 && width + w > INLINE_WIDTH_BUDGET) break;
    width += w;
    count += 1;
  }
  return count;
}

const columnWidth = (rows: string[][], j: number) => Math.max(...rows.slice(0, INLINE_ROWS).map((r) => cellWidth(r[j] ?? '')));

/** Сколько столбцов матрицы показать в карточке. */
export function inlineCols(rows: string[][]): number {
  const total = Math.min(rows[0]?.length ?? 0, INLINE_MAX_COLS);
  let width = 0;
  let count = 0;
  for (let j = 0; j < total; j++) {
    const w = columnWidth(rows, j);
    if (count > 0 && width + w > INLINE_WIDTH_BUDGET) break;
    width += w;
    count += 1;
  }
  return count;
}

const MAIN_GAP_LR = 56; // между колонками: стрелке нужно место под наконечник
const MAIN_GAP_TB = 44; // между рядами карточки низкие, зазор меньше
const CROSS_GAP = 24; // между карточками внутри колонки или ряда
const DEFAULT_MAX_EXTENT = 720; // длиннее — колонка переносится, чтобы схема не вытягивалась в одну линию
const FIT_PADDING = 0.12; // совпадает с fitViewOptions.padding: схема занимает (1 − padding) области
const FIT_MAX_ZOOM = 1.3;
const LR_OK_SCALE = 0.85; // при таком масштабе (≈11 px текст) слева направо остаётся
const TB_ADVANTAGE = 1.15; // «сверху вниз» выбирается, только если карточки заметно крупнее

export interface Size {
  w: number;
  h: number;
}

export interface Position {
  x: number;
  y: number;
}

const FOOT_ROW = 18;

/**
 * Приблизительные размеры карточек — нужны только для раскладки. Откалиброваны по реальным размерам в браузере
 * (с небольшим запасом): занижение даёт наложение карточек, завышение — лишнее уменьшение схемы.
 */
export function estimateSize(node: GraphNode, extraFootRows = 0): Size {
  if (node.type === 'output') {
    const lines = node.text.replace(/\n$/, '').split('\n');
    const shown = lines.slice(0, 10);
    const widest = Math.min(56, Math.max(8, ...shown.map((l) => l.length)));
    return {
      w: Math.max(190, widest * 8.2 + 52),
      h: 52 + shown.length * 19 + (lines.length > shown.length ? FOOT_ROW : 0) + (node.truncated || node.unsupported ? FOOT_ROW : 0),
    };
  }
  const v = node.value;
  const foot = ((node.mutated ? 1 : 0) + (node.partial ? 1 : 0) + (node.unsupported ? 1 : 0) + extraFootRows) * FOOT_ROW;
  const exprRow = node.expr && node.expr !== v.repr ? 22 : 0;
  const exprW = node.expr ? Math.min(node.expr.length * 7.3, 460) : 0;
  const meta = [v.shape ? `(${v.shape.join(', ')},)` : '', v.dtype ?? ''].join(' ');
  const headW = node.name.length * 8.2 + meta.length * 6.1 + 70;
  const p = v.preview;
  if (p && p.shownShape.length === 1) {
    const data = p.data as string[];
    const n = inlineCount1D(data);
    const more = (v.shape?.[0] ?? data.length) > n;
    const bodyW = data.slice(0, n).reduce((sum, t) => sum + cellWidth(t), 0) + 28 + (more ? 84 : 0);
    return { w: Math.min(700, Math.max(170, headW, exprW, bodyW) + 36), h: 104 + exprRow + foot };
  }
  if (p && p.shownShape.length === 2) {
    const data = p.data as string[][];
    const cols = inlineCols(data);
    const rows = Math.min(data.length, INLINE_ROWS);
    const moreRows = (v.shape?.[0] ?? rows) > rows;
    const bodyW = 30 + Array.from({ length: cols }, (_, j) => columnWidth(data, j)).reduce((a, b) => a + b, 0)
      + ((v.shape?.[1] ?? cols) > cols ? 34 : 0);
    return { w: Math.min(700, Math.max(170, headW, exprW, bodyW) + 36), h: 74 + exprRow + (rows + (moreRows ? 1 : 0)) * 26 + foot };
  }
  if (!v.preview && !v.note && v.repr.length <= 40 && v.kind !== 'str' && v.kind !== 'dict') {
    // компактная карточка «имя = значение»
    return { w: Math.min(520, node.name.length * 8.2 + v.repr.length * 8.4 + 112), h: 44 + exprRow + foot };
  }
  const text = v.note ?? v.repr;
  return { w: Math.max(200, Math.min(380, text.length * 6.5 + 40)), h: 56 + exprRow + Math.min(4, Math.ceil(text.length / 44)) * 19 + foot };
}

function firstLine(node: GraphNode): number {
  return node.lines[0]?.[0] ?? 0;
}

/** Глубина узла = длина самой длинной цепочки зависимостей, ведущей к нему. */
export function depths(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const incoming = new Map<string, string[]>();
  for (const e of edges) incoming.set(e.target, [...(incoming.get(e.target) ?? []), e.source]);
  const memo = new Map<string, number>();
  const visiting = new Set<string>();
  const depthOf = (id: string): number => {
    const cached = memo.get(id);
    if (cached !== undefined) return cached;
    if (visiting.has(id)) return 0; // защита от цикла (по построению его нет)
    visiting.add(id);
    const d = Math.max(-1, ...(incoming.get(id) ?? []).map(depthOf)) + 1;
    visiting.delete(id);
    memo.set(id, d);
    return d;
  };
  nodes.forEach((n) => depthOf(n.id));
  return memo;
}

export type Direction = 'LR' | 'TB';

/** Размер карточки с учётом подписи «выделено маской» у массивов, которые индексируются маской. */
function sizer(graph: Graph) {
  const maskSources = new Set(graph.edges.filter((e) => e.mask).map((e) => e.source));
  return (node: GraphNode) => estimateSize(node, maskSources.has(node.id) ? 1 : 0);
}

/**
 * Уровень = глубина зависимости. Слева направо (LR) уровень — колонка, сверху вниз (TB) — ряд.
 * Внутри уровня карточки идут в порядке строк кода и центрируются на общей оси; длинные стрелки,
 * пропускающие уровень, не проходят сквозь карточки (нечётные уровни сдвинуты поперёк).
 * Слишком длинный уровень переносится на следующую полосу (maxExtent — предельная длина поперёк).
 */
export function layoutGraph(graph: Graph, direction: Direction = 'LR', maxExtent = DEFAULT_MAX_EXTENT): Map<string, Position> {
  const sizeOf = sizer(graph);
  const depthById = depths(graph.nodes, graph.edges);
  const levels = new Map<number, GraphNode[]>();
  for (const node of graph.nodes) {
    const d = depthById.get(node.id) ?? 0;
    levels.set(d, [...(levels.get(d) ?? []), node]);
  }
  const cross = (s: Size) => (direction === 'LR' ? s.h : s.w);
  const main = (s: Size) => (direction === 'LR' ? s.w : s.h);
  const hasLongEdge = graph.edges.some((e) => (depthById.get(e.target) ?? 0) - (depthById.get(e.source) ?? 0) > 1);
  const widest = Math.max(0, ...graph.nodes.map((n) => cross(sizeOf(n))));
  const shift = hasLongEdge ? widest / 2 + CROSS_GAP : 0;

  const placed: { id: string; main: number; cross: number }[] = [];
  let mainPos = 0;
  for (const d of [...levels.keys()].sort((a, b) => a - b)) {
    const nodes = [...levels.get(d)!].sort((a, b) => firstLine(a) - firstLine(b));
    const bands: GraphNode[][] = [];
    let current: GraphNode[] = [];
    let extent = 0;
    for (const node of nodes) {
      const c = cross(sizeOf(node));
      if (current.length && extent + CROSS_GAP + c > maxExtent) {
        bands.push(current);
        current = [];
        extent = 0;
      }
      extent += (current.length ? CROSS_GAP : 0) + c;
      current.push(node);
    }
    bands.push(current);
    for (const band of bands) {
      const total = band.reduce((sum, n, i) => sum + cross(sizeOf(n)) + (i ? CROSS_GAP : 0), 0);
      let offset = (d % 2 === 1 ? shift : 0) - total / 2;
      for (const node of band) {
        placed.push({ id: node.id, main: mainPos, cross: offset });
        offset += cross(sizeOf(node)) + CROSS_GAP;
      }
      mainPos += Math.max(...band.map((n) => main(sizeOf(n)))) + (direction === 'LR' ? MAIN_GAP_LR : MAIN_GAP_TB);
    }
  }
  const minCross = Math.min(0, ...placed.map((p) => p.cross));
  return new Map(placed.map((p) => [p.id, direction === 'LR'
    ? { x: p.main, y: p.cross - minCross }
    : { x: p.cross - minCross, y: p.main }]));
}

export function layoutBounds(graph: Graph, positions: Map<string, Position>): Size {
  const sizeOf = sizer(graph);
  let w = 0;
  let h = 0;
  for (const node of graph.nodes) {
    const p = positions.get(node.id);
    if (!p) continue;
    const s = sizeOf(node);
    w = Math.max(w, p.x + s.w);
    h = Math.max(h, p.y + s.h);
  }
  return { w, h };
}

/** Масштаб, с которым схема поместится в область (так же считает подгонка вида). */
export function fitScale(bounds: Size, pane: Size): number {
  if (bounds.w === 0 || bounds.h === 0) return FIT_MAX_ZOOM;
  const usable = 1 - FIT_PADDING;
  return Math.min(FIT_MAX_ZOOM, (pane.w * usable) / bounds.w, (pane.h * usable) / bounds.h);
}

/**
 * Направление выбирается по тому, при каком карточки получаются крупнее: длинная цепочка в широкой
 * строке сжимается до нечитаемого размера, а сверху вниз (как читается код) укладывается в область.
 * Слева направо — по умолчанию (как в n8n); сверху вниз — только если так карточки заметно крупнее
 * и слева направо они мельче порога читаемости.
 */
export function pickLayout(graph: Graph, pane: Size): { direction: Direction; positions: Map<string, Position> } {
  const build = (direction: Direction) => {
    const maxExtent = Math.max(360, (direction === 'LR' ? pane.h : pane.w) * 0.95);
    const positions = layoutGraph(graph, direction, maxExtent);
    return { direction, positions, scale: fitScale(layoutBounds(graph, positions), pane) };
  };
  const lr = build('LR');
  const tb = build('TB');
  const best = lr.scale >= LR_OK_SCALE || tb.scale <= lr.scale * TB_ADVANTAGE ? lr : tb;
  return { direction: best.direction, positions: best.positions };
}

export interface MaskHighlight {
  maskName: string;
  /** те же индексы, что и у preview.data источника */
  picked: (i: number, j?: number) => boolean;
  count: number;
}

/**
 * Какие элементы массива-источника выбраны булевой маской. Берётся стрелка источник → потребитель,
 * помеченная сервером (a[mask]); если у источника несколько таких стрелок, приоритет у выбранного потребителя.
 */
export function maskHighlight(nodeId: string, graph: Graph, selectedId: string | null): MaskHighlight | null {
  const node = graph.nodes.find((n) => n.id === nodeId);
  if (!node || node.type !== 'value' || !node.value.preview) return null;
  const marked = graph.edges.filter((e) => e.source === nodeId && e.mask);
  const edge = marked.find((e) => e.target === selectedId) ?? marked[0];
  if (!edge?.mask) return null;
  const maskNode = graph.nodes.find((n) => n.id === edge.mask);
  if (!maskNode || maskNode.type !== 'value' || !maskNode.value.preview) return null;
  const a = node.value.preview;
  const m = maskNode.value.preview;
  if (a.shownShape.join() !== m.shownShape.join()) return null;
  const at = (i: number, j?: number) =>
    (j === undefined ? (m.data as string[])[i] : (m.data as string[][])[i]?.[j]) === 'True';
  let count = 0;
  if (m.shownShape.length === 1) (m.data as string[]).forEach((x) => (count += x === 'True' ? 1 : 0));
  else (m.data as string[][]).forEach((row) => row.forEach((x) => (count += x === 'True' ? 1 : 0)));
  return { maskName: maskNode.name, picked: at, count };
}

/** Подпись версии показывается только у имён, которые присваивались несколько раз. */
export function versionCounts(nodes: GraphNode[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const n of nodes) if (n.type === 'value') counts.set(n.name, (counts.get(n.name) ?? 0) + 1);
  return counts;
}

/** Выбранный узел и узлы, связанные с ним стрелкой напрямую (источники и потребители). */
export function relatedIds(selectedId: string | null, edges: GraphEdge[]): Set<string> {
  const related = new Set<string>();
  if (!selectedId) return related;
  related.add(selectedId);
  for (const e of edges) {
    if (e.source === selectedId) related.add(e.target);
    if (e.target === selectedId) related.add(e.source);
  }
  return related;
}

export function linesLabel(lines: LineRange[]): string {
  return lines.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(', ');
}

export function isValueNode(node: GraphNode): node is ValueNode {
  return node.type === 'value';
}

export function shapeText(shape: number[] | undefined): string {
  if (!shape) return '';
  return `(${shape.join(', ')}${shape.length === 1 ? ',' : ''})`;
}

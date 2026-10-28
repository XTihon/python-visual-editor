import { describe, expect, it } from 'vitest';
import { depths, estimateSize, fitScale, layoutBounds, layoutGraph, maskHighlight, pickLayout, relatedIds, versionCounts } from './graph';
import type { Graph, ValueInfo, ValueNode } from './types';

const info = (name: string, over: Partial<ValueInfo> = {}): ValueInfo => ({
  name, type: 'int', kind: 'scalar', repr: '1', truncated: false, hidden: false, ...over,
});

const value = (id: string, name: string, line: number, over: Partial<ValueInfo> = {}, version = 1): ValueNode => ({
  id, type: 'value', name, version, lines: [[line, line]], expr: null, mutated: false, partial: null,
  unsupported: null, value: info(name, over),
});

const arr = (data: string[], dtypeKind: ValueInfo['dtypeKind'] = 'int'): Partial<ValueInfo> => ({
  kind: 'ndarray', type: 'ndarray', shape: [data.length], dtype: 'int64', dtypeKind,
  preview: { data, shownShape: [data.length], hidden: 0 },
});

// a → mask, a → result (маска mask), mask → result, result → output
const spec = (): Graph => ({
  nodes: [
    value('n1', 'a', 3, arr(['2', '7', '4', '9'])),
    value('n2', 'mask', 4, arr(['False', 'True', 'False', 'True'], 'bool')),
    value('n3', 'result', 5, arr(['7', '9'])),
    { id: 'output', type: 'output', name: 'output', text: '[7 9]\n', truncated: false, lines: [[6, 6]], unsupported: null },
  ],
  edges: [
    { source: 'n1', target: 'n2' },
    { source: 'n1', target: 'n3', mask: 'n2' },
    { source: 'n2', target: 'n3' },
    { source: 'n3', target: 'output' },
  ],
  notes: [], dropped: 0,
});

describe('раскладка', () => {
  it('глубина = длина самой длинной цепочки зависимостей', () => {
    const g = spec();
    const d = depths(g.nodes, g.edges);
    expect([d.get('n1'), d.get('n2'), d.get('n3'), d.get('output')]).toEqual([0, 1, 2, 3]);
  });

  it('колонки идут слева направо без пересечений карточек', () => {
    const g = spec();
    const pos = layoutGraph(g);
    const xs = ['n1', 'n2', 'n3', 'output'].map((id) => pos.get(id)!.x);
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
    expect(new Set(xs).size).toBe(4);
    for (let i = 0; i + 1 < 4; i++) {
      const id = ['n1', 'n2', 'n3'][i];
      expect(pos.get(id)!.x + estimateSize(g.nodes[i]).w).toBeLessThan(xs[i + 1]);
    }
  });

  it('узлы одной колонки стоят друг под другом в порядке строк и не налезают', () => {
    const g: Graph = {
      nodes: [value('n2', 'b', 7), value('n1', 'a', 2, arr(['1', '2', '3']))], edges: [], notes: [], dropped: 0,
    };
    const pos = layoutGraph(g);
    expect(pos.get('n1')!.y).toBe(0);
    expect(pos.get('n2')!.y).toBeGreaterThanOrEqual(estimateSize(g.nodes[1]).h);
    expect(pos.get('n1')!.x).toBe(pos.get('n2')!.x);
  });

  it('повторные версии одного имени — отдельные узлы в своих колонках', () => {
    const g: Graph = {
      nodes: [value('n1', 'x', 1, {}, 1), value('n2', 'x', 2, {}, 2)],
      edges: [{ source: 'n1', target: 'n2' }], notes: [], dropped: 0,
    };
    const pos = layoutGraph(g);
    expect(pos.get('n2')!.x).toBeGreaterThan(pos.get('n1')!.x);
    expect([...versionCounts(g.nodes)]).toEqual([['x', 2]]);
  });
});

describe('раскладка многих несвязанных значений', () => {
  it('высокая колонка переносится вправо, карточки не пересекаются', () => {
    const nodes = Array.from({ length: 12 }, (_, i) => value(`n${i}`, `v${i}`, i + 1, arr(['1', '2', '3', '4'])));
    const g: Graph = { nodes, edges: [], notes: [], dropped: 0 };
    const pos = layoutGraph(g);
    const xs = new Set(nodes.map((n) => pos.get(n.id)!.x));
    expect(xs.size).toBeGreaterThan(1);
    const bottoms = nodes.map((n) => pos.get(n.id)!.y + estimateSize(n).h);
    expect(Math.max(...bottoms)).toBeLessThanOrEqual(720 + 30);
    for (const a of nodes) for (const b of nodes) {
      if (a === b) continue;
      const pa = pos.get(a.id)!, pb = pos.get(b.id)!, sa = estimateSize(a), sb = estimateSize(b);
      const overlap = pa.x < pb.x + sb.w && pb.x < pa.x + sa.w && pa.y < pb.y + sb.h && pb.y < pa.y + sa.h;
      expect(overlap).toBe(false);
    }
  });

  it('зависимые узлы остаются правее своих источников даже после переноса колонок', () => {
    const nodes = [
      ...Array.from({ length: 10 }, (_, i) => value(`s${i}`, `s${i}`, i + 1, arr(['1', '2', '3', '4']))),
      value('t', 't', 20),
    ];
    const g: Graph = { nodes, edges: nodes.slice(0, 10).map((n) => ({ source: n.id, target: 't' })), notes: [], dropped: 0 };
    const pos = layoutGraph(g);
    const rightmost = Math.max(...nodes.slice(0, 10).map((n) => pos.get(n.id)!.x + estimateSize(n).w));
    expect(pos.get('t')!.x).toBeGreaterThan(rightmost);
  });
});

describe('выделение элементов маской', () => {
  it('в массиве-источнике выделяются элементы, где маска True', () => {
    const h = maskHighlight('n1', spec(), null)!;
    expect(h.maskName).toBe('mask');
    expect([0, 1, 2, 3].map((i) => h.picked(i))).toEqual([false, true, false, true]);
    expect(h.count).toBe(2);
  });

  it('у узлов без помеченной стрелки выделения нет', () => {
    expect(maskHighlight('n2', spec(), null)).toBeNull();
    expect(maskHighlight('n3', spec(), null)).toBeNull();
  });

  it('несовместимые предпросмотры не выделяются', () => {
    const g = spec();
    (g.nodes[1] as ValueNode).value.preview = { data: ['True'], shownShape: [1], hidden: 0 };
    expect(maskHighlight('n1', g, null)).toBeNull();
  });

  it('работает для двумерных массивов', () => {
    const g = spec();
    (g.nodes[0] as ValueNode).value.preview = { data: [['1', '2'], ['3', '4']], shownShape: [2, 2], hidden: 0 };
    (g.nodes[1] as ValueNode).value.preview = { data: [['True', 'False'], ['False', 'True']], shownShape: [2, 2], hidden: 0 };
    const h = maskHighlight('n1', g, null)!;
    expect([h.picked(0, 0), h.picked(0, 1), h.picked(1, 0), h.picked(1, 1)]).toEqual([true, false, false, true]);
  });

  it('при нескольких масках приоритет у выбранного потребителя', () => {
    const g = spec();
    g.nodes.push(value('n4', 'm2', 6, arr(['True', 'True', 'False', 'False'], 'bool')));
    g.nodes.push(value('n5', 'other', 7, arr(['2', '7'])));
    g.edges.push({ source: 'n1', target: 'n5', mask: 'n4' });
    expect(maskHighlight('n1', g, 'n3')!.maskName).toBe('mask');
    expect(maskHighlight('n1', g, 'n5')!.maskName).toBe('m2');
  });
});

describe('связанные узлы', () => {
  it('подсвечиваются только непосредственные соседи выбранного узла', () => {
    const g = spec();
    expect([...relatedIds('n2', g.edges)].sort()).toEqual(['n1', 'n2', 'n3']); // output — через result, не напрямую
    expect([...relatedIds('n1', g.edges)].sort()).toEqual(['n1', 'n2', 'n3']);
    expect([...relatedIds('output', g.edges)].sort()).toEqual(['n3', 'output']);
    expect(relatedIds(null, g.edges).size).toBe(0);
  });
});

// цепочка a → b → c → d → e: длинная и узкая по высоте
const chain = (n: number): Graph => {
  const nodes = Array.from({ length: n }, (_, i) => value(`n${i}`, `v${i}`, i + 1, arr(['1', '2', '3'])));
  return { nodes, edges: nodes.slice(1).map((node, i) => ({ source: nodes[i].id, target: node.id })), notes: [], dropped: 0 };
};
const overlaps = (g: Graph, pos: Map<string, { x: number; y: number }>) =>
  g.nodes.some((a, i) => g.nodes.some((b, j) => {
    if (i >= j) return false;
    const pa = pos.get(a.id)!, pb = pos.get(b.id)!, sa = estimateSize(a), sb = estimateSize(b);
    return pa.x < pb.x + sb.w && pb.x < pa.x + sa.w && pa.y < pb.y + sb.h && pb.y < pa.y + sa.h;
  }));

describe('направление и масштаб схемы', () => {
  it('сверху вниз: уровни идут вниз, карточки не пересекаются, ряды центрированы', () => {
    const g = chain(5);
    const pos = layoutGraph(g, 'TB');
    const ys = g.nodes.map((n) => pos.get(n.id)!.y);
    expect(ys).toEqual([...ys].sort((a, b) => a - b));
    expect(new Set(ys).size).toBe(5);
    expect(new Set(g.nodes.map((n) => pos.get(n.id)!.x)).size).toBe(1); // одна ось
    expect(overlaps(g, pos)).toBe(false);
  });

  it('слева направо: колонки центрированы по вертикали на общей оси', () => {
    const g: Graph = {
      nodes: [value('a', 'a', 1, arr(['1', '2'])), value('b', 'b', 2), value('c', 'c', 3, arr(['1', '2']))],
      edges: [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }], notes: [], dropped: 0,
    };
    const pos = layoutGraph(g, 'LR');
    const centers = g.nodes.map((n) => pos.get(n.id)!.y + estimateSize(n).h / 2);
    expect(Math.max(...centers) - Math.min(...centers)).toBeLessThan(1);
  });

  it('длинная цепочка в почти квадратной области укладывается сверху вниз и получается крупнее', () => {
    const g = chain(6);
    const pane = { w: 930, h: 880 };
    const picked = pickLayout(g, pane);
    const lr = fitScale(layoutBounds(g, layoutGraph(g, 'LR', 836)), pane);
    const chosen = fitScale(layoutBounds(g, picked.positions), pane);
    expect(picked.direction).toBe('TB');
    expect(chosen).toBeGreaterThan(lr * 1.15);
    expect(chosen).toBeGreaterThan(0.8); // карточки не сжимаются до нечитаемого размера
  });

  it('короткая схема, которая и так читается, остаётся слева направо', () => {
    expect(pickLayout(chain(2), { w: 930, h: 880 }).direction).toBe('LR');
    expect(pickLayout(spec(), { w: 1500, h: 700 }).direction).toBe('LR'); // широкая область
  });

  it('четыре блока в почти квадратной области укладываются сверху вниз и читаются крупно', () => {
    const g = spec();
    const picked = pickLayout(g, { w: 930, h: 880 });
    expect(picked.direction).toBe('TB');
    expect(fitScale(layoutBounds(g, picked.positions), { w: 930, h: 880 })).toBeGreaterThan(1);
  });

  it('в широкой области длинная цепочка остаётся слева направо', () => {
    expect(pickLayout(chain(4), { w: 1500, h: 420 }).direction).toBe('LR');
  });

  it('несвязанные значения переносятся по размеру области, а не по фиксированному порогу', () => {
    const nodes = Array.from({ length: 9 }, (_, i) => value(`n${i}`, `v${i}`, i + 1, arr(['1', '2', '3'])));
    const g: Graph = { nodes, edges: [], notes: [], dropped: 0 };
    const tall = pickLayout(g, { w: 930, h: 1400 });
    const short = pickLayout(g, { w: 930, h: 500 });
    const columns = (pos: Map<string, { x: number; y: number }>) => new Set(nodes.map((n) => pos.get(n.id)!.x)).size;
    expect(columns(short.positions)).toBeGreaterThan(columns(tall.positions));
    expect(overlaps(g, short.positions)).toBe(false);
    expect(overlaps(g, tall.positions)).toBe(false);
  });
});

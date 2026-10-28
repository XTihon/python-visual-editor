export type DtypeKind = 'bool' | 'int' | 'float' | 'complex' | 'str' | 'other';

export interface Preview {
  /** 1D: string[]; 2D: string[][] — уже отформатированные значения */
  data: string[] | string[][];
  shownShape: number[];
  hidden: number;
}

export interface ValueInfo {
  name: string;
  type: string;
  kind: 'ndarray' | 'scalar' | 'str' | 'list' | 'dict' | 'object' | 'module' | 'function' | 'class';
  repr: string;
  truncated: boolean;
  hidden: boolean;
  shape?: number[];
  dtype?: string;
  ndim?: number;
  size?: number;
  dtypeKind?: DtypeKind;
  length?: number;
  preview?: Preview | null;
  note?: string;
}

export type LineRange = [number, number];

export interface ValueNode {
  id: string;
  type: 'value';
  name: string;
  version: number;
  lines: LineRange[];
  expr: string | null;
  /** изменён на месте (a[0] = 1, a.sort()), а не присвоен заново */
  mutated: boolean;
  /** вызов пользовательской функции: связи внутри неё не анализируются */
  partial: string | null;
  /** конструкция, для которой связи не определяются (цикл for, if…) */
  unsupported: string | null;
  value: ValueInfo;
}

export interface OutputNode {
  id: string;
  type: 'output';
  name: 'output';
  text: string;
  truncated: boolean;
  lines: LineRange[];
  unsupported: string | null;
}

export type GraphNode = ValueNode | OutputNode;

export interface GraphEdge {
  source: string;
  target: string;
  /** id узла булевой маски, которой источник индексируется в целевой инструкции */
  mask?: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  notes: string[];
  dropped: number;
}

export type ErrorKind = 'exception' | 'syntax' | 'timeout' | 'stopped' | 'crash';

export interface RunError {
  kind: ErrorKind;
  type: string;
  message: string;
  text: string;
  line: number | null;
}

export interface RunResult {
  status: 'done' | 'error';
  startedAt: string;
  durationMs: number;
  /** код, который выполнялся: по нему определяется, что схема устарела */
  code: string;
  stdout: string;
  stderr: string;
  outputTruncated: boolean;
  error: RunError | null;
  partial: boolean;
  notice: string | null;
  graph: Graph;
}

export interface Project {
  schemaVersion: 2;
  id: string;
  name: string;
  code: string;
  run: RunResult | null;
  createdAt: string;
  updatedAt: string;
  migratedFrom?: number | null;
  original?: Record<string, unknown> | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  updatedAt: string;
}

export interface RunStatus {
  running: boolean;
  defaultTimeoutSec: number;
}

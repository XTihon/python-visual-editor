import type { Project, ProjectSummary, RunResult, RunStatus } from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailText(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d))).join('; ');
  }
  return 'Неизвестная ошибка сервера.';
}

async function request<T>(method: string, url: string, body?: unknown, as: 'json' | 'text' = 'json'): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Нет связи с локальным сервером. Он запущен? (запустите start.ps1)');
  }
  if (!resp.ok) {
    let message = `Ошибка сервера (${resp.status}).`;
    try {
      message = detailText((await resp.json()).detail);
    } catch {
      /* тело не JSON — оставляем общий текст */
    }
    throw new ApiError(resp.status, message);
  }
  return (as === 'text' ? resp.text() : resp.json()) as Promise<T>;
}

export const api = {
  status: () => request<RunStatus>('GET', '/api/status'),
  run: (body: { code: string; timeoutSec: number }) => request<RunResult>('POST', '/api/run', body),
  stop: () => request<{ stopped: boolean }>('POST', '/api/stop'),
  listProjects: () => request<ProjectSummary[]>('GET', '/api/projects'),
  loadProject: (id: string) => request<Project>('GET', `/api/projects/${encodeURIComponent(id)}`),
  saveProject: (project: Project) =>
    request<Project>('PUT', `/api/projects/${encodeURIComponent(project.id)}`, project),
  importProject: (raw: unknown) => request<Project>('POST', '/api/projects/import', raw),
  listExamples: () => request<{ id: string; name: string }[]>('GET', '/api/examples'),
  loadExample: (id: string) => request<Project>('GET', `/api/examples/${encodeURIComponent(id)}`),
  exportPython: (project: Project) => request<string>('POST', '/api/export/py', project, 'text'),
  exportMarkdown: (project: Project) => request<string>('POST', '/api/export/md', project, 'text'),
};

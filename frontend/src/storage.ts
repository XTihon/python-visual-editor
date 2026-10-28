/** localStorage бывает недоступен (приватный режим, запрет): интерфейс должен работать и без него. */
export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(`vr:${key}`);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(`vr:${key}`, value);
  } catch {
    /* не критично */
  }
}

import { Api, ConnectionError, HttpError } from "./api";

function retryable(error: unknown): boolean {
  if (error instanceof HttpError)
    return error.status >= 500 || [408, 429].includes(error.status);
  return (
    error instanceof ConnectionError || error instanceof TypeError ||
    (error instanceof DOMException &&
      ["AbortError", "TimeoutError"].includes(error.name))
  );
}

/** Retry read-only monitoring; job submissions and other writes never pass here. */
export function pollRead<T>(
  api: Api,
  path: string,
  options: {
    intervalMs: number;
    initialDelayMs?: number;
    onValue: (value: T) => boolean | void;
    onRetry: (error: unknown) => void;
    onError: (error: unknown) => void;
  },
): () => void {
  let stopped = false;
  let failures = 0;
  let timer: number | undefined;
  let request: AbortController | undefined;
  const poll = async () => {
    const controller = new AbortController();
    request = controller;
    const deadline = window.setTimeout(() => controller.abort(), 15000);
    let delay = options.intervalMs;
    try {
      const value = await api.request<T>(path, "GET", undefined, controller.signal);
      if (stopped) return;
      failures = 0;
      if (options.onValue(value) === false) return;
    } catch (error) {
      if (stopped) return;
      if (!retryable(error)) {
        options.onError(error);
        return;
      }
      delay = Math.min(15000, 1000 * 2 ** Math.min(failures++, 4));
      options.onRetry(error);
    } finally {
      clearTimeout(deadline);
      request = undefined;
    }
    if (!stopped) timer = window.setTimeout(poll, delay);
  };
  timer = window.setTimeout(poll, options.initialDelayMs ?? 0);
  return () => {
    stopped = true;
    clearTimeout(timer);
    request?.abort();
  };
}

// Typed fetch wrapper: unwraps the backend error envelope, one retry on 5xx.

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string | null;

  constructor(code: string, message: string, status: number, requestId: string | null) {
    super(message);
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

async function parseError(resp: Response): Promise<ApiError> {
  let code = "HTTP_ERROR";
  let message = `Request failed (${resp.status})`;
  let requestId: string | null = resp.headers.get("X-Request-Id");
  try {
    const body = await resp.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      requestId = body.error.request_id ?? requestId;
    }
  } catch {
    // non-JSON error body; keep defaults
  }
  return new ApiError(code, message, resp.status, requestId);
}

async function request<T>(path: string, init?: RequestInit, retry = true): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (err) {
    throw new ApiError("NETWORK_ERROR", "Backend unreachable — is uvicorn running on :8000?", 0, null);
  }
  if (!resp.ok) {
    if (retry && resp.status >= 500) {
      await new Promise((r) => setTimeout(r, 800));
      return request<T>(path, init, false);
    }
    throw await parseError(resp);
  }
  return (await resp.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
};

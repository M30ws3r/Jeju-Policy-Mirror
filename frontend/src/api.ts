import type { AnalysisResult, ApiError, Meta } from "./types";

// 기본은 같은 출처(/api). 프런트와 API 를 다른 도메인에 둘 때만 VITE_API_BASE(https) 를 지정한다.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";
if (BASE && !BASE.startsWith("https://")) {
  throw new Error("VITE_API_BASE 는 https:// 주소여야 합니다.");
}

// CSRF 토큰은 메모리에만 둔다 (localStorage 에 저장하지 않는다). 세션 토큰은 HttpOnly 쿠키라 스크립트가 읽을 수 없다.
let csrfToken = "";

export class ApiFailure extends Error {
  constructor(public readonly info: ApiError, public readonly status: number) {
    super(info.message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (csrfToken && init.method === "POST") headers.set("X-CSRF-Token", csrfToken);
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new ApiFailure({ code: "network", message: "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요." }, 0);
  }
  if (!response.ok) {
    let info: ApiError = { code: "error", message: "요청을 처리할 수 없습니다." };
    try {
      const body = (await response.json()) as { error?: ApiError };
      if (body.error?.message) info = body.error;
    } catch {
      /* 본문이 JSON 이 아니면 기본 메시지를 쓴다 */
    }
    throw new ApiFailure(info, response.status);
  }
  return response as unknown as T;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request<Response>(path, init);
  return (await response.json()) as T;
}

export const api = {
  meta: () => json<Meta>("/api/meta"),

  async me(): Promise<string | null> {
    try {
      const data = await json<{ email_masked: string; csrf_token: string }>("/api/auth/me");
      csrfToken = data.csrf_token;
      return data.email_masked;
    } catch {
      return null;
    }
  },

  async auth(kind: "login" | "register", email: string, password: string): Promise<void> {
    const data = await json<{ csrf_token: string }>(`/api/auth/${kind}`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    csrfToken = data.csrf_token;
  },

  async logout(): Promise<void> {
    await json("/api/auth/logout", { method: "POST" });
    csrfToken = "";
  },

  analyze: (payload: { question: string; area?: string; policy_month?: string; industry?: string }) =>
    json<AnalysisResult>("/api/analyze", { method: "POST", body: JSON.stringify(payload) }),

  async downloadPdf(analysisId: string): Promise<void> {
    const response = await request<Response>(`/api/analyses/${encodeURIComponent(analysisId)}/pdf`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `정책검토보고서-${analysisId.slice(0, 8)}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  },
};

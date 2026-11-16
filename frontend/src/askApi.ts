// 실데이터 문장 질문 API (백엔드 app/main_v3.py: POST /api/ask, /api/ask/pdf).
// 새 파일로 만든 이유: 사례 조회(casesApi.ts)와 합성 샘플 질문(api.ts)의 동작을 바꾸지 않기 위함.
// 이 요청은 서버에 아무것도 저장하지 않으므로 로그인·CSRF 토큰이 필요 없다.
import { CaseFailure, type CaseResult } from "./casesApi";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export interface AskOptions {
  first_month: string;
  last_month: string;
  examples: string[];
}
export type AskResponse =
  | (CaseResult & { status: "done"; options: AskOptions })
  | { status: "needs_input"; message: string; options: AskOptions };

async function post(path: string, question: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new CaseFailure("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  }
  if (!response.ok) {
    let message = response.status === 422 ? "질문을 확인해 주세요 (300자 이내)." : "요청을 처리할 수 없습니다.";
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      if (body.error?.message && response.status !== 422) message = body.error.message;
    } catch {
      /* 기본 메시지 사용 */
    }
    throw new CaseFailure(message);
  }
  return response;
}

export const askApi = {
  ask: async (question: string) => (await (await post("/api/ask", question)).json()) as AskResponse,
  async downloadPdf(question: string): Promise<void> {
    const blob = await (await post("/api/ask/pdf", question)).blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "정책검토보고서-질문.pdf";
    link.click();
    URL.revokeObjectURL(url);
  },
};

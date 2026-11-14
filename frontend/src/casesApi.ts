// 버스 실데이터 정책 사례 API (백엔드 app/main_v2.py).
// 새 파일로 만든 이유: 기존 api.ts 는 합성 샘플 질문 분석·로그인 흐름 전용이라, 그 동작을 바꾸지 않고 사례 조회만 따로 둔다.
import type { AnalysisResult } from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export interface CaseItem {
  id: string;
  label: string;
  question: string;
  policy: string;
  policy_month: string;
}

export interface CaseResult extends AnalysisResult {
  case_id: string;
  observed?: AnalysisResult["observed"] & {
    target_daily_pre?: number;
    target_daily_post?: number;
    island_before_after_pct?: number;
  };
}

export class CaseFailure extends Error {}

async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { credentials: "include" });
  } catch {
    throw new CaseFailure("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  }
  if (!response.ok) {
    let message = "요청을 처리할 수 없습니다.";
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      if (body.error?.message) message = body.error.message;
    } catch {
      /* 기본 메시지 사용 */
    }
    throw new CaseFailure(message);
  }
  return (await response.json()) as T;
}

export const casesApi = {
  list: () => getJson<{ available: boolean; items: CaseItem[] }>("/api/cases"),
  get: (id: string) => getJson<CaseResult>(`/api/cases/${encodeURIComponent(id)}`),
  async downloadPdf(id: string): Promise<void> {
    let response: Response;
    try {
      response = await fetch(`${BASE}/api/cases/${encodeURIComponent(id)}/pdf`, { credentials: "include" });
    } catch {
      throw new CaseFailure("서버에 연결할 수 없습니다.");
    }
    if (!response.ok) throw new CaseFailure("PDF 를 만들 수 없습니다.");
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `정책검토보고서-${id}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  },
};

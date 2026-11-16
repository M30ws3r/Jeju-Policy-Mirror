// 화면 v3: 실데이터만 보여 준다 — 실제 정책 사례(위) + 실데이터 자유 질문(아래).
// 새 파일로 만든 이유: v2 는 아래쪽 자유 질문이 합성 샘플이라 '실데이터 에이전트'라는 기획과 어긋났다.
// 합성 샘플 화면(App.tsx)과 v2(AppV2.tsx)는 지우지 않고 남겨 두며, main.tsx 의 import 만 바꾸면 되돌릴 수 있다.
import { AskPanel } from "./components/AskPanel";
import { CasesPanel } from "./components/CasesPanel";

export function AppV3() {
  return (
    <div className="page page-top">
      <header style={{ marginBottom: 16 }}>
        <h1>Jeju Policy Mirror</h1>
        <p className="lead">정책을 시행한 뒤 정말 달라졌는지, 계절이나 관광 수요 변화 때문은 아닌지 실데이터로 확인합니다.</p>
        <p className="small">
          사용 자료: 제주데이터허브 일일 노선별 버스 이용자 정보(API, 4일 간격 표본) · 제주관광빅데이터플랫폼 카드 관광 읍면동 리 월별 통계(파일)
        </p>
      </header>
      <CasesPanel />
      <AskPanel />
    </div>
  );
}

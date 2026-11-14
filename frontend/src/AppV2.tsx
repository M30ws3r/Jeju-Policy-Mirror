// 화면 v2: 실제 정책 사례(버스 실데이터)를 맨 위에, 기존 자유 질문 화면(합성 샘플)을 아래에 둔다.
// 새 파일로 만든 이유: 기존 App.tsx 를 그대로 두고 감싸기만 해서, 이전 화면으로 언제든 되돌릴 수 있게 하기 위함.
// 되돌리려면 main.tsx 의 import 를 "./App" 으로 바꾸면 된다.
import { App } from "./App";
import { CasesPanel } from "./components/CasesPanel";

export function AppV2() {
  return (
    <>
      <div className="page page-top">
        <CasesPanel />
      </div>
      <div className="divider-note">
        <p className="small">아래는 자유 질문 시연입니다 (합성 샘플 데이터, 실제 수치 아님).</p>
      </div>
      <App />
    </>
  );
}

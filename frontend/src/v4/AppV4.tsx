// 화면 v4: '근미래 잡지' 방향의 편집 디자인. 기능은 v3 와 같고(실데이터 사례 + 실데이터 질문) 배치와 표현만 바꿨다.
// 새 파일로 만든 이유: v3(AppV3.tsx)를 그대로 두어 main.tsx 한 줄로 되돌릴 수 있게 하기 위함.
import { AskPanelV2 } from "./AskPanelV2";
import { CaseIndex } from "./CaseIndex";
import { HeroMirror } from "./HeroMirror";

export function AppV4() {
  return (
    <div className="mag">
      <header className="masthead">
        <p className="wordmark">Jeju Policy Mirror</p>
        <nav aria-label="바로가기">
          <a href="#cases">실제 사례</a>
          <a href="#ask">직접 질문하기</a>
        </nav>
      </header>

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-text">
            <h1 id="hero-title">
              감차 뒤 이용객이 줄었다면,
              <br />
              정말 감차 때문일까요?
            </h1>
            <p className="lead">
              Jeju Policy Mirror는 제주 정책을 시행한 뒤 숫자가 달라졌을 때, 그 변화가 정책 때문인지 계절이나 관광객 흐름 때문인지 실데이터로 가려
              냅니다. 비교할 조건이 갖춰지지 않으면 효과를 말하지 않고, 확인된 사실만 보고합니다.
            </p>
          </div>
          <HeroMirror />
        </section>

        <section id="cases" className="chapter" aria-labelledby="cases-title">
          <div className="chapter-head">
            <h2 id="cases-title">2024년 8월 버스 노선 개편, 다섯 가지 질문</h2>
            <p>
              제주도는 이때 85개 노선을 조정하고 버스 75대를 줄였습니다. 질문을 누르면 에이전트가 시행 전 흐름이 비슷한 노선을 비교 대상으로 고르고,
              10가지 점검을 통과한 만큼만 결론을 냅니다.
            </p>
          </div>
          <CaseIndex />
        </section>

        <section id="ask" className="chapter" aria-labelledby="ask-title">
          <div className="chapter-head">
            <h2 id="ask-title">직접 질문하기</h2>
            <p>노선 번호와 정책 시행 연월을 넣어 물어보세요. 여러 노선을 적으면 합쳐서 하나로 봅니다. 위 사례와 같은 데이터, 같은 점검을 거칩니다.</p>
          </div>
          <AskPanelV2 />
        </section>
      </main>

      <footer className="colophon">
        <p>
          사용한 자료: 제주데이터허브 일일 노선별 버스 이용자 정보(API, 4일 간격 표본), 제주관광공사 제주관광빅데이터플랫폼 카드 관광 읍면동 리 월별
          통계(파일, 원천 BC카드, 공공누리 제1유형).
        </p>
        <p>분석 결과는 노선 단위 집계만 쓰며, 질문 내용은 저장하지 않습니다.</p>
      </footer>
    </div>
  );
}

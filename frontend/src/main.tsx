import React from "react";
import { createRoot } from "react-dom/client";
import { AppV4 as App } from "./v4/AppV4"; // v4 화면(편집 디자인). 이전 화면: "./AppV3" 의 AppV3, "./AppV2" 의 AppV2, "./App" 의 App
import "./styles.css";
import "./v4/theme.css"; // v4 디자인. 이 줄과 위 App import 를 되돌리면 v3 모양으로 돌아감

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

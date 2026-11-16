import React from "react";
import { createRoot } from "react-dom/client";
import { AppV3 as App } from "./AppV3"; // v3 화면(실데이터 전용). 이전 화면: "./AppV2" 의 AppV2, "./App" 의 App
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

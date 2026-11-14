import React from "react";
import { createRoot } from "react-dom/client";
import { AppV2 as App } from "./AppV2"; // v2 화면. 이전 화면은 "./App" 의 App
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

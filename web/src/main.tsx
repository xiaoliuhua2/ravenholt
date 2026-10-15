import "@douyinfe/semi-ui/react19-adapter";
import { LocaleProvider } from "@douyinfe/semi-ui";
import zhCN from "@douyinfe/semi-ui/lib/es/locale/source/zh_CN";
import React from "react";
import ReactDOM from "react-dom/client";
import "@douyinfe/semi-ui/lib/es/_base/base.css";
import { App } from "./app/App";
import { ThemeProvider } from "./shared/theme/ThemeProvider";
import "./app/styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider>
      <LocaleProvider locale={zhCN}>
        <App />
      </LocaleProvider>
    </ThemeProvider>
  </React.StrictMode>,
);

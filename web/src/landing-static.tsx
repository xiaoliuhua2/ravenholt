import React from "react";
import ReactDOM, { hydrateRoot } from "react-dom/client";
import "./app/styles/landing-static.css";
import { LandingContent } from "./features/landing/LandingContent";
import { landingPrimaryAction } from "./features/landing/landingConfig";
import { ThemeProvider } from "./shared/theme/ThemeProvider";
import ravenholtLogo from "./assets/ravenholt-logo.svg";

const rootElement = document.getElementById("root") as HTMLElement;
const landing = (
  <React.StrictMode>
    <ThemeProvider>
      <LandingContent logoSrc={ravenholtLogo} primaryAction={landingPrimaryAction} />
    </ThemeProvider>
  </React.StrictMode>
);

if (rootElement.hasChildNodes()) {
  hydrateRoot(rootElement, landing);
} else {
  ReactDOM.createRoot(rootElement).render(landing);
}

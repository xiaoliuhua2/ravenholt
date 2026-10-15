import { renderToString } from "react-dom/server";
import { LandingContent } from "./features/landing/LandingContent";
import { landingPrimaryAction } from "./features/landing/landingConfig";
import { ThemeProvider } from "./shared/theme/ThemeProvider";

export function renderLandingHtml(logoSrc: string) {
  return renderToString(
    <ThemeProvider>
      <LandingContent logoSrc={logoSrc} primaryAction={landingPrimaryAction} />
    </ThemeProvider>,
  );
}

import mermaid from "mermaid";
import { memo, useEffect, useId, useMemo, useState } from "react";

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
  theme: "base",
  suppressErrorRendering: true,
  themeVariables: {
    primaryColor: "#eef2f7",
    primaryTextColor: "#10141d",
    primaryBorderColor: "#cbd2dd",
    lineColor: "#8b93a3",
    secondaryColor: "#f3f5f8",
    tertiaryColor: "#ffffff",
    noteBkgColor: "#fff7e6",
    noteTextColor: "#10141d",
  },
});

export const MermaidDiagram = memo(function MermaidDiagram({ source }: { source: string }) {
  const reactId = useId();
  const renderId = useMemo(() => `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`, [reactId]);
  const [result, setResult] = useState<{ svg: string } | { error: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setResult(null);

    mermaid
      .render(renderId, source)
      .then(({ svg }) => {
        if (!cancelled) setResult({ svg });
      })
      .catch((error: unknown) => {
        if (!cancelled) setResult({ error: error instanceof Error ? error.message : String(error) });
      });

    return () => {
      cancelled = true;
    };
  }, [renderId, source]);

  if (result && "error" in result) {
    return (
      <div className="mermaid-diagram mermaid-diagram-error" title={result.error}>
        <div className="mermaid-error-label">Mermaid 渲染失败</div>
        <pre>
          <code className="language-mermaid">{source}</code>
        </pre>
      </div>
    );
  }

  return (
    <div
      className="mermaid-diagram"
      aria-busy={!result}
      aria-label="Mermaid 图"
      dangerouslySetInnerHTML={result && "svg" in result ? { __html: result.svg } : undefined}
    />
  );
});

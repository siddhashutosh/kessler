// Embeds the n8n-style flow diagram (documents/diagrams KSL-DIA-001, served
// from /diagrams/pipeline-flow.html) and feeds it live agent status (FR-UI-3).
import { useEffect, useRef } from "react";
import { api } from "../api/client";
import type { PipelineStatus } from "../types";

export default function PipelinePage() {
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    let cancelled = false;

    const push = async () => {
      try {
        const status = await api.get<PipelineStatus>("/api/v1/pipeline/status");
        if (cancelled) return;
        frameRef.current?.contentWindow?.postMessage(
          {
            type: "kessler:pipeline",
            agents: status.agents.map((a) => ({
              id: a.id,
              status: a.status,
              detail:
                a.status === "ok" && a.items
                  ? `ok · ${a.items} items`
                  : a.error
                    ? a.status
                    : a.status,
            })),
          },
          "*",
        );
      } catch {
        // backend offline — diagram falls back to its standalone animation
      }
    };

    const id = setInterval(push, 5000);
    const t = setTimeout(push, 1200); // after iframe load
    return () => {
      cancelled = true;
      clearInterval(id);
      clearTimeout(t);
    };
  }, []);

  return (
    <div className="pipeline-page">
      <iframe
        ref={frameRef}
        className="pipeline-frame"
        src="/diagrams/pipeline-flow.html"
        title="KESSLER agent pipeline"
      />
    </div>
  );
}

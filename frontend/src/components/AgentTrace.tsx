import { useEffect, useRef } from "react";
import type { AgentStep } from "../types";
import { Icon, type IconName } from "./Icon";

const kindMeta: Record<AgentStep["kind"], { label: string; icon: IconName }> = {
  reasoning: { label: "Reasoning", icon: "brain" },
  tool_call: { label: "Tool call", icon: "tool" },
  tool_result: { label: "Result", icon: "result" },
  guardrail: { label: "Guardrail", icon: "shield" },
  error: { label: "Error", icon: "alert" },
};

export function AgentTrace({ steps, live, refName }: { steps: AgentStep[]; live: boolean; refName?: string }) {
  const end = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (live) end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [steps.length, live]);

  if (!refName) {
    return (
      <div className="pane-empty">
        <div className="empty-art"><Icon name="brain" size={30} /></div>
        <h3>No line selected</h3>
        <p>Select a line to follow the agent step by step: searches, comparisons and guardrail checks.</p>
      </div>
    );
  }

  if (steps.length === 0) {
    return (
      <div className="pane-empty">
        <div className="empty-art">{live ? <span className="spinner dark" /> : <Icon name="clock" size={30} />}</div>
        <h3>{live ? "Waiting for the first step…" : "No steps yet"}</h3>
        <p>{live ? "Steps appear here as the agent streams them." : `Run the analysis to see how ${refName} gets its verdict.`}</p>
      </div>
    );
  }

  return (
    <div className="trace">
      <header className="trace-head">
        <span>{steps.length} step{steps.length === 1 ? "" : "s"} for <strong>{refName}</strong></span>
        {live ? <span className="live-pill"><span className="pulse" />Streaming</span> : <span className="chip subtle"><Icon name="check" size={13} strokeWidth={2.6} />Complete</span>}
      </header>
      <ol className="timeline">
        {steps.map((step, i) => {
          const meta = kindMeta[step.kind];
          const hasArgs = step.arguments && Object.keys(step.arguments).length > 0;
          return (
            <li key={`${step.step}-${step.kind}-${i}`} className={`tl-item ${step.kind}`}>
              <span className="tl-icon"><Icon name={meta.icon} size={15} /></span>
              <div className="tl-body">
                <div className="tl-top">
                  <span className="tl-kind">{meta.label}</span>
                  {step.tool && <code className="tool">{step.tool}</code>}
                  <span className="tl-step">#{step.step}</span>
                </div>
                {step.text && <p className={step.kind === "reasoning" ? "reasoning-text" : ""}>{step.text}</p>}
                {step.summary && <p className="tl-summary">{step.summary}</p>}
                {hasArgs && (
                  <details className="args">
                    <summary>Arguments</summary>
                    <pre>{JSON.stringify(step.arguments, null, 2)}</pre>
                  </details>
                )}
              </div>
            </li>
          );
        })}
        {live && <li ref={end} className="tl-item tail"><span className="tl-icon"><span className="spinner sm dark" /></span><div className="tl-body"><p className="quiet">Working…</p></div></li>}
        {!live && <li ref={end} className="tl-end" aria-hidden="true" />}
      </ol>
    </div>
  );
}

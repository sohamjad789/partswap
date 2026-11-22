import { percent, titleCase } from "../format";
import type { EvalResults } from "../types";
import { Icon } from "./Icon";

const approachLabel: Record<string, string> = {
  naive_baseline: "Basic cross-reference",
  partswap_rules: "PartSwap rules",
  partswap_bolt: "PartSwap + Nemotron Bolt",
  partswap_super: "PartSwap + Nemotron Super",
};

/** An arm with more fallbacks than this is not described as the model's accuracy (PLAN.md Phase 7). */
const MAX_FALLBACKS = 4;

function formatLatency(ms: number): string {
  if (ms < 1) return "<1 ms";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function EvalPanel({ results }: { results?: EvalResults }) {
  const approaches = results?.approaches ?? [];
  if (!results || results.ready === false || approaches.length === 0) {
    return (
      <section className="card eval">
        <header className="card-head"><div><h2>Evaluation</h2><p className="sub">How PartSwap compares with a basic cross-reference</p></div></header>
        <div className="eval-empty"><Icon name="clock" size={20} /><span>Evaluation not generated yet.</span></div>
      </section>
    );
  }

  const naive = approaches.find(a => a.name === "naive_baseline");
  const best = approaches.find(a => a.name === "partswap_super") ?? approaches.find(a => a.name === "partswap_rules");
  const dangerous = results.dangerous_count;
  const headline = naive && best && dangerous != null
    ? `A basic cross-reference approved ${naive.false_drop_in_count} of ${dangerous} dangerous swaps. PartSwap approved ${best.false_drop_in_count}.`
    : undefined;

  return (
    <section className="card eval">
      <header className="card-head">
        <div><h2>Evaluation</h2><p className="sub">{results.pair_count != null ? `${results.pair_count} labelled swap pairs` : "Labelled swap pairs"}{results.prompt_version ? ` · prompt ${results.prompt_version}` : ""}</p></div>
        {headline && <p className="eval-headline"><Icon name="shield" size={16} />{headline}</p>}
      </header>
      <div className="table-wrap">
        <table className="rtable static">
          <thead>
            <tr>
              <th>Approach</th><th>Accuracy</th>
              <th title="Dangerous pairs whose final verdict was drop-in">Unsafe</th>
              <th title="Dangerous pairs the model itself called drop-in, before the deterministic guardrail">Model only</th>
              <th title="Decisions the guardrail made stricter">Tightened</th>
              <th title="Pairs where the model failed and the rules decided">Fallbacks</th>
              <th title="Median time per pair">Median</th>
            </tr>
          </thead>
          <tbody>
            {approaches.map(row => {
              const mostlyFallback = (row.fallback_count ?? 0) > MAX_FALLBACKS;
              return (
                <tr key={row.name} className={row.name === best?.name ? "best" : ""}>
                  <td>
                    <strong>{approachLabel[row.name] ?? titleCase(row.name)}</strong>
                    {mostlyFallback && <small className="fallback-note">Mostly rule fallbacks, not model accuracy</small>}
                  </td>
                  <td><span className="meter"><span className="meter-bar"><span style={{ width: percent(row.accuracy) }} /></span>{percent(row.accuracy)}</span></td>
                  <td><span className={row.false_drop_in_count > 0 ? "num-bad" : "num-good"}>{row.false_drop_in_count}</span></td>
                  <td>{row.model_false_drop_in_count ?? "—"}</td>
                  <td>{row.tightened_count ?? "—"}</td>
                  <td className={mostlyFallback ? "num-bad" : ""}>{row.fallback_count ?? "—"}</td>
                  <td>{formatLatency(row.median_latency_ms)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

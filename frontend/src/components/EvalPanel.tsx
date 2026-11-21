import { percent, titleCase } from "../format";
import type { EvalResults } from "../types";
import { Icon } from "./Icon";

const approachLabel: Record<string, string> = {
  naive_baseline: "Basic cross-reference",
  partswap_rules: "PartSwap rules",
  partswap_bolt: "PartSwap + Nemotron Bolt",
  partswap_super: "PartSwap + Nemotron Super",
};

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
      </header>
      {headline && <p className="eval-headline"><Icon name="shield" size={20} />{headline}</p>}
      <div className="metrics">
        {naive && dangerous != null && (
          <div className="metric bad"><span className="metric-label">Unsafe approvals · baseline</span><span className="metric-num">{naive.false_drop_in_count}<small>/ {dangerous}</small></span></div>
        )}
        {best && dangerous != null && (
          <div className="metric good"><span className="metric-label">Unsafe approvals · PartSwap</span><span className="metric-num">{best.false_drop_in_count}<small>/ {dangerous}</small></span></div>
        )}
        {best && <div className="metric"><span className="metric-label">Accuracy · {approachLabel[best.name] ?? titleCase(best.name)}</span><span className="metric-num">{percent(best.accuracy)}</span></div>}
      </div>
      <div className="table-wrap">
        <table className="rtable static">
          <thead><tr><th>Approach</th><th>Accuracy</th><th>Unsafe approvals</th><th>Tightened</th><th>Fallbacks</th><th>Median latency</th></tr></thead>
          <tbody>
            {approaches.map(row => (
              <tr key={row.name} className={row.name === best?.name ? "best" : ""}>
                <td><strong>{approachLabel[row.name] ?? titleCase(row.name)}</strong></td>
                <td><span className="meter"><span className="meter-bar"><span style={{ width: percent(row.accuracy) }} /></span>{percent(row.accuracy)}</span></td>
                <td><span className={row.false_drop_in_count > 0 ? "num-bad" : "num-good"}>{row.false_drop_in_count}</span></td>
                <td>{row.tightened_count ?? "—"}</td>
                <td>{row.fallback_count ?? "—"}</td>
                <td>{Math.round(row.median_latency_ms)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

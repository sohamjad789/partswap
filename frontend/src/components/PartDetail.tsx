import { useEffect, useState } from "react";
import { datasheetUrl, fetchExtraction, fetchPart } from "../api";
import { percent, resultLabel, specName, titleCase, valueText, verdictHint, verdictLabel } from "../format";
import type { BomLine, Check, CheckResult, CheckValue, Decision, Extraction } from "../types";
import { Icon, type IconName } from "./Icon";
import { VerdictBadge } from "./ResultsTable";

const datasheetCache = new Map<string, Promise<boolean>>();
function hasDatasheet(mpn: string): Promise<boolean> {
  if (!datasheetCache.has(mpn)) datasheetCache.set(mpn, fetchPart(mpn).then(part => Boolean(part.datasheet_available)).catch(() => false));
  return datasheetCache.get(mpn)!;
}

const resultIcon: Record<CheckResult, IconName> = { pass: "check", fail: "x", caveat: "alert", unknown: "question", skip: "info" };

function ResultPill({ result }: { result: CheckResult }) {
  return <span className={`rpill ${result}`}><Icon name={resultIcon[result]} size={13} strokeWidth={2.6} />{resultLabel[result]}</span>;
}

function Value({ side, mpn, linkable }: { side?: CheckValue | null; mpn?: string | null; linkable: boolean }) {
  return (
    <>
      <span className="val">{valueText(side)}</span>
      {(side?.condition || side?.page) && (
        <small className="cond">
          {side?.condition}
          {side?.page != null && (linkable && mpn
            ? <a className="page-link" href={datasheetUrl(mpn, side.page)} target="_blank" rel="noreferrer" onClick={event => event.stopPropagation()}>p.{side.page}<Icon name="link" size={11} /></a>
            : <span className="page-ref">p.{side.page}</span>)}
        </small>
      )}
    </>
  );
}

function SpecTable({ decision, links }: { decision: Decision; links: Record<string, boolean> }) {
  const [diffOnly, setDiffOnly] = useState(false);
  const checks = decision.spec_checks.filter(check => check.result !== "skip");
  const flagged = checks.filter(check => check.result !== "pass");
  const rows: Check[] = diffOnly ? flagged : checks;
  const passCount = checks.length - flagged.length;
  return (
    <section className="dsec">
      <header className="dsec-head">
        <h3><Icon name="layers" size={17} />Spec comparison</h3>
        <label className="toggle">
          <input type="checkbox" checked={diffOnly} onChange={event => setDiffOnly(event.target.checked)} />
          <span className="track"><span /></span>Only issues
        </label>
      </header>
      <p className="dsec-sub">
        <span className="rpill pass"><Icon name="check" size={13} strokeWidth={2.6} />{passCount} pass</span>
        {flagged.length > 0 && <span className="rpill caveat"><Icon name="alert" size={13} strokeWidth={2.6} />{flagged.length} flagged</span>}
      </p>
      {rows.length === 0 ? (
        <p className="quiet">{checks.length === 0 ? "No spec checks for this line." : "Every spec passes. Nothing to flag."}</p>
      ) : (
        <div className="diff">
          <div className="diff-head">
            <span><span className="side-tag">Original</span><span className="mpn">{decision.original_mpn}</span></span>
            <span><span className="side-tag cand">Candidate</span><span className="mpn">{decision.compared_mpn ?? "—"}</span></span>
          </div>
          {rows.map((check, i) => (
            <div key={check.spec} className={`diff-row ${check.result}`} style={{ ["--i" as string]: i }}>
              <div className="diff-spec">
                <div>
                  <span className="spec-name">{specName(check.spec)}</span>
                  {check.requirement && <small className="req">Requirement: {check.requirement}</small>}
                </div>
                <ResultPill result={check.result} />
              </div>
              <div className="diff-cols">
                <div className="diff-cell"><Value side={check.original} mpn={decision.original_mpn} linkable={links[decision.original_mpn] ?? false} /></div>
                <div className="diff-cell cand"><Value side={check.candidate} mpn={decision.compared_mpn} linkable={decision.compared_mpn ? links[decision.compared_mpn] ?? false : false} /></div>
              </div>
              {check.result !== "pass" && check.reason && <p className="diff-reason"><Icon name={resultIcon[check.result]} size={14} strokeWidth={2.4} />{check.reason}</p>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ExtractionCheck({ mpn }: { mpn?: string | null }) {
  const [data, setData] = useState<Extraction>();
  useEffect(() => {
    setData(undefined);
    if (mpn) void fetchExtraction(mpn).then(setData).catch(() => undefined);
  }, [mpn]);
  if (!data?.available || !data.fields?.length) return null;
  return (
    <section className="dsec">
      <header className="dsec-head"><h3><Icon name="sparkle" size={17} />Extracted by Nemotron vs. human-verified</h3>{data.parser && <span className="chip subtle">{data.parser}</span>}</header>
      <div className="table-wrap">
        <table className="spec-table">
          <thead><tr><th>Field</th><th>Verified</th><th>Extracted</th><th>Status</th></tr></thead>
          <tbody>
            {data.fields.map(field => (
              <tr key={field.key} className={field.status === "match" ? "pass" : field.status === "mismatch" ? "fail" : "unknown"}>
                <td><span className="spec-name">{specName(field.key)}</span></td>
                <td>{field.verified_raw ?? "—"}</td>
                <td>{field.extracted_raw ?? "—"}</td>
                <td><span className={`rpill ${field.status === "match" ? "pass" : field.status === "mismatch" ? "fail" : "unknown"}`}>{titleCase(field.status)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

interface Props {
  decision?: Decision;
  line?: BomLine;
  pending: boolean;
  liveRunning: boolean;
  hasKey: boolean;
  onLive: () => void;
}

export function PartDetail({ decision, line, pending, liveRunning, hasKey, onLive }: Props) {
  const [links, setLinks] = useState<Record<string, boolean>>({});
  useEffect(() => {
    const mpns = [decision?.original_mpn, decision?.compared_mpn].filter((m): m is string => Boolean(m));
    let alive = true;
    void Promise.all(mpns.map(async mpn => [mpn, await hasDatasheet(mpn)] as const)).then(entries => { if (alive) setLinks(Object.fromEntries(entries)); });
    return () => { alive = false; };
  }, [decision?.original_mpn, decision?.compared_mpn]);

  if (!line) {
    return (
      <div className="pane-empty">
        <div className="empty-art"><Icon name="search" size={30} /></div>
        <h3>Nothing selected</h3>
        <p>Pick a line in the results to see the spec comparison, rejected candidates and the reasoning behind its verdict.</p>
      </div>
    );
  }

  if (!decision) {
    return (
      <div className="detail">
        <p className="eyebrow">{line.ref}{line.description ? ` · ${line.description}` : ""}</p>
        <div className="fix">
          <div className="fix-part"><span className="fix-label">Original</span><span className="mpn">{line.mpn}</span><small>{line.manufacturer}</small></div>
          <span className="fix-arrow"><Icon name="arrow" size={20} /></span>
          <div className="fix-part ghost"><span className="fix-label">Recommended</span><span className="skeleton" /><span className="skeleton short" /></div>
        </div>
        <div className="callout neutral">{pending ? <><span className="spinner sm" />The agent is working on this line. Watch the Agent tab for live steps.</> : <><Icon name="info" size={18} />Run the analysis to get a verdict for this line.</>}</div>
      </div>
    );
  }

  const rejectedTraps = decision.rejected.filter(r => r.headline_match).length;

  return (
    <div className="detail" key={decision.ref}>
      <p className="eyebrow">{decision.ref}{line.description ? ` · ${line.description}` : ""}</p>

      <div className={`fix v-${decision.verdict}`}>
        <div className="fix-part"><span className="fix-label">Original</span><span className="mpn">{decision.original_mpn}</span><small>{decision.original_manufacturer}</small></div>
        <span className="fix-arrow"><Icon name="arrow" size={20} /></span>
        <div className="fix-part rec">
          <span className="fix-label">Recommended</span>
          {decision.recommended_mpn ? <><span className="mpn">{decision.recommended_mpn}</span><small>{decision.recommended_manufacturer}</small></> : <span className="mpn muted">No safe match</span>}
        </div>
      </div>

      <div className="verdict-row">
        <VerdictBadge verdict={decision.verdict} large />
        <span className="verdict-hint">{verdictHint[decision.verdict]}</span>
      </div>

      <div className="meta-row">
        {decision.confidence != null && <span className="meta"><Icon name="bolt" size={15} />Confidence <strong>{percent(decision.confidence)}</strong></span>}
        <span className="meta"><Icon name="brain" size={15} />{decision.source === "model" ? "Model" : decision.source === "deterministic_fallback" ? "Rules (fallback)" : "Rules"}</span>
        <span className="meta"><Icon name="layers" size={15} />{decision.candidates_considered.length} candidate{decision.candidates_considered.length === 1 ? "" : "s"} checked</span>
      </div>

      <section className="why">
        <h3>Why this verdict</h3>
        <p>{decision.explanation}</p>
      </section>

      {decision.tightened && (
        <div className="callout warn">
          <Icon name="shield" size={18} />
          <div><strong>Tightened by deterministic check</strong><p>The model asked for <em>{decision.model_verdict ? verdictLabel[decision.model_verdict] : "a looser verdict"}</em>; the Python guardrail made it stricter. Confidence is capped at 60%.</p></div>
        </div>
      )}

      {decision.package_pinout && (
        <section className="dsec">
          <header className="dsec-head"><h3><Icon name="package" size={17} />Package & pinout</h3></header>
          <div className="pp">
            <span className="pp-item">Package <ResultPill result={decision.package_pinout.package_result} /></span>
            <span className="pp-item">Pinout <ResultPill result={decision.package_pinout.pinout_result} /></span>
          </div>
          <p className="quiet">{decision.package_pinout.detail}</p>
        </section>
      )}

      <SpecTable decision={decision} links={links} />

      {decision.caveats.length > 0 && (
        <section className="dsec">
          <header className="dsec-head"><h3><Icon name="alert" size={17} />Caveats</h3></header>
          <ul className="caveats">
            {decision.caveats.map(caveat => {
              const match = caveat.match(/^([a-z0-9_]+):\s*(.+)$/);
              return <li key={caveat}><Icon name="alert" size={16} /><span>{match ? <><strong>{specName(match[1])}:</strong> {match[2]}</> : caveat}</span></li>;
            })}
          </ul>
        </section>
      )}

      {decision.rejected.length > 0 && (
        <section className="dsec">
          <header className="dsec-head">
            <h3><Icon name="shield" size={17} />Rejected candidates</h3>
            {rejectedTraps > 0 && <span className="chip trap">{rejectedTraps} trap{rejectedTraps === 1 ? "" : "s"} caught</span>}
          </header>
          <div className="rejects">
            {decision.rejected.map((candidate, i) => {
              const [spec, ...rest] = candidate.reason.split(": ");
              const reason = rest.length ? rest.join(": ") : candidate.reason;
              return (
                <article key={candidate.mpn} className={`reject${candidate.headline_match ? " is-trap" : ""}`} style={{ ["--i" as string]: i }}>
                  <div className="reject-top">
                    <span className="mpn struck">{candidate.mpn}</span>
                    <VerdictBadge verdict={candidate.verdict} />
                  </div>
                  <small className="reject-maker">{candidate.manufacturer}</small>
                  <p className="reject-reason">{rest.length > 0 && <strong>{specName(spec)}: </strong>}{reason}</p>
                  {candidate.headline_match && <p className="trap-note"><Icon name="alert" size={15} />A basic cross-reference would approve this</p>}
                </article>
              );
            })}
          </div>
        </section>
      )}

      <ExtractionCheck mpn={decision.compared_mpn} />

      <footer className="detail-foot">
        <button type="button" className="btn secondary" disabled={liveRunning} onClick={onLive} title={hasKey ? "Re-run this line with Nemotron" : "No API key: the backend will fall back to deterministic rules"}>
          {liveRunning ? <><span className="spinner sm dark" />Running live…</> : <><Icon name="bolt" size={16} />Run live on this line</>}
        </button>
        {!hasKey && <span className="quiet small">No API key set, so this falls back to rules.</span>}
      </footer>
    </div>
  );
}

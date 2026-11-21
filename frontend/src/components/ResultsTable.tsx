import { useEffect, useRef, useState } from "react";
import { percent, trapCount, verdictLabel } from "../format";
import type { BomLine, Decision, Verdict } from "../types";
import { Icon } from "./Icon";

interface Props {
  lines: BomLine[];
  decisions: Record<string, Decision>;
  selectedRef?: string;
  activeRef?: string;
  running: boolean;
  filter?: Verdict;
  query: string;
  exportUrl: (kind: "bom.csv" | "risk.md") => string | undefined;
  onQuery: (query: string) => void;
  onClearFilter: () => void;
  onSelect: (ref: string) => void;
  onDemo: () => void;
}

export function VerdictBadge({ verdict, large }: { verdict: Verdict; large?: boolean }) {
  return <span className={`badge ${verdict}${large ? " lg" : ""}`}>{verdictLabel[verdict]}</span>;
}

function ExportMenu({ exportUrl }: { exportUrl: Props["exportUrl"] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const ready = Boolean(exportUrl("bom.csv"));
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const esc = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="menu" ref={root}>
      <button type="button" className="btn secondary" disabled={!ready} onClick={() => setOpen(!open)} aria-expanded={open} title={ready ? "Download results" : "Available when a run completes"}>
        <Icon name="download" size={16} />Export<Icon name="chevron" size={14} className={`chev${open ? " up" : ""}`} />
      </button>
      {open && ready && (
        <div className="menu-pop" role="menu">
          <a role="menuitem" href={exportUrl("bom.csv")} onClick={() => setOpen(false)}>
            <Icon name="file" size={18} /><span><strong>New BOM</strong><small>CSV with recommended parts</small></span>
          </a>
          <a role="menuitem" href={exportUrl("risk.md")} onClick={() => setOpen(false)}>
            <Icon name="shield" size={18} /><span><strong>Risk report</strong><small>Markdown, one section per line</small></span>
          </a>
        </div>
      )}
    </div>
  );
}

export function ResultsTable({ lines, decisions, selectedRef, activeRef, running, filter, query, exportUrl, onQuery, onClearFilter, onSelect, onDemo }: Props) {
  const q = query.trim().toLowerCase();
  const visible = lines.filter(line => {
    const d = decisions[line.ref];
    if (filter && d?.verdict !== filter) return false;
    if (!q) return true;
    return [line.ref, line.mpn, line.manufacturer, line.description, d?.recommended_mpn, d?.recommended_manufacturer].some(v => v && String(v).toLowerCase().includes(q));
  });
  const done = lines.filter(line => decisions[line.ref]).length;

  const selectedRow = useRef<HTMLTableRowElement>(null);
  useEffect(() => { selectedRow.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [selectedRef]);

  return (
    <section className="card results">
      <header className="card-head">
        <div>
          <h2>Replacement analysis</h2>
          <p className="sub">{lines.length ? `${done} of ${lines.length} lines analyzed` : "No BOM loaded"}</p>
        </div>
        <div className="head-actions">
          <label className="search">
            <Icon name="search" size={16} />
            <input placeholder="Search parts…" value={query} onChange={event => onQuery(event.target.value)} aria-label="Search parts" />
          </label>
          <ExportMenu exportUrl={exportUrl} />
        </div>
      </header>

      {lines.length > 0 && <div className="progress" aria-hidden="true"><span style={{ width: `${(done / lines.length) * 100}%` }} className={running ? "live" : ""} /></div>}

      {filter && (
        <div className="filter-row">
          <span className="chip">Showing <strong>{verdictLabel[filter]}</strong><button type="button" onClick={onClearFilter} aria-label="Clear filter"><Icon name="x" size={14} /></button></span>
        </div>
      )}

      {lines.length === 0 ? (
        <div className="empty-state">
          <div className="empty-art"><Icon name="chip" size={34} /></div>
          <h3>Check your BOM for safe swaps</h3>
          <p>Upload a BOM CSV or load the demo board, set the design context, then run. Each line gets one verdict, backed by the datasheet.</p>
          <button type="button" className="btn primary" onClick={onDemo}><Icon name="sparkle" size={16} />Load demo BOM</button>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="rtable">
            <thead>
              <tr><th>Ref</th><th>Original</th><th aria-label="replaced by" /><th>Recommended</th><th>Verdict</th><th>Confidence</th><th>Traps</th></tr>
            </thead>
            <tbody>
              {visible.map((line, i) => {
                const d = decisions[line.ref];
                const traps = trapCount(d);
                const selected = selectedRef === line.ref;
                return (
                  <tr
                    key={line.ref}
                    ref={selected ? selectedRow : undefined}
                    className={`row${selected ? " selected" : ""}${d ? " ready" : " pending"}`}
                    style={{ ["--i" as string]: i }}
                    onClick={() => onSelect(line.ref)}
                    tabIndex={0}
                    onKeyDown={event => event.key === "Enter" && onSelect(line.ref)}
                    aria-selected={selected}
                  >
                    <td><span className="ref">{line.ref}</span></td>
                    <td><span className="mpn">{line.mpn}</span><small>{line.manufacturer}</small></td>
                    <td className="arrow-cell"><Icon name="arrow" size={16} /></td>
                    <td>
                      {d ? (
                        d.recommended_mpn ? <><span className="mpn">{d.recommended_mpn}</span><small>{d.recommended_manufacturer}</small></> : <span className="muted">No safe match</span>
                      ) : activeRef === line.ref && running ? (
                        <span className="analyzing"><span className="spinner sm" />Analyzing…</span>
                      ) : (
                        <span className="skeleton" />
                      )}
                    </td>
                    <td>{d ? <VerdictBadge verdict={d.verdict} /> : <span className="skeleton short" />}</td>
                    <td>
                      {d?.confidence == null ? <span className="muted">—</span> : (
                        <span className="meter" title={percent(d.confidence)}><span className="meter-bar"><span style={{ width: percent(d.confidence) }} /></span>{percent(d.confidence)}</span>
                      )}
                    </td>
                    <td>{traps ? <span className="trap-tag"><Icon name="shield" size={14} />{traps} rejected</span> : <span className="muted">—</span>}</td>
                  </tr>
                );
              })}
              {visible.length === 0 && (
                <tr><td colSpan={7} className="no-rows">No lines match {filter ? `"${verdictLabel[filter]}"` : ""}{filter && q ? " and " : ""}{q ? `"${query}"` : ""}.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

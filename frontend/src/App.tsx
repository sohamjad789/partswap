import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, fetchDemoBom, fetchEval, getHealth, parseBom, streamRun } from "./api";
import { AgentTrace } from "./components/AgentTrace";
import { BomForm } from "./components/BomForm";
import { EvalPanel } from "./components/EvalPanel";
import { Icon } from "./components/Icon";
import { PartDetail } from "./components/PartDetail";
import { ResultsTable } from "./components/ResultsTable";
import { SummaryStrip } from "./components/SummaryStrip";
import { Toasts, useToasts } from "./components/Toasts";
import { VERDICTS, modeInfo, trapCount } from "./format";
import type { AgentStep, BomLine, Decision, DesignContext, EvalResults, Health, Mode, RunEvent, Verdict } from "./types";

const defaults: DesignContext = { input_voltage_v: 24, input_voltage_max_v: 32, operating_temp_min_c: -40, operating_temp_max_c: 85, preferred_manufacturer: "Diodes Incorporated", goal: "lowest_risk" };
type Tab = "detail" | "agent";

const messages = (error: unknown, fallback: string) =>
  error instanceof ApiError && error.details.length ? error.details : [error instanceof Error ? error.message : fallback];

export default function App() {
  const [health, setHealth] = useState<Health>();
  const [offline, setOffline] = useState(false);
  const [context, setContext] = useState<DesignContext>(defaults);
  const [mode, setMode] = useState<Mode>("fixture");
  const [lines, setLines] = useState<BomLine[]>([]);
  const [bomName, setBomName] = useState<string>();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [steps, setSteps] = useState<Record<string, AgentStep[]>>({});
  const [selectedRef, setSelectedRef] = useState<string>();
  const [activeRef, setActiveRef] = useState<string>();
  const [liveRef, setLiveRef] = useState<string>();
  const [runId, setRunId] = useState<string>();
  const [running, setRunning] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("detail");
  const [wide, setWide] = useState(false);
  const [filter, setFilter] = useState<Verdict>();
  const [query, setQuery] = useState("");
  const [evalResults, setEvalResults] = useState<EvalResults>();
  const [lastRun, setLastRun] = useState<{ ms: number; count: number }>();
  const { toasts, push, dismiss } = useToasts();

  useEffect(() => {
    void getHealth()
      .then(result => { setHealth(result); setMode(result.mode_default); })
      .catch(() => setOffline(true));
    void fetchEval().then(setEvalResults).catch(() => undefined);
  }, []);

  const busy = running || Boolean(liveRef);
  const selected = selectedRef ? decisions[selectedRef] : undefined;
  const selectedLine = useMemo(() => lines.find(line => line.ref === selectedRef), [lines, selectedRef]);
  const counts = useMemo(() => {
    const result = Object.fromEntries(VERDICTS.map(v => [v, 0])) as Record<Verdict, number>;
    Object.values(decisions).forEach(d => { result[d.verdict] += 1; });
    return result;
  }, [decisions]);
  const traps = useMemo(() => Object.values(decisions).reduce((sum, d) => sum + trapCount(d), 0), [decisions]);
  const done = lines.filter(line => decisions[line.ref]).length;

  const loadCsv = async (name: string, csv: string) => {
    try {
      const parsed = await parseBom(csv);
      setLines(parsed.lines);
      setBomName(name);
      setDecisions({});
      setSteps({});
      setRunId(undefined);
      setLastRun(undefined);
      setFilter(undefined);
      setSelectedRef(parsed.lines[0]?.ref);
      setErrors([]);
      push({ tone: "success", title: "BOM loaded", body: `${parsed.lines.length} line${parsed.lines.length === 1 ? "" : "s"} from ${name}` });
    } catch (error) {
      setErrors(messages(error, "Could not parse BOM"));
    }
  };

  const loadDemo = async () => {
    try {
      const demo = await fetchDemoBom();
      setContext(demo.design_context);
      await loadCsv("demo_bom.csv", demo.csv);
    } catch (error) {
      setErrors(messages(error, "Could not load demo BOM"));
    }
  };

  const receive = (single: boolean) => (event: RunEvent) => {
    switch (event.event) {
      case "run_started":
        if (!single) setRunId(event.data.run_id);
        break;
      case "part_started":
        setActiveRef(event.data.ref);
        break;
      case "agent_step":
        setSteps(old => ({ ...old, [event.data.ref]: [...(old[event.data.ref] ?? []), event.data] }));
        break;
      case "part_decision":
        setDecisions(old => ({ ...old, [event.data.ref]: event.data }));
        setSelectedRef(current => current ?? event.data.ref);
        break;
      case "part_error":
        push({ tone: "info", title: `${event.data.ref}: fell back to rules`, body: event.data.message });
        break;
      case "error":
        setErrors(old => [...old, event.data.message]);
        push({ tone: "error", title: "Run error", body: event.data.message });
        break;
      case "run_completed":
        if (!single) {
          setRunning(false);
          setLastRun(prev => ({ ms: event.data.elapsed_ms, count: prev?.count ?? 0 }));
        }
        break;
    }
  };

  const run = async (onlyLine?: BomLine) => {
    if (busy) return;
    if (!lines.length) { setErrors(["Load or upload a BOM first."]); return; }
    setErrors([]);
    if (onlyLine) {
      setLiveRef(onlyLine.ref);
      setSteps(old => ({ ...old, [onlyLine.ref]: [] }));
    } else {
      setRunning(true);
      setDecisions({});
      setSteps({});
      setRunId(undefined);
      setLastRun({ ms: 0, count: lines.length });
    }
    const started = performance.now();
    try {
      await streamRun({ lines: onlyLine ? [onlyLine] : lines, design_context: context, mode: onlyLine ? "live" : mode }, receive(Boolean(onlyLine)));
      const seconds = ((performance.now() - started) / 1000).toFixed(1);
      push({ tone: "success", title: onlyLine ? `${onlyLine.ref} re-run complete` : "Analysis complete", body: onlyLine ? undefined : `${lines.length} line${lines.length === 1 ? "" : "s"} in ${seconds}s` });
    } catch (error) {
      const list = messages(error, "Run failed");
      setErrors(list);
      push({ tone: "error", title: "Run failed", body: list[0] });
    } finally {
      if (onlyLine) setLiveRef(undefined);
      else setRunning(false);
      setActiveRef(undefined);
    }
  };

  // Keyboard: Ctrl/Cmd+Enter runs; arrow keys move the selection when not typing.
  const latest = useRef({ run, lines, selectedRef });
  latest.current = { run, lines, selectedRef };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const { run: doRun, lines: all, selectedRef: current } = latest.current;
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void doRun(); return; }
      const target = event.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName) || !all.length) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const index = all.findIndex(line => line.ref === current);
        const next = event.key === "ArrowDown" ? Math.min(all.length - 1, index + 1) : Math.max(0, index - 1);
        setSelectedRef(all[next].ref);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const exportUrl = (kind: "bom.csv" | "risk.md") => (runId && !running ? `/api/runs/${encodeURIComponent(runId)}/export/${kind}` : undefined);
  const selectedSteps = selectedRef ? steps[selectedRef] ?? [] : [];
  const selectedLive = (running && activeRef === selectedRef) || liveRef === selectedRef;

  let status: ReactNode;
  if (offline) status = <span className="run-status error"><span className="sdot" />Backend unavailable</span>;
  else if (running) status = <span className="run-status live"><span className="pulse" />Analyzing {Math.min(done + 1, lines.length)} of {lines.length}{activeRef ? ` · ${activeRef}` : ""}</span>;
  else if (liveRef) status = <span className="run-status live"><span className="pulse" />Running {liveRef} live</span>;
  else if (lastRun && done) status = <span className="run-status ok"><Icon name="check" size={14} strokeWidth={2.6} />{done} line{done === 1 ? "" : "s"} analyzed{lastRun.ms ? ` · ${lastRun.ms} ms` : ""}</span>;
  else status = <span className="run-status"><span className="sdot idle" />Ready</span>;

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand">
          <span className="wordmark">PartSwap</span>
          <span className="tagline">: BOM cross-reference intelligence</span>
        </h1>
        <div className="topbar-center">{status}</div>
        <div className="topbar-right">
          <span className="pill mode-pill" title={modeInfo[mode].hint}><Icon name="layers" size={14} />{modeInfo[mode].label}</span>
          <span className={`pill key-pill ${health?.has_api_key ? "on" : "off"}`}>
            <span className="sdot" />{health ? (health.has_api_key ? "Nemotron connected" : "No API key") : offline ? "Offline" : "Checking…"}
          </span>
        </div>
      </header>

      {offline && (
        <div className="banner"><Icon name="alert" size={18} />The backend is not responding. Start FastAPI (see README), then reload this page.</div>
      )}

      <main className={`layout${wide ? " wide" : ""}`}>
        <BomForm
          context={context}
          mode={mode}
          hasKey={Boolean(health?.has_api_key)}
          running={busy}
          errors={errors}
          bomName={bomName}
          lineCount={lines.length}
          onContext={setContext}
          onMode={setMode}
          onFile={(name, csv) => void loadCsv(name, csv)}
          onDemo={() => void loadDemo()}
          onRun={() => void run()}
        />

        <section className="center">
          {lines.length > 0 && <SummaryStrip counts={counts} traps={traps} filter={filter} onFilter={setFilter} />}
          <ResultsTable
            lines={lines}
            decisions={decisions}
            selectedRef={selectedRef}
            activeRef={activeRef}
            running={running}
            filter={filter}
            query={query}
            exportUrl={exportUrl}
            onQuery={setQuery}
            onClearFilter={() => setFilter(undefined)}
            onSelect={setSelectedRef}
            onDemo={() => void loadDemo()}
          />
          <EvalPanel results={evalResults} />
        </section>

        <aside className="pane card" aria-label="Line detail">
          <div className="pane-head">
            <div className="tabs" role="tablist" data-tab={tab}>
              <button role="tab" aria-selected={tab === "detail"} className={tab === "detail" ? "on" : ""} onClick={() => setTab("detail")}><Icon name="layers" size={16} />Detail</button>
              <button role="tab" aria-selected={tab === "agent"} className={tab === "agent" ? "on" : ""} onClick={() => setTab("agent")}>
                <Icon name="brain" size={16} />Agent
                {selectedSteps.length > 0 && <span className={`count${selectedLive ? " live" : ""}`}>{selectedSteps.length}</span>}
              </button>
              <span className="tab-ink" />
            </div>
            <button type="button" className="icon-btn" onClick={() => setWide(!wide)} title={wide ? "Collapse panel" : "Expand panel"} aria-label={wide ? "Collapse panel" : "Expand panel"}>
              <Icon name={wide ? "collapse" : "expand"} size={16} />
            </button>
          </div>
          <div className="pane-body auto-scrollbar" key={`${tab}-${selectedRef ?? "none"}`}>
            {tab === "detail" ? (
              <PartDetail
                decision={selected}
                line={selectedLine}
                pending={selectedLive}
                liveRunning={liveRef === selectedRef && Boolean(liveRef)}
                hasKey={Boolean(health?.has_api_key)}
                onLive={() => selectedLine && void run(selectedLine)}
              />
            ) : (
              <AgentTrace steps={selectedSteps} live={selectedLive} refName={selectedRef} />
            )}
          </div>
        </aside>
      </main>

      <Toasts toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}

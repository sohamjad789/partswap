import { useRef, useState, type ChangeEvent, type DragEvent, type ReactNode } from "react";
import { modeInfo } from "../format";
import type { DesignContext, Goal, Mode } from "../types";
import { Icon } from "./Icon";

interface Props {
  context: DesignContext;
  mode: Mode;
  hasKey: boolean;
  running: boolean;
  errors: string[];
  bomName?: string;
  lineCount: number;
  onContext: (next: DesignContext) => void;
  onMode: (mode: Mode) => void;
  onFile: (name: string, csv: string) => void;
  onDemo: () => void;
  onRun: () => void;
}

const goals: Array<{ value: Goal; label: string }> = [
  { value: "lowest_risk", label: "Risk" },
  { value: "lowest_cost", label: "Cost" },
  { value: "shortest_lead_time", label: "Lead time" },
];
const modes: Mode[] = ["fixture", "deterministic", "cache", "live"];

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="step">
      <header className="step-head">
        <span className="step-num">{n}</span>
        <h2>{title}</h2>
      </header>
      <div className="step-body">{children}</div>
    </section>
  );
}

function NumberField({ label, unit, value, onChange }: { label: string; unit: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <span className="input-wrap">
        <input type="number" inputMode="decimal" value={Number.isFinite(value) ? value : ""} onChange={event => onChange(Number(event.target.value))} />
        <span className="unit">{unit}</span>
      </span>
    </label>
  );
}

export function BomForm({ context, mode, hasKey, running, errors, bomName, lineCount, onContext, onMode, onFile, onDemo, onRun }: Props) {
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const readFile = (file?: File) => {
    if (file) void file.text().then(text => onFile(file.name, text));
  };
  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    readFile(event.target.files?.[0]);
    event.target.value = "";
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    readFile(event.dataTransfer.files?.[0]);
  };
  const set = <K extends keyof DesignContext>(key: K, value: DesignContext[K]) => onContext({ ...context, [key]: value });

  return (
    <aside className="setup card" aria-label="Run setup">
      <div className="setup-scroll">
        <Step n={1} title="Bill of materials">
          <div
            className={`dropzone${dragging ? " dragging" : ""}${lineCount ? " loaded" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => input.current?.click()}
            onKeyDown={event => (event.key === "Enter" || event.key === " ") && input.current?.click()}
            onDragOver={event => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input ref={input} type="file" accept=".csv,text/csv" hidden onChange={onPick} />
            {lineCount ? (
              <>
                <span className="dz-icon ok"><Icon name="file" size={20} /></span>
                <span className="dz-text"><strong>{bomName ?? "BOM"}</strong><span>{lineCount} line{lineCount === 1 ? "" : "s"} ready · click to replace</span></span>
              </>
            ) : (
              <>
                <span className="dz-icon"><Icon name="upload" size={20} /></span>
                <span className="dz-text"><strong>Drop a BOM CSV</strong><span>or click to browse</span></span>
              </>
            )}
          </div>
          <button type="button" className="btn ghost full" onClick={onDemo}><Icon name="sparkle" size={16} />Load demo BOM</button>
          {errors.length > 0 && (
            <div className="callout danger" role="alert">
              <Icon name="alert" size={18} />
              <div><strong>Fix the BOM</strong><ul>{errors.map((error, i) => <li key={i}>{error}</li>)}</ul></div>
            </div>
          )}
        </Step>

        <Step n={2} title="Design context">
          <div className="grid-2">
            <NumberField label="Input voltage" unit="V" value={context.input_voltage_v} onChange={v => set("input_voltage_v", v)} />
            <NumberField label="Input max" unit="V" value={context.input_voltage_max_v} onChange={v => set("input_voltage_max_v", v)} />
            <NumberField label="Temp min" unit="°C" value={context.operating_temp_min_c} onChange={v => set("operating_temp_min_c", v)} />
            <NumberField label="Temp max" unit="°C" value={context.operating_temp_max_c} onChange={v => set("operating_temp_max_c", v)} />
          </div>
          <label className="field">
            <span className="field-label">Preferred manufacturer</span>
            <span className="input-wrap"><input value={context.preferred_manufacturer} onChange={event => set("preferred_manufacturer", event.target.value)} /></span>
          </label>
          <div className="field">
            <span className="field-label">Optimize for</span>
            <div className="segmented" role="radiogroup" aria-label="Goal">
              {goals.map(goal => (
                <button type="button" role="radio" aria-checked={context.goal === goal.value} key={goal.value} className={context.goal === goal.value ? "on" : ""} onClick={() => set("goal", goal.value)}>{goal.label}</button>
              ))}
            </div>
          </div>
        </Step>

        <Step n={3} title="Mode">
          <div className="mode-grid" role="radiogroup" aria-label="Mode">
            {modes.map(item => (
              <button type="button" role="radio" aria-checked={mode === item} key={item} className={`mode-option${mode === item ? " on" : ""}`} onClick={() => onMode(item)}>
                <span className="mode-name">{modeInfo[item].label}{item === "live" && !hasKey && <span className="tag">no key</span>}</span>
              </button>
            ))}
          </div>
          <p className="hint">{modeInfo[mode].hint}</p>
        </Step>
      </div>

      <footer className="setup-foot">
        <button type="button" className="btn primary full lg" disabled={running} onClick={onRun}>
          {running ? <><span className="spinner" />Analyzing…</> : <><Icon name="play" size={15} />Run analysis</>}
        </button>
        <p className="kbd-hint"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> run · <kbd>↑</kbd><kbd>↓</kbd> rows</p>
      </footer>
    </aside>
  );
}

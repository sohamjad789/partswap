import { useState } from "react";
import { proposePowerTree } from "../api";
import { percent } from "../format";
import type { PowerStage, PowerTreeResult, Rail } from "../types";
import { Icon } from "./Icon";

const MAX_RAILS = 3;
const watts = (value?: number | null) => (value == null ? null : value < 1 ? `${Math.round(value * 1000)} mW` : `${value.toFixed(2)} W`);
const dollars = (value?: number | null) => (value == null ? "price not in catalog" : `$${value.toFixed(2)}`);

function StageCell({ stage }: { stage: PowerStage }) {
  if (!stage.mpn) return <><strong className="num-bad">No catalog part</strong><small>{stage.note}</small></>;
  return (
    <>
      <span className="mpn"><strong>{stage.mpn}</strong></span>
      <small>{stage.category === "ldo" ? "LDO" : "Buck"} from {stage.source} · {Math.round(stage.load_a * 1000)} mA</small>
      <small>{stage.loss_w == null ? stage.note : `${watts(stage.loss_w)} heat · ${percent(stage.efficiency)} efficient`}</small>
    </>
  );
}

export function PowerTree() {
  const [vin, setVin] = useState(24);
  const [rails, setRails] = useState<Rail[]>([{ voltage_v: 5, current_a: 0.5 }, { voltage_v: 3.3, current_a: 0.2 }]);
  const [result, setResult] = useState<PowerTreeResult>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const setRail = (index: number, key: keyof Rail, value: number) =>
    setRails(old => old.map((rail, i) => (i === index ? { ...rail, [key]: value } : rail)));
  const valid = vin > 0 && rails.every(rail => rail.voltage_v > 0 && rail.current_a > 0);

  const propose = async () => {
    if (!valid) { setError("Every voltage and current must be greater than zero."); return; }
    setBusy(true);
    setError(undefined);
    try {
      setResult(await proposePowerTree({ input_voltage_v: vin, rails }));
    } catch (err) {
      setError(err instanceof Error && typeof err.message === "string" ? err.message : "Could not propose a power tree.");
    } finally {
      setBusy(false);
    }
  };

  const railNames = result?.options[0]?.stages.map(stage => stage.rail) ?? [];

  return (
    <section className="card eval power-tree">
      <header className="card-head">
        <div><h2>Power tree</h2><p className="sub">Catalog bucks and LDOs for up to three rails · ranked by total loss</p></div>
      </header>
      <div className="pt-form">
        <label className="field">
          <span className="field-label">Input</span>
          <span className="input-wrap"><input type="number" inputMode="decimal" value={vin} onChange={e => setVin(Number(e.target.value))} /><span className="unit">V</span></span>
        </label>
        {rails.map((rail, i) => (
          <div className="pt-rail" key={i}>
            <label className="field">
              <span className="field-label">Rail {i + 1}</span>
              <span className="input-wrap"><input type="number" inputMode="decimal" value={rail.voltage_v} onChange={e => setRail(i, "voltage_v", Number(e.target.value))} /><span className="unit">V</span></span>
            </label>
            <label className="field">
              <span className="field-label">Current</span>
              <span className="input-wrap"><input type="number" inputMode="decimal" value={rail.current_a} onChange={e => setRail(i, "current_a", Number(e.target.value))} /><span className="unit">A</span></span>
            </label>
            {rails.length > 1 && (
              <button type="button" className="icon-btn" aria-label={`Remove rail ${i + 1}`} onClick={() => setRails(old => old.filter((_, j) => j !== i))}><Icon name="x" size={16} /></button>
            )}
          </div>
        ))}
        <div className="pt-actions">
          {rails.length < MAX_RAILS && (
            <button type="button" className="btn ghost" onClick={() => setRails(old => [...old, { voltage_v: 1.8, current_a: 0.1 }])}>Add rail</button>
          )}
          <button type="button" className="btn primary" disabled={busy} onClick={() => void propose()}>
            {busy ? <><span className="spinner" />Proposing…</> : <><Icon name="bolt" size={15} />Propose</>}
          </button>
        </div>
      </div>

      {error && <div className="callout danger pt-callout" role="alert"><Icon name="alert" size={18} /><div>{error}</div></div>}
      {result && result.unserved.length > 0 && (
        <div className="callout warn pt-callout"><Icon name="alert" size={18} /><div><ul>{result.unserved.map(u => <li key={u.rail}><strong>{u.rail}:</strong> {u.reason}</li>)}</ul></div></div>
      )}
      {result && result.options.length === 0 && (
        <div className="eval-empty"><Icon name="info" size={20} /><span>No catalog part can supply any of these rails.</span></div>
      )}
      {result && result.options.length > 0 && (
        <div className="table-wrap">
          <table className="rtable static">
            <thead><tr><th>#</th>{railNames.map(name => <th key={name}>{name}</th>)}<th>Total heat</th><th>Efficiency</th><th>Cost</th></tr></thead>
            <tbody>
              {result.options.map((option, i) => (
                <tr key={option.label + i} className={i === 0 && option.complete && option.total_loss_w != null ? "best" : ""}>
                  <td><strong>{i + 1}</strong>{!option.complete && <small>incomplete</small>}</td>
                  {option.stages.map(stage => <td key={stage.rail}><StageCell stage={stage} /></td>)}
                  <td>{watts(option.total_loss_w) ?? <small>efficiency not in catalog</small>}</td>
                  <td>{option.efficiency == null ? "—" : percent(option.efficiency)}</td>
                  <td>{option.cost_usd == null ? <small>{dollars(option.cost_usd)}</small> : dollars(option.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

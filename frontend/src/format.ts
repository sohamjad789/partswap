import type { CheckResult, CheckValue, Decision, Mode, Verdict } from "./types";

export const VERDICTS: Verdict[] = ["drop_in", "drop_in_with_caveats", "needs_redesign", "no_safe_match"];

export const verdictLabel: Record<Verdict, string> = {
  drop_in: "Drop-in",
  drop_in_with_caveats: "Drop-in with caveats",
  needs_redesign: "Needs redesign",
  no_safe_match: "No safe match",
};

export const verdictHint: Record<Verdict, string> = {
  drop_in: "Swap with no board changes",
  drop_in_with_caveats: "Swap works, review the caveats",
  needs_redesign: "Closest part needs layout or circuit changes",
  no_safe_match: "Nothing in the catalog is safe here",
};

export const modeInfo: Record<Mode, { label: string; hint: string }> = {
  fixture: { label: "Fixture", hint: "Replays a recorded run. No network." },
  deterministic: { label: "Deterministic", hint: "Python rules only. No model, no key." },
  cache: { label: "Cache", hint: "Reuses stored agent decisions." },
  live: { label: "Live", hint: "Calls Nemotron. Needs an API key." },
};

const specNames: Record<string, string> = {
  output_type: "Output type",
  topology: "Topology",
  polarity: "Polarity",
  diode_count: "Diode count",
  channel_count: "Channel count",
  category: "Category",
  package: "Package",
  pinout: "Pinout",
  vout_v: "Output voltage",
  vin_abs_max_v: "VIN absolute max",
  vin_max_v: "VIN max",
  vin_min_v: "VIN min",
  iout_max_a: "Output current",
  dropout_v: "Dropout voltage",
  iq_a: "Quiescent current",
  fsw_hz: "Switching frequency",
  vrrm_v: "Reverse voltage (VRRM)",
  if_avg_a: "Avg. forward current",
  vf_v: "Forward voltage",
  ir_a: "Reverse leakage",
  vds_max_v: "Drain-source voltage",
  id_max_a: "Drain current",
  vgs_max_v: "Gate-source max",
  vgs_th_max_v: "Gate threshold",
  rds_on_ohm: "On-resistance",
  vrwm_v: "Working voltage (VRWM)",
  esd_contact_kv: "ESD contact rating",
  vc_v: "Clamping voltage",
  c_pf: "Capacitance",
  temp_min_c: "Temp min",
  temp_max_c: "Temp max",
};

export function specName(key: string): string {
  if (specNames[key]) return specNames[key];
  const words = key.replace(/_(v|a|c|hz|ohm|pf|kv)$/, "").split("_");
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function valueText(side?: CheckValue | null): string {
  if (!side) return "—";
  if (side.raw) return side.raw;
  return side.value == null ? "—" : String(side.value);
}

export const resultLabel: Record<CheckResult, string> = {
  pass: "Pass",
  fail: "Fail",
  caveat: "Caveat",
  unknown: "Unknown",
  skip: "Skipped",
};

export function trapCount(decision?: Decision): number {
  return decision?.rejected.filter(candidate => candidate.headline_match).length ?? 0;
}

export function percent(value?: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function titleCase(text: string): string {
  return text.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
}

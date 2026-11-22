export type Mode = "fixture" | "deterministic" | "cache" | "live";
export type Verdict = "drop_in" | "drop_in_with_caveats" | "needs_redesign" | "no_safe_match";
export type CheckResult = "pass" | "fail" | "caveat" | "unknown" | "skip";
export type Goal = "lowest_risk" | "lowest_cost" | "shortest_lead_time";

export interface BomLine { ref: string; manufacturer: string; mpn: string; qty: number; description: string; [key: string]: string | number | undefined; }
export interface DesignContext { input_voltage_v: number; input_voltage_max_v: number; operating_temp_min_c: number; operating_temp_max_c: number; preferred_manufacturer: string; goal: Goal; }
export interface CheckValue { value?: string | number | null; raw?: string | null; condition?: string | null; page?: number | null; }
export interface Check { spec: string; result: CheckResult; requirement?: string | null; original?: CheckValue | null; candidate?: CheckValue | null; reason: string; }
export interface RejectedCandidate { mpn: string; manufacturer: string; verdict: Verdict; reason: string; headline_match: boolean; }
export interface Decision { ref: string; original_mpn: string; original_manufacturer: string; recommended_mpn?: string | null; recommended_manufacturer?: string | null; compared_mpn?: string | null; verdict: Verdict; model_verdict?: Verdict | null; tightened: boolean; confidence?: number | null; source: string; model?: string | null; spec_checks: Check[]; package_pinout?: { package_result: CheckResult; pinout_result: CheckResult; detail: string } | null; caveats: string[]; explanation: string; rejected: RejectedCandidate[]; candidates_considered: string[]; }
export interface AgentStep { ref: string; step: number; kind: "reasoning" | "tool_call" | "tool_result" | "guardrail" | "error"; text?: string; tool?: string; arguments?: Record<string, unknown>; summary?: string; }
export type RunEvent = { event: "run_started"; data: { run_id: string; part_count: number; mode: Mode } } | { event: "part_started"; data: { ref: string; mpn: string; index: number } } | { event: "agent_step"; data: AgentStep } | { event: "part_decision"; data: Decision } | { event: "part_error"; data: { ref: string; message: string; fallback: true } } | { event: "run_completed"; data: { run_id: string; elapsed_ms: number } } | { event: "error"; data: { message: string } };
export interface Health { status: string; mode_default: Mode; has_api_key: boolean; }
export interface EvalApproach { name: string; accuracy: number; false_drop_in_count: number; model_false_drop_in_count?: number | null; tightened_count?: number | null; fallback_count?: number | null; median_latency_ms: number; }
export interface EvalResults { ready?: boolean; generated_at?: string; pair_count?: number; dangerous_count?: number; prompt_version?: string; approaches?: EvalApproach[]; }
export interface PartInfo { mpn: string; manufacturer: string; category: string; description?: string; datasheet_available?: boolean; package?: { code: string; pins: number } | null; }
export interface Rail { voltage_v: number; current_a: number; }
export interface PowerStage { rail: string; rail_voltage_v: number; source: string; source_voltage_v?: number | null; mpn?: string | null; manufacturer?: string | null; category?: "ldo" | "buck" | null; load_a: number; input_current_a?: number | null; loss_w?: number | null; efficiency?: number | null; unit_price_usd?: number | null; note?: string | null; }
export interface PowerOption { label: string; complete: boolean; stages: PowerStage[]; part_count: number; total_loss_w?: number | null; efficiency?: number | null; cost_usd?: number | null; }
export interface PowerTreeResult { input_voltage_v: number; options: PowerOption[]; unserved: Array<{ rail: string; reason: string }>; }
export interface Extraction { available: boolean; parser?: string; fields?: Array<{ key: string; verified_raw?: string | null; extracted_raw?: string | null; status: "match" | "mismatch" | "missing" }>; }

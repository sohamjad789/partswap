import { useEffect, useRef, useState } from "react";
import { VERDICTS, verdictHint, verdictLabel } from "../format";
import type { Verdict } from "../types";
import { Icon } from "./Icon";

/** Counts up smoothly when the value changes. */
function Counter({ value }: { value: number }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = performance.now();
    const begin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 450);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(Math.round(begin + (value - begin) * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = value;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <>{shown}</>;
}

interface Props {
  counts: Record<Verdict, number>;
  traps: number;
  filter?: Verdict;
  onFilter: (verdict?: Verdict) => void;
}

export function SummaryStrip({ counts, traps, filter, onFilter }: Props) {
  return (
    <div className="summary">
      {VERDICTS.map(verdict => (
        <button
          type="button"
          key={verdict}
          className={`stat ${verdict}${filter === verdict ? " on" : ""}${filter && filter !== verdict ? " dim" : ""}`}
          onClick={() => onFilter(filter === verdict ? undefined : verdict)}
          aria-pressed={filter === verdict}
          title={verdictHint[verdict]}
        >
          <span className="stat-top"><span className={`dot ${verdict}`} />{verdictLabel[verdict]}</span>
          <span className="stat-num"><Counter value={counts[verdict]} /></span>
        </button>
      ))}
      <div className="stat traps" title="Candidates that match on headline specs but were rejected from the datasheet">
        <span className="stat-top"><Icon name="shield" size={16} />Traps caught</span>
        <span className="stat-num"><Counter value={traps} /></span>
      </div>
    </div>
  );
}

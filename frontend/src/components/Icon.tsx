const paths: Record<string, string> = {
  logo: "M7 4h6a5 5 0 0 1 0 10H9v6H6V5a1 1 0 0 1 1-1zm2 3v4h4a2 2 0 0 0 0-4H9z",
  upload: "M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5zm0 0v5h5M9 13h6M9 17h4",
  sparkle: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z",
  play: "M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5z",
  arrow: "M5 12h14m0 0-5-5m5 5-5 5",
  check: "M5 12.5l4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6 6 18",
  alert: "M12 9v4m0 4h.01M10.3 3.9 2.4 17.6A2 2 0 0 0 4.1 20.6h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-13h.01M11 12h1v5h1",
  question: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm-2.5-11.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14m0 3h.01",
  shield: "M12 3 4.5 6v5.5c0 4.6 3.2 8.5 7.5 9.5 4.3-1 7.5-4.9 7.5-9.5V6L12 3zm-3.5 9 2.5 2.5 4.5-5",
  brain: "M9.5 4A2.5 2.5 0 0 0 7 6.5v.2A3 3 0 0 0 4.5 9.6 3 3 0 0 0 5 15a2.5 2.5 0 0 0 4.5 2.4V4.6M14.5 4A2.5 2.5 0 0 1 17 6.5v.2a3 3 0 0 1 2.5 2.9A3 3 0 0 1 19 15a2.5 2.5 0 0 1-4.5 2.4V4.6M9.5 4.6a2.5 2.5 0 0 1 5 0",
  tool: "M14.7 6.3a4 4 0 0 0-5.4 5l-5.6 5.6a1.5 1.5 0 0 0 2.1 2.1l5.6-5.6a4 4 0 0 0 5-5.4l-2.6 2.6-2.1-.5-.5-2.1 2.6-2.6z",
  result: "M4 12h4l2.5-6 3 12 2.5-6H20",
  download: "M12 4v11m0 0 4.5-4.5M12 15l-4.5-4.5M4 17v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1",
  chevron: "M6 9l6 6 6-6",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm9 2-4-4",
  chip: "M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm3 5h4v4h-4z",
  bolt: "M13 3 5 13.5h6L10 21l8-10.5h-6L13 3z",
  link: "M14 4h6v6m0-6-9 9M19 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-13v4.5l3 1.5",
  package: "M12 3 4 7.5v9L12 21l8-4.5v-9L12 3zm0 0v18M4 7.5l8 4.5 8-4.5",
  layers: "M12 3 3 8l9 5 9-5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5",
  expand: "M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7",
  collapse: "M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7",
  keyboard: "M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zm3 4h.01M11 10h.01M15 10h.01M7 14h10",
};

export type IconName = keyof typeof paths;

export function Icon({ name, size = 18, className, strokeWidth = 1.9 }: { name: IconName; size?: number; className?: string; strokeWidth?: number }) {
  const filled = name === "play" || name === "logo";
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}

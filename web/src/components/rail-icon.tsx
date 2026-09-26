import type { CSSProperties } from "react";

export type IconName = "rail" | "overview" | "work" | "corridor" | "plan" | "solver" | "compare" | "validate" | "review" | "calendar" | "change" | "execution" | "report" | "data" | "settings" | "health" | "menu" | "close" | "arrow" | "search";

const paths: Record<IconName, string> = {
  rail: "M7 3h10v12H7z M7 8h10 M9 18l-3 3 M15 18l3 3 M8 18h8 M10 12h.01 M14 12h.01",
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  work: "M9 5V3h6v2 M5 5h14v16H5z M8 10h8 M8 14h5 M8 18h7",
  corridor: "M4 5h16 M4 19h16 M6 5v14 M18 5v14 M6 9h12 M6 15h12",
  plan: "M4 3v18h17 M8 7h11 M8 12h7 M11 17h10",
  solver: "M8 3h8v5H8z M3 16h6v5H3z M15 16h6v5h-6z M12 8v4 M6 16v-4h12v4",
  compare: "M4 5h16 M12 3v18 M4 10h5 M15 10h5 M4 15h5 M15 15h3 M4 20h5 M15 20h6",
  validate: "M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6",
  review: "M5 3h10l4 4v5 M15 3v5h4 M5 3v18h8 M8 8h3 M8 12h5 M15 18l2 2 5-6",
  calendar: "M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2 M8 18h2",
  change: "M4 8a8 8 0 0 1 14-3l2 3 M20 3v5h-5 M20 16a8 8 0 0 1-14 3l-2-3 M4 21v-5h5",
  execution: "M8 4h12v16H8 M4 8l4 4-4 4 M1 12h13 M13 7h4 M13 17h4",
  report: "M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5",
  data: "M4 5h16v5H4z M4 14h16v5H4z M7 7.5h.01 M7 16.5h.01 M10 10v4 M14 10v4",
  settings: "M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6",
  health: "M3 12h4l3-7 4 14 3-7h4",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  close: "M6 6l12 12 M6 18L18 6",
  arrow: "M4 12h16 M14 6l6 6-6 6",
  search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6",
};

export function RailIcon({name, size=20, style}: {name:IconName; size?:number; style?:CSSProperties}) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={paths[name]}/></svg>;
}

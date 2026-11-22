import { useEffect, useState } from "react";
import { Icon } from "./Icon";

type Theme = "light" | "dark";
const STORAGE_KEY = "partswap-theme";

/** The theme index.html already applied before React rendered (stored choice, else the OS setting). */
function initialTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

/** One minimal button that switches between light and dark mode and remembers the choice. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* storage can be unavailable (private mode); the toggle still works for this visit */
    }
  }, [theme]);

  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="theme-toggle" onClick={() => setTheme(next)} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
    </button>
  );
}

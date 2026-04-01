import { useTheme } from './ThemeProvider';

export function ThemeToggleButton() {
  const { theme, toggleTheme } = useTheme();
  const switchingToLight = theme === 'dark';
  const label = switchingToLight ? 'Switch to light mode' : 'Switch to dark mode';

  return (
    <button
      type="button"
      className="button-secondary theme-toggle-button"
      aria-label={label}
      title={label}
      onClick={toggleTheme}
    >
      {switchingToLight ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.75v2.5" />
      <path d="M12 18.75v2.5" />
      <path d="M21.25 12h-2.5" />
      <path d="M5.25 12h-2.5" />
      <path d="m18.54 5.46-1.77 1.77" />
      <path d="m7.23 16.77-1.77 1.77" />
      <path d="m18.54 18.54-1.77-1.77" />
      <path d="M7.23 7.23 5.46 5.46" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14.5 3.75a8.75 8.75 0 1 0 5.75 15.35A9.75 9.75 0 0 1 14.5 3.75Z" />
    </svg>
  );
}

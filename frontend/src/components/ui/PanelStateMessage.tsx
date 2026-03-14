interface PanelStateMessageProps {
  message: string;
  compact?: boolean;
}

/**
 * Shared empty/loading message treatment used across auth and dashboard panels.
 * Keeping this centralized prevents subtle state-style drift between screens.
 */
export function PanelStateMessage({ message, compact = false }: PanelStateMessageProps) {
  const className = compact ? 'panel-state panel-state-compact' : 'panel-state';
  return (
    <div className={className}>
      <p className="state-text">{message}</p>
    </div>
  );
}

import type { ThemeMode } from '../hooks/useTheme'
import { DesktopIcon, MoonIcon, SunIcon } from './icons'

interface Props {
  mode: ThemeMode
  onChange: (mode: ThemeMode) => void
}

const OPTIONS: { mode: ThemeMode; label: string; Icon: typeof SunIcon }[] = [
  { mode: 'system', label: 'System', Icon: DesktopIcon },
  { mode: 'light', label: 'Light', Icon: SunIcon },
  { mode: 'dark', label: 'Dark', Icon: MoonIcon },
]

export function ThemeSelector({ mode, onChange }: Props) {
  return (
    <div className="theme-control">
      <span className="theme-label">Appearance</span>
      <div className="theme-selector" role="group" aria-label="Theme mode">
        {OPTIONS.map(({ mode: option, label, Icon }) => (
          <button
            key={option}
            type="button"
            className={`theme-option ${mode === option ? 'active' : ''}`}
            onClick={() => onChange(option)}
            aria-pressed={mode === option}
            title={`${label} theme`}
          >
            <Icon className="btn-icon" width={13} height={13} />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { THEME_STORAGE_KEY, getInitialTheme } from '../lib/theme'
import type { Theme } from '../lib/theme'

/**
 * 全画面共通のダークモード切り替えボタン（docs/spec.md §4「全画面共通：ダークモード切り替え」）。
 * `document.documentElement`の`data-theme`属性を切り替え、選択を`localStorage`に保存する。
 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() =>
    getInitialTheme(
      localStorage.getItem(THEME_STORAGE_KEY),
      window.matchMedia('(prefers-color-scheme: dark)').matches,
    ),
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  return (
    <button
      className="theme-toggle"
      onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
    >
      {theme === 'dark' ? '☀️ ライト' : '🌙 ダーク'}
    </button>
  )
}

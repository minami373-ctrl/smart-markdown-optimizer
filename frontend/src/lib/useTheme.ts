import { useEffect, useState } from 'react'
import type { Theme } from './theme'

function currentTheme(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}

/**
 * `document.documentElement`の`data-theme`属性を購読するフック（docs/spec.md §4
 * 「全画面共通：ダークモード切り替え」）。Chart.jsはcanvasに直接描画するためCSS変数を
 * 追従できず、tick/grid色をJS側で明示的に切り替える必要がある箇所（グラフコンポーネント）で使う。
 * `ThemeToggle`とはReact Contextを介さない疎結合（`MutationObserver`で属性変化を監視するだけ）。
 */
export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(currentTheme)

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(currentTheme()))
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    return () => observer.disconnect()
  }, [])

  return theme
}

/**
 * Chart.jsの軸目盛り・グリッド線の色をテーマに合わせて返す（index.cssの`--sub`/`--ink`と同系色）。
 * canvas描画はCSS変数を追従できないため、JS側で明示的に切り替える。
 */
export function chartAxisColors(theme: Theme): { tick: string; grid: string } {
  return theme === 'dark'
    ? { tick: '#a89e8f', grid: 'rgba(240, 236, 230, 0.12)' }
    : { tick: '#7a7268', grid: 'rgba(43, 38, 32, 0.1)' }
}

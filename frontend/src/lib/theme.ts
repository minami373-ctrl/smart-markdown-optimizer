export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'theme'

/**
 * ダークモードの初期状態を決める純関数（docs/spec.md §4「全画面共通：ダークモード切り替え」）。
 * 優先順：①保存済みの選択 ②OSの設定（prefers-color-scheme） ③ライトモード。
 */
export function getInitialTheme(storedValue: string | null, prefersDark: boolean): Theme {
  if (storedValue === 'light' || storedValue === 'dark') return storedValue
  return prefersDark ? 'dark' : 'light'
}

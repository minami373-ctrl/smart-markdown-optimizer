import { describe, expect, it } from 'vitest'
import { getInitialTheme } from './theme'

describe('getInitialTheme', () => {
  it('保存済みの選択があればそれを優先する（OS設定と食い違っていても）', () => {
    expect(getInitialTheme('light', true)).toBe('light')
    expect(getInitialTheme('dark', false)).toBe('dark')
  })

  it('保存済みの選択が無ければOSの設定に従う', () => {
    expect(getInitialTheme(null, true)).toBe('dark')
    expect(getInitialTheme(null, false)).toBe('light')
  })

  it('保存済みの値が不正（想定外の文字列）ならOSの設定に従う', () => {
    expect(getInitialTheme('sepia', true)).toBe('dark')
    expect(getInitialTheme('', false)).toBe('light')
  })
})

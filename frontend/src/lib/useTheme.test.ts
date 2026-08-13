import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { chartAxisColors, useTheme } from './useTheme'

describe('useTheme', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-theme')
  })

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme')
  })

  it('data-theme属性が無ければ light を返す', () => {
    const { result } = renderHook(() => useTheme())

    expect(result.current).toBe('light')
  })

  it('data-theme="dark" が既に付いていれば dark を返す', () => {
    document.documentElement.setAttribute('data-theme', 'dark')

    const { result } = renderHook(() => useTheme())

    expect(result.current).toBe('dark')
  })

  it('data-theme属性が後から変わると、値も追従する（MutationObserver経由）', async () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current).toBe('light')

    act(() => {
      document.documentElement.setAttribute('data-theme', 'dark')
    })

    await waitFor(() => {
      expect(result.current).toBe('dark')
    })
  })
})

describe('chartAxisColors', () => {
  it('light と dark で異なる色を返す', () => {
    const light = chartAxisColors('light')
    const dark = chartAxisColors('dark')

    expect(light.tick).not.toBe(dark.tick)
    expect(light.grid).not.toBe(dark.grid)
  })
})

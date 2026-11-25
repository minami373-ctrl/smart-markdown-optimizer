import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ThemeToggle from './ThemeToggle'
import { THEME_STORAGE_KEY } from '../lib/theme'

function mockPrefersDark(matches: boolean) {
  // jsdomはmatchMediaを実装していないためモックする
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

describe('ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('保存済みの選択が無く、OSがダークならダークモードで開始する', () => {
    mockPrefersDark(true)

    render(<ThemeToggle />)

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(screen.getByRole('button', { name: /明るい表示/ })).toBeInTheDocument()
  })

  it('保存済みの選択が無く、OSがライトならライトモードで開始する', () => {
    mockPrefersDark(false)

    render(<ThemeToggle />)

    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(screen.getByRole('button', { name: /暗い表示/ })).toBeInTheDocument()
  })

  it('localStorageに保存済みの選択があれば、OSの設定より優先する', () => {
    mockPrefersDark(true) // OSはダークだが
    localStorage.setItem(THEME_STORAGE_KEY, 'light') // 保存済みの選択（ライト）を優先

    render(<ThemeToggle />)

    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('ボタンを押すとモードが切り替わり、data-theme属性とlocalStorageの両方が更新される', async () => {
    mockPrefersDark(false)
    const user = userEvent.setup()
    render(<ThemeToggle />)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    await user.click(screen.getByRole('button'))

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(screen.getByRole('button', { name: /明るい表示/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button'))

    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  })
})

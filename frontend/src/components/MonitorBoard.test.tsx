import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MonitorBoard from './MonitorBoard'

describe('MonitorBoard', () => {
  it('値引き中の商品は値引きの言葉と値引き後の売値、売り切れは「売り切れ」を表示する', () => {
    render(
      <MonitorBoard
        clock="20:30"
        items={[
          { productId: 1, name: '唐揚げ弁当', unitPrice: 430, appliedRate: 0.5, remainingStock: 3 },
          { productId: 2, name: 'ロースカツ', unitPrice: 250, appliedRate: 0, remainingStock: 8 },
          { productId: 3, name: 'たこ焼き', unitPrice: 300, appliedRate: 0.3, remainingStock: 0 },
        ]}
      />,
    )

    const board = screen.getByLabelText('売り場モニター')
    expect(within(board).getByText('20:30')).toBeInTheDocument()
    const bento = within(board).getByText('唐揚げ弁当').closest('li')!
    expect(bento).toHaveTextContent('50%引き')
    expect(bento).toHaveTextContent('¥215')
    const katsu = within(board).getByText('ロースカツ').closest('li')!
    expect(katsu).toHaveTextContent('¥250')
    expect(katsu).not.toHaveTextContent('引き')
    const tako = within(board).getByText('たこ焼き').closest('li')!
    expect(tako).toHaveTextContent('売り切れ')
  })
})

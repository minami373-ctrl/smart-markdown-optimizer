import { describe, expect, it } from 'vitest'
import { storeAlert } from './storeAlert'

describe('storeAlert', () => {
  it('半分以上の商品が「売れていない」なら店全体の知らせを出す', () => {
    expect(storeAlert(['low', 'low', null, 'high'])).toBe(
      '今日はいつもより売れていません（4商品中2商品）。長期休みなど、入れ忘れた条件がないか確認してください。',
    )
  })

  it('半分以上の商品が「売れている」なら逆向きの知らせ', () => {
    expect(storeAlert(['high', 'high', 'high', null])).toMatch(/^今日はいつもより売れています（4商品中3商品）/)
  })

  it('一部の商品だけが外れているときは出さない（ばらつきの範囲）', () => {
    expect(storeAlert(['low', null, null, 'high'])).toBeNull()
    expect(storeAlert([])).toBeNull()
  })
})

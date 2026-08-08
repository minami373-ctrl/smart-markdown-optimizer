import { describe, expect, it } from 'vitest'
import { conditionKey } from './conditionKey'

describe('conditionKey', () => {
  it('天気・曜日・イベント有無からバックエンドと同じ形式のキーを作る', () => {
    expect(conditionKey('晴れ', '平日', false)).toBe('晴れ_平日_なし')
    expect(conditionKey('雨', '休日', true)).toBe('雨_休日_あり')
  })
})

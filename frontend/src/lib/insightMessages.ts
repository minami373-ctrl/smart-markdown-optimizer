export interface InsightMessage {
  text: string
  to: string
}

/**
 * 分析結果バナー（docs/spec.md §4「全画面共通：分析結果バナー」）用のメッセージを組み立てる純関数。
 * 件数が0のものはメッセージを作らない。両方0件なら空配列（＝バナー自体を表示しない）。
 */
export function buildInsightMessages(
  opportunityCount: number,
  overstockCount: number,
): InsightMessage[] {
  const messages: InsightMessage[] = []
  if (opportunityCount > 0) {
    messages.push({
      text: `在庫不足の可能性がある商品が${opportunityCount}件あります。`,
      to: '/opportunities',
    })
  }
  if (overstockCount > 0) {
    messages.push({
      text: `過剰在庫の可能性がある商品が${overstockCount}件あります。`,
      to: '/overstock',
    })
  }
  return messages
}

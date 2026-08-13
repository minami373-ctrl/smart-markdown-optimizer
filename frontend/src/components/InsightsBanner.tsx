import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchOpportunities } from '../api/opportunities'
import { fetchOverstocks } from '../api/overstock'
import { buildInsightMessages } from '../lib/insightMessages'

/**
 * 全画面共通の分析結果バナー（docs/spec.md §4「全画面共通：分析結果バナー」）。
 * アプリ起動時に一度だけ機会損失・過剰在庫の件数を取得し、1件以上ある間だけ表示する。
 * どちらかの取得に失敗しても、その行だけ出さずアプリ全体は正常に表示され続ける
 * （0件と失敗を区別せず、単に出さない）。
 */
export default function InsightsBanner() {
  const [opportunityCount, setOpportunityCount] = useState(0)
  const [overstockCount, setOverstockCount] = useState(0)

  useEffect(() => {
    fetchOpportunities()
      .then((list) => setOpportunityCount(list.length))
      .catch(() => {})
    fetchOverstocks()
      .then((list) => setOverstockCount(list.length))
      .catch(() => {})
  }, [])

  const messages = buildInsightMessages(opportunityCount, overstockCount)

  if (messages.length === 0) return null

  return (
    <div className="insight-banner">
      {messages.map((m) => (
        <div key={m.to} className="insight-banner-row">
          {m.text} <Link to={m.to}>詳しく見る →</Link>
        </div>
      ))}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { fetchOpportunities } from '../api/opportunities'
import type { Opportunity } from '../api/types'

const TOTAL_STEPS = 40

export default function OpportunitiesPage() {
  const [opportunities, setOpportunities] = useState<Opportunity[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchOpportunities()
      .then(setOpportunities)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="error">{error}</p>

  return (
    <div>
      <h1>機会損失分析</h1>
      <p>
        値引きを一切せず、閉店より前に完売してしまった商品です。在庫を増やせばもっと売れていた可能性があります。
      </p>

      {opportunities === null && <p>読み込み中…</p>}

      {opportunities !== null && opportunities.length === 0 && (
        <p className="card">値引きなしで早期完売した商品はまだありません。</p>
      )}

      {opportunities !== null && opportunities.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>順位</th>
                <th>商品名</th>
                <th>該当回数</th>
                <th>平均完売ステップ</th>
                <th>推奨追加在庫数</th>
              </tr>
            </thead>
            <tbody>
              {opportunities.map((o, i) => (
                <tr key={o.product_id}>
                  <td>{i + 1}</td>
                  <td>{o.product_name}</td>
                  <td>{o.occurrence_count}回</td>
                  <td>
                    {Math.round(o.avg_sellout_step)}/{TOTAL_STEPS}
                  </td>
                  <td>
                    <strong>+{Math.round(o.avg_suggested_increase)}個</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const BUSINESS_START_MINUTES = 10 * 60 // 10:00
const BUSINESS_END_MINUTES = 22 * 60 // 22:00（2026-11-26改訂。1ステップ18分）
const DEFAULT_TOTAL_STEPS = 48 // 15分ごと（docs/spec.md §5.19。2026-11-26改訂）

/**
 * シミュレーションのステップ番号を営業時間（10:00〜22:00。docs/spec.md §5.2）内の
 * 時刻（`HH:MM`）に変換する純関数（docs/spec.md §4①「現在の時刻」）。
 * `step`が範囲外でも`0`〜`totalSteps`にクランプし、壊れた表示にしない。
 */
export function stepToClockTime(step: number, totalSteps: number = DEFAULT_TOTAL_STEPS): string {
  const clampedStep = Math.max(0, Math.min(step, totalSteps))
  const ratio = totalSteps > 0 ? clampedStep / totalSteps : 0
  // 分単位で先に丸めてからhours/minutesに分解する（分だけ丸めるとXX:60になりうるため）
  const totalMinutes = Math.round(
    BUSINESS_START_MINUTES + (BUSINESS_END_MINUTES - BUSINESS_START_MINUTES) * ratio,
  )
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

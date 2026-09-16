
export default function ScoreBadge({ score, onClick }) {
  const cls = score >= 70
    ? 'bg-emerald-900 text-emerald-300 border border-emerald-700'
    : score >= 40
    ? 'bg-yellow-900 text-yellow-300 border border-yellow-700'
    : 'bg-red-900 text-red-300 border border-red-700'

  return (
    <span
      onClick={onClick}
      className={`${cls} text-xs font-bold px-2.5 py-1 rounded-full ${onClick ? 'cursor-pointer hover:opacity-80 transition' : ''}`}>
      {score}%
    </span>
  )
}

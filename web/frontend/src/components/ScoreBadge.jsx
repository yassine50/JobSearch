import { motion } from 'framer-motion'

export default function ScoreBadge({ score = 0, onClick, size = 'sm' }) {
  const safeScore = Math.max(0, Math.min(100, Number(score) || 0))

  const palette = safeScore >= 75
    ? {
        bg: 'bg-emerald-950/85 hover:bg-emerald-900/80',
        border: 'border-emerald-500/40',
        text: 'text-emerald-300',
        stroke: '#10b981',
        glow: 'shadow-[0_0_15px_-3px_rgba(16,185,129,0.3)]'
      }
    : safeScore >= 50
    ? {
        bg: 'bg-blue-950/85 hover:bg-blue-900/80',
        border: 'border-blue-500/40',
        text: 'text-blue-300',
        stroke: '#3b82f6',
        glow: 'shadow-[0_0_15px_-3px_rgba(59,130,246,0.3)]'
      }
    : {
        bg: 'bg-amber-950/85 hover:bg-amber-900/80',
        border: 'border-amber-500/40',
        text: 'text-amber-300',
        stroke: '#f59e0b',
        glow: 'shadow-[0_0_15px_-3px_rgba(245,158,11,0.25)]'
      }

  const radius = size === 'lg' ? 10 : 7
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference - (safeScore / 100) * circumference
  const svgDim = size === 'lg' ? 26 : 18

  return (
    <motion.span
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.96 }}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 ${palette.bg} ${palette.text} border ${palette.border} ${palette.glow} text-xs font-extrabold px-2.5 py-1 rounded-full transition-all select-none ${
        onClick ? 'cursor-pointer' : ''
      }`}
    >
      <svg width={svgDim} height={svgDim} className="-rotate-90 shrink-0">
        <circle
          cx={svgDim / 2}
          cy={svgDim / 2}
          r={radius}
          fill="transparent"
          stroke="rgba(148, 163, 184, 0.2)"
          strokeWidth="2.4"
        />
        <motion.circle
          cx={svgDim / 2}
          cy={svgDim / 2}
          r={radius}
          fill="transparent"
          stroke={palette.stroke}
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </svg>
      <span>{safeScore}%</span>
    </motion.span>
  )
}

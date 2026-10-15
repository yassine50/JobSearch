import { useId } from 'react'

/**
 * Official CVtoMatch Brand Logo
 * Features the geometric C arc + V checkmark monogram + emerald status dot,
 * paired with "CVto" (white) + "Match" (#818CF8) and "AI RESUME & CAREER OS" subtitle.
 */
export default function BrandLogo({ size = 'md', showSubtitle = true, className = '' }) {
  const uid = useId()
  const cGradId = `cvm-c-${uid}`
  const vGradId = `cvm-v-${uid}`

  const sizes = {
    sm: {
      icon: 32,
      title: 'text-[17px]',
      sub: 'text-[7.5px] tracking-[0.22em]',
      gap: 'gap-2.5',
    },
    md: {
      icon: 40,
      title: 'text-[21px]',
      sub: 'text-[8.5px] tracking-[0.25em]',
      gap: 'gap-3',
    },
    lg: {
      icon: 46,
      title: 'text-[25px]',
      sub: 'text-[9.5px] tracking-[0.27em]',
      gap: 'gap-3.5',
    },
  }

  const s = sizes[size] || sizes.md

  return (
    <div className={`inline-flex items-center select-none ${s.gap} ${className}`}>
      {/* C + V Checkmark + Emerald Dot Monogram */}
      <svg
        width={s.icon}
        height={s.icon}
        viewBox="0 0 60 56"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0 group-hover:scale-105 transition-transform duration-200"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={cGradId} x1="6" y1="8" x2="40" y2="50" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#5B58F6" />
            <stop offset="100%" stopColor="#4338CA" />
          </linearGradient>
          <linearGradient id={vGradId} x1="22" y1="38" x2="48" y2="14" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#6366F1" />
            <stop offset="100%" stopColor="#8B93FF" />
          </linearGradient>
        </defs>
        {/* Bold C Arc */}
        <path
          d="M36.8 16.5C33.6 13.5 29.3 12 24.5 12C14.6 12 7 19.8 7 30C7 40.2 14.6 48 24.5 48C29.6 48 34 46.2 37.3 42.9"
          stroke={`url(#${cGradId})`}
          strokeWidth="10.2"
          strokeLinecap="butt"
        />
        {/* Nested V Checkmark */}
        <path
          d="M22.5 27.5L29.8 38.2L45 16.8"
          stroke={`url(#${vGradId})`}
          strokeWidth="8.2"
          strokeLinecap="butt"
          strokeLinejoin="miter"
        />
        {/* Emerald Top-Right Dot */}
        <circle cx="50" cy="10.5" r="4.2" fill="#10B981" />
      </svg>

      {/* Wordmark & Subtitle */}
      <div className="flex flex-col justify-center min-w-0">
        <div className={`${s.title} font-black tracking-tight leading-none flex items-baseline`}>
          <span className="text-white">CVto</span>
          <span className="text-[#818CF8]">Match</span>
        </div>
        {showSubtitle && (
          <span
            className={`${s.sub} font-bold uppercase text-slate-400/90 block mt-1.5 leading-none whitespace-nowrap`}
          >
            AI RESUME &amp; CAREER OS
          </span>
        )}
      </div>
    </div>
  )
}

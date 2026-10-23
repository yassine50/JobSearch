export default function PageWrapper({ children }) {
  return (
    <div className="relative min-h-screen bg-[#050811] bg-grid-pattern overflow-x-hidden">
      {/* Ambient Non-Interactive Aurora Lighting */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="aurora-orb-1 absolute -top-36 left-1/4 w-[520px] h-[520px] rounded-full bg-blue-600/10 blur-[130px]" />
        <div className="aurora-orb-2 absolute top-1/3 -right-32 w-[460px] h-[460px] rounded-full bg-indigo-600/10 blur-[130px]" />
        <div className="aurora-orb-3 absolute -bottom-40 left-1/3 w-[480px] h-[480px] rounded-full bg-purple-600/8 blur-[140px]" />
      </div>

      {/* Main Content Layer */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}

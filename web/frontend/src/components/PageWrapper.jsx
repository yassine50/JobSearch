export default function PageWrapper({ children }) {
  return (
    <div className="relative min-h-screen bg-[#050811] bg-grid-pattern overflow-x-hidden">
      {/* Ambient Non-Interactive Aurora Lighting (GPU-composited radial gradients to avoid continuous blur repaint lag) */}
      <div
        className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
        style={{
          background:
            'radial-gradient(circle 420px at 28% 8%, rgba(37, 99, 235, 0.09), transparent 70%), radial-gradient(circle 380px at 88% 36%, rgba(79, 70, 229, 0.08), transparent 70%), radial-gradient(circle 400px at 38% 92%, rgba(147, 51, 234, 0.06), transparent 70%)',
          transform: 'translateZ(0)',
        }}
      />

      {/* Main Content Layer */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}

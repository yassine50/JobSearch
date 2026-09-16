
export default function LoadingSpinner({ label = 'Loading...' }) {
  return (
    <div className="flex items-center gap-3 text-slate-400 text-sm">
      <span className="spinner" />
      {label}
    </div>
  )
}

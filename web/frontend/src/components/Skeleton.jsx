
export function SkeletonRow() {
  return (
    <tr className="border-b border-slate-700/50 animate-pulse">
      {[200, 150, 120, 80, 100, 80, 140].map((w, i) => (
        <td key={i} className="py-3.5 pr-4">
          <div className="h-3.5 bg-slate-700 rounded-full" style={{ width: w }} />
        </td>
      ))}
    </tr>
  )
}

export function SkeletonCard() {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5 animate-pulse space-y-3">
      <div className="flex justify-between items-start">
        <div className="space-y-2 flex-1">
          <div className="h-3.5 bg-slate-700 rounded-full w-3/4"/>
          <div className="h-3 bg-slate-700/60 rounded-full w-1/2"/>
        </div>
        <div className="h-7 w-14 bg-slate-700 rounded-full ml-3"/>
      </div>
      <div className="h-3 bg-slate-700/50 rounded-full w-full"/>
      <div className="h-3 bg-slate-700/30 rounded-full w-2/3"/>
      <div className="flex gap-1.5 pt-1">
        {[60,80,50].map(w=><div key={w} className="h-5 bg-slate-700 rounded-full" style={{width:w}}/>)}
      </div>
    </div>
  )
}

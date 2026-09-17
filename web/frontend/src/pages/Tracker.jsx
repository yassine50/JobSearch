import { useEffect, useState } from 'react'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import client from '../api/client.js'
import { Plus, Trash2, ExternalLink, StickyNote, Mail, CheckCircle, XCircle, ChevronDown } from 'lucide-react'

const COLUMNS = [
  { key:'applied',   label:'📤 Applied',   color:'border-blue-700'   },
  { key:'interview', label:'📞 Interview',  color:'border-purple-700' },
  { key:'offer',     label:'🤝 Offer',      color:'border-emerald-700'},
  { key:'rejected',  label:'❌ Rejected',   color:'border-red-700'    },
  { key:'accepted',  label:'🏆 Accepted',   color:'border-yellow-700' },
]

function EmailBadge({ email }) {
  return (
    <div className="flex items-center gap-1 text-xs text-slate-400 mt-1">
      {email.status==='sent'
        ? <CheckCircle size={10} className="text-emerald-400 shrink-0"/>
        : <XCircle size={10} className="text-red-400 shrink-0"/>}
      <span className="truncate" title={email.subject}>{email.subject}</span>
    </div>
  
  )
}

export default function Tracker() {
  const [apps, setApps]       = useState([])
  const [editing, setEditing] = useState(null)
  const [notes, setNotes]     = useState('')
  const [adding, setAdding]   = useState(false)
  const [form, setForm]       = useState({ title:'', company:'', location:'', url:'', notes:'' })
  const [expanded, setExpanded] = useState({})

  const load = () => client.get('/tracker').then(r=>setApps(r.data)).catch(()=>{})
  useEffect(()=>{ load() },[])

  const addApp = async () => {
    if (!form.title) return
    await client.post('/tracker', form)
    setForm({ title:'', company:'', location:'', url:'', notes:'' })
    setAdding(false); load()
  }

  const moveStatus = async (id, status) => {
    await client.patch(`/tracker/${id}`, { status })
    setApps(a => a.map(x => x.id===id ? {...x, status} : x))
  }

  const saveNotes = async () => {
    await client.patch(`/tracker/${editing}`, { notes })
    setApps(a => a.map(x => x.id===editing ? {...x, notes} : x))
    setEditing(null)
  }

  const del = async (id) => {
    await client.delete(`/tracker/${id}`)
    setApps(a => a.filter(x=>x.id!==id))
  }

  const byStatus = key => apps.filter(a=>a.status===key)
  const totalEmails = apps.reduce((sum,a)=>sum+(a.emails?.length||0),0)

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar/>
      <main className="ml-60 flex-1 p-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">📋 Application Tracker</h1>
            <p className="text-slate-400 text-sm mt-1">{apps.length} applications · {totalEmails} emails sent</p>
          </div>
          <button onClick={()=>setAdding(true)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
            <Plus size={16}/> Add Manually
          </button>
        </div>

        {/* Stats */}
        <div className="flex gap-3 mb-6 flex-wrap">
          {COLUMNS.map(c=>(
            <div key={c.key} className={`bg-slate-800 border ${c.color} rounded-xl px-4 py-3 text-center min-w-[90px]`}>
              <div className="text-xl font-bold">{byStatus(c.key).length}</div>
              <div className="text-xs text-slate-400">{c.label.split(' ').slice(1).join(' ')}</div>
            </div>
          ))}
          <div className="bg-slate-800 border border-blue-600 rounded-xl px-4 py-3 text-center min-w-[90px]">
            <div className="text-xl font-bold text-blue-400">{totalEmails}</div>
            <div className="text-xs text-slate-400">Emails Sent</div>
          </div>
        </div>

        {/* Kanban */}
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
          {COLUMNS.map(col=>(
            <div key={col.key} className={`bg-slate-800 border ${col.color} rounded-2xl p-4 min-h-[300px]`}>
              <h3 className="font-semibold text-sm mb-3">
                {col.label} <span className="text-slate-500">({byStatus(col.key).length})</span>
              </h3>
              <div className="space-y-3">
                {byStatus(col.key).map(a=>(
                  <div key={a.id} className="bg-slate-900 border border-slate-700 rounded-xl p-3 hover:border-slate-500 transition">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-1">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{a.title}</p>
                        <p className="text-xs text-slate-400 truncate">{a.company}</p>
                      </div>
                      {a.match_score>0 && <ScoreBadge score={a.match_score}/>}
                    </div>

                    {/* Notes preview */}
                    {a.notes && <p className="text-xs text-slate-500 italic mt-1 line-clamp-2">{a.notes}</p>}

                    {/* Emails sent section */}
                    {a.emails && a.emails.length > 0 && (
                      <div className="mt-2 border-t border-slate-700 pt-2">
                        <button onClick={()=>setExpanded(e=>({...e,[a.id]:!e[a.id]}))}
                          className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition">
                          <Mail size={11}/>
                          {a.emails.length} email{a.emails.length>1?'s':''} sent
                          <ChevronDown size={11} className={`transition-transform ${expanded[a.id]?'rotate-180':''}`}/>
                        </button>
                        {expanded[a.id] && (
                          <div className="mt-1.5 space-y-0.5 max-h-24 overflow-y-auto">
                            {a.emails.map(e=><EmailBadge key={e.id} email={e}/>)}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Action buttons */}
                    <div className="flex items-center gap-2 mt-2">
                      {a.url && <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 transition"><ExternalLink size={12}/></a>}
                      <button onClick={()=>{setEditing(a.id);setNotes(a.notes||'')}} className="text-slate-400 hover:text-white transition"><StickyNote size={12}/></button>
                      <button onClick={()=>del(a.id)} className="text-red-400 hover:text-red-300 transition ml-auto"><Trash2 size={12}/></button>
                    </div>

                    {/* Move buttons */}
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {COLUMNS.filter(c=>c.key!==col.key).map(c=>(
                        <button key={c.key} onClick={()=>moveStatus(a.id,c.key)}
                          className="text-xs bg-slate-700 hover:bg-slate-600 px-1.5 py-0.5 rounded transition">
                          →{c.label.split(' ').slice(1).join(' ')}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* Add Modal */}
      {adding && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={()=>setAdding(false)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-md" onClick={e=>e.stopPropagation()}>
            <h3 className="font-bold text-lg mb-4">Add Application</h3>
            <div className="space-y-3">
              {[['Job Title *','title'],['Company','company'],['Location','location'],['Job URL','url']].map(([label,key])=>(
                <div key={key}>
                  <label className="text-xs text-slate-400 mb-1 block">{label}</label>
                  <input value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"/>
                </div>
              ))}
              <div>
                <label className="text-xs text-slate-400 mb-1 block">Notes</label>
                <textarea value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})} rows={3}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition resize-none"/>
              </div>
              <div className="flex gap-2 pt-2">
                <button onClick={()=>setAdding(false)} className="flex-1 bg-slate-700 hover:bg-slate-600 py-2 rounded-lg text-sm transition">Cancel</button>
                <button onClick={addApp} className="flex-1 bg-blue-600 hover:bg-blue-500 py-2 rounded-lg text-sm font-semibold transition">Add</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Notes Modal */}
      {editing && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={()=>setEditing(null)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-sm" onClick={e=>e.stopPropagation()}>
            <h3 className="font-bold mb-3">📝 Notes</h3>
            <textarea value={notes} onChange={e=>setNotes(e.target.value)} rows={5}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition resize-none mb-3"/>
            <div className="flex gap-2">
              <button onClick={()=>setEditing(null)} className="flex-1 bg-slate-700 hover:bg-slate-600 py-2 rounded-lg text-sm transition">Cancel</button>
              <button onClick={saveNotes} className="flex-1 bg-blue-600 hover:bg-blue-500 py-2 rounded-lg text-sm font-semibold transition">Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  </PageWrapper>
  )
}

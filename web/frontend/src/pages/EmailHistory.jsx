import { useEffect, useState } from 'react'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import EmailCalendarView from '../components/EmailCalendarView.jsx'
import client from '../api/client.js'
import { Mail, CheckCircle, XCircle, Eye, AlertTriangle, RefreshCw, Filter, Calendar, List } from 'lucide-react'

const TEMPLATE_LABELS = {
  application:'Job Application', auto_apply:'Direct Application', cold_outreach:'Cold Outreach',
  follow_up:'Follow-Up', thank_you:'Thank You', cover_letter:'Cover Letter', custom:'Custom'
}

export default function EmailHistory() {
  const [logs, setLogs]         = useState([])
  const [filter, setFilter]     = useState('all')
  const [viewing, setViewing]   = useState(null)
  const [viewMode, setViewMode] = useState('calendar') // 'calendar' | 'table'

  useEffect(() => {
    client.get('/email/history').then(r=>setLogs(r.data)).catch(()=>{})
  }, [])

  const filteredLogs = logs.filter(l => {
    if (filter === 'all') return true
    if (filter === 'sent') return l.status === 'sent'
    if (filter === 'bounced') return l.status === 'bounced'
    if (filter === 'follow_up') return l.template_type === 'follow_up'
    return true
  })

  const countSent = logs.filter(l => l.status === 'sent').length
  const countBounced = logs.filter(l => l.status === 'bounced').length
  const countFollowUps = logs.filter(l => l.template_type === 'follow_up').length

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2.5">
              <span>📧 Email Outbox & Activity Tracker</span>
            </h1>
            <p className="text-xs text-slate-400 mt-1">Daily calendar analytics, sent email audit log, and recruiter bounce tracking.</p>
          </div>

          {/* Primary View Toggle: Calendar vs Table */}
          <div className="flex items-center gap-2">
            <div className="flex bg-slate-800 border border-slate-700 rounded-xl p-1 text-xs font-semibold shadow-sm">
              <button
                onClick={() => setViewMode('calendar')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                  viewMode === 'calendar'
                    ? 'bg-blue-600 text-white shadow'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <Calendar size={13} />
                <span>Daily Calendar</span>
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                  viewMode === 'table'
                    ? 'bg-blue-600 text-white shadow'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <List size={13} />
                <span>Audit Table ({logs.length})</span>
              </button>
            </div>
          </div>
        </div>

        {viewMode === 'calendar' ? (
          <EmailCalendarView />
        ) : (
          <div>
            {/* Filter tabs for Table view */}
            <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
              <div className="flex bg-slate-800 border border-slate-700 rounded-xl p-1 text-xs font-medium">
                {[
                  { id: 'all', label: `All (${logs.length})` },
                  { id: 'sent', label: `Sent (${countSent})` },
                  { id: 'bounced', label: `Bounced (${countBounced})` },
                  { id: 'follow_up', label: `Follow-Ups (${countFollowUps})` },
                ].map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setFilter(tab.id)}
                    className={`px-3 py-1.5 rounded-lg transition cursor-pointer ${
                      filter === tab.id ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <span className="text-xs text-slate-400">Showing {filteredLogs.length} of {logs.length} logged email(s)</span>
            </div>

        {filteredLogs.length === 0 ? (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-16 text-center">
            <Mail size={48} className="mx-auto mb-4 text-slate-600"/>
            <p className="text-slate-400">No emails matching filter.</p>
            <p className="text-slate-600 text-sm mt-1">Emails you send and their delivery status will appear here.</p>
          </div>
        ) : (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 fade-in shadow-sm">
            <p className="text-slate-400 text-xs mb-4">Showing {filteredLogs.length} of {logs.length} logged email(s)</p>
            <div className="overflow-x-auto -mx-2 px-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-700">
                    {['Status','To Recruiter','Subject','Template Type','Sent At','Action'].map(h=>(
                      <th key={h} className="pb-3 pr-4 font-medium text-xs">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredLogs.map(l=>(
                    <tr key={l.id} className="border-b border-slate-700/50 hover:bg-slate-700/20 transition">
                      <td className="py-3 pr-4 whitespace-nowrap">
                        {l.status === 'sent' ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-emerald-950/80 border border-emerald-800/60 text-emerald-300 text-xs font-medium">
                            <CheckCircle size={13} className="text-emerald-400"/>
                            Sent
                          </span>
                        ) : l.status === 'bounced' ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-red-950/80 border border-red-800/60 text-red-300 text-xs font-medium" title="Message bloqué ou Adresse introuvable">
                            <AlertTriangle size={13} className="text-red-400"/>
                            Bounced
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-amber-950/80 border border-amber-800/60 text-amber-300 text-xs font-medium">
                            <XCircle size={13} className="text-amber-400"/>
                            {l.status}
                          </span>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="font-medium text-slate-200">{l.to_name}</div>
                        <div className="text-xs text-slate-400 font-mono">{l.to_email}</div>
                      </td>
                      <td className="py-3 pr-4 max-w-xs">
                        <div className="truncate text-slate-300" title={l.subject}>{l.subject}</div>
                      </td>
                      <td className="py-3 pr-4">
                        <span className={`text-xs px-2 py-0.5 rounded border ${
                          l.template_type === 'follow_up' ? 'bg-blue-950 text-blue-300 border-blue-800/60' :
                          l.template_type === 'auto_apply' ? 'bg-purple-950 text-purple-300 border-purple-800/60' :
                          'bg-slate-700/60 text-slate-300 border-slate-600'
                        }`}>
                          {TEMPLATE_LABELS[l.template_type] || l.template_type}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-slate-400 text-xs whitespace-nowrap">
                        {new Date(l.sent_at).toLocaleString()}
                      </td>
                      <td className="py-3">
                        <button onClick={()=>setViewing(l)}
                          className="text-slate-400 hover:text-white transition cursor-pointer p-1" title="View Full Email Content">
                          <Eye size={15}/>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        </div>
      )}
      </main>

      {/* View email modal */}
      {viewing && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={()=>setViewing(null)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={e=>e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="font-bold text-base text-slate-100">{viewing.subject}</h3>
                <p className="text-slate-400 text-xs mt-0.5">To: {viewing.to_name} &lt;{viewing.to_email}&gt;</p>
              </div>
              <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                viewing.status==='sent' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' :
                viewing.status==='bounced' ? 'bg-red-950 text-red-300 border border-red-800' :
                'bg-amber-950 text-amber-300 border border-amber-800'
              }`}>
                {viewing.status === 'bounced' ? 'Bounced / Bloqué' : viewing.status}
              </span>
            </div>
            <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans bg-slate-900 rounded-xl p-4 leading-relaxed border border-slate-700/80">
              {viewing.body}
            </pre>
            <button onClick={()=>setViewing(null)} className="mt-4 w-full bg-slate-700 hover:bg-slate-600 rounded-xl py-2 text-sm font-medium transition cursor-pointer">Close</button>
          </div>
        </div>
      )}
    </div>
  </PageWrapper>
  )
}

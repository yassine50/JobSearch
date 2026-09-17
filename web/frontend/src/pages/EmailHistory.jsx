import { useEffect, useState } from 'react'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import client from '../api/client.js'
import { Mail, CheckCircle, XCircle, Eye } from 'lucide-react'

const TEMPLATE_LABELS = {
  application:'Job Application', cold_outreach:'Cold Outreach',
  follow_up:'Follow-Up', thank_you:'Thank You', cover_letter:'Cover Letter', custom:'Custom'
}

export default function EmailHistory() {
  const [logs, setLogs]     = useState([])
  const [viewing, setViewing] = useState(null)

  useEffect(() => {
    client.get('/email/history').then(r=>setLogs(r.data)).catch(()=>{})
  }, [])

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8">
        <h1 className="text-2xl font-bold mb-6">📧 Email History</h1>

        {logs.length === 0 ? (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-16 text-center">
            <Mail size={48} className="mx-auto mb-4 text-slate-600"/>
            <p className="text-slate-400">No emails sent yet.</p>
            <p className="text-slate-600 text-sm mt-1">Emails you send from the app will appear here.</p>
          </div>
        ) : (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 fade-in">
            <p className="text-slate-400 text-sm mb-4">{logs.length} emails sent</p>
            <div className="overflow-x-auto -mx-2 px-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-700">
                    {['Status','To','Subject','Type','Sent At',''].map(h=>(
                      <th key={h} className="pb-3 pr-4 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {logs.map(l=>(
                    <tr key={l.id} className="border-b border-slate-700/50 hover:bg-slate-700/20 transition">
                      <td className="py-3 pr-4">
                        {l.status==='sent'
                          ? <CheckCircle size={16} className="text-emerald-400"/>
                          : <XCircle size={16} className="text-red-400"/>}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="font-medium">{l.to_name}</div>
                        <div className="text-xs text-slate-400">{l.to_email}</div>
                      </td>
                      <td className="py-3 pr-4 max-w-xs">
                        <div className="truncate" title={l.subject}>{l.subject}</div>
                      </td>
                      <td className="py-3 pr-4">
                        <span className="bg-slate-700 text-xs px-2 py-0.5 rounded">
                          {TEMPLATE_LABELS[l.template_type] || l.template_type}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-slate-400 text-xs">
                        {new Date(l.sent_at).toLocaleString()}
                      </td>
                      <td className="py-3">
                        <button onClick={()=>setViewing(l)}
                          className="text-slate-400 hover:text-white transition">
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
      </main>

      {/* View email modal */}
      {viewing && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={()=>setViewing(null)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={e=>e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="font-bold">{viewing.subject}</h3>
                <p className="text-slate-400 text-sm">To: {viewing.to_name} &lt;{viewing.to_email}&gt;</p>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full ${viewing.status==='sent'?'bg-emerald-900 text-emerald-300':'bg-red-900 text-red-300'}`}>
                {viewing.status}
              </span>
            </div>
            <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans bg-slate-900 rounded-lg p-4 leading-relaxed">
              {viewing.body}
            </pre>
            <button onClick={()=>setViewing(null)} className="mt-4 w-full bg-slate-700 hover:bg-slate-600 rounded-lg py-2 text-sm transition">Close</button>
          </div>
        </div>
      )}
    </div>
  </PageWrapper>
  )
}

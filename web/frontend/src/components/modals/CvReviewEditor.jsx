import { useState } from 'react'
import { Plus, Trash2, ChevronDown, ChevronRight, RotateCcw, Save, Loader2 } from 'lucide-react'

/*
 * Review-before-download editor: shows exactly what the engine extracted from the user's CV file
 * and lets them fix it. The saved structure is used for every future tailoring of this CV.
 */

const inputCls =
  'w-full px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 ' +
  'placeholder-slate-600 focus:outline-none focus:border-purple-500/60'
const labelCls = 'text-[10px] font-semibold uppercase tracking-wider text-slate-500'

const linesToList = (s) => (s || '').split('\n').map(x => x.trim()).filter(Boolean)
const listToLines = (l) => (l || []).join('\n')
const commaToList = (s) => (s || '').split(',').map(x => x.trim()).filter(Boolean)

function Field({ label, value, onChange, placeholder }) {
  return (
    <label className="space-y-1 block">
      <span className={labelCls}>{label}</span>
      <input className={inputCls} value={value || ''} placeholder={placeholder} onChange={e => onChange(e.target.value)} />
    </label>
  )
}

function Area({ label, value, onChange, rows = 3, placeholder }) {
  return (
    <label className="space-y-1 block">
      <span className={labelCls}>{label}</span>
      <textarea className={`${inputCls} resize-y leading-relaxed`} rows={rows} value={value || ''}
        placeholder={placeholder} onChange={e => onChange(e.target.value)} />
    </label>
  )
}

function Section({ title, count, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60">
      <button type="button" onClick={() => setOpen(o => !o)}
        className="w-full px-3 py-2 flex items-center justify-between text-left cursor-pointer">
        <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {title}
        </span>
        {count != null && <span className="text-[10px] text-slate-500">{count}</span>}
      </button>
      {open && <div className="px-3 pb-3 space-y-2.5">{children}</div>}
    </div>
  )
}

function EntryList({ entries, onChange, kind }) {
  const isEdu = kind === 'education'
  const update = (i, patch) => onChange(entries.map((e, j) => (j === i ? { ...e, ...patch } : e)))
  const remove = (i) => onChange(entries.filter((_, j) => j !== i))
  const add = () => onChange([...entries, { title: '', org: '', location: '', date_text: '', bullets: [], stack: [], links: [], kind }])
  return (
    <>
      {entries.map((e, i) => (
        <div key={i} className="p-2.5 rounded-lg border border-slate-800 bg-slate-900/60 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-300 truncate">{e.title || e.org || `Entry ${i + 1}`}</span>
            <button type="button" onClick={() => remove(i)} title="Remove entry"
              className="p-1 text-slate-500 hover:text-red-400 cursor-pointer"><Trash2 size={13} /></button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label={isEdu ? 'Degree' : kind === 'project' ? 'Project title' : 'Job title'} value={e.title} onChange={v => update(i, { title: v })} />
            <Field label={isEdu ? 'School' : 'Company / organisation'} value={e.org} onChange={v => update(i, { org: v })} />
            <Field label="Dates" value={e.date_text} placeholder="Mar 2025 – Sep 2025" onChange={v => update(i, { date_text: v })} />
            <Field label="Location" value={e.location} onChange={v => update(i, { location: v })} />
          </div>
          <Area label={isEdu ? 'Details (one per line)' : 'Bullet points (one per line)'} rows={Math.min(8, Math.max(2, (e.bullets || []).length + 1))}
            value={listToLines(e.bullets)} onChange={v => update(i, { bullets: v.split('\n') })} />
          {!isEdu && (
            <Field label="Technologies (comma separated)" value={(e.stack || []).join(', ')}
              onChange={v => update(i, { stack: commaToList(v) })} />
          )}
        </div>
      ))}
      <button type="button" onClick={add}
        className="text-[11px] font-semibold text-purple-300 hover:text-purple-200 flex items-center gap-1 cursor-pointer">
        <Plus size={12} /> Add {isEdu ? 'education' : kind === 'project' ? 'project' : 'experience'}
      </button>
    </>
  )
}

export default function CvReviewEditor({ initialCv, saving, onSave, onReset, reviewed }) {
  const [cv, setCv] = useState(() => ({
    ...initialCv,
    contact: { ...(initialCv?.contact || {}) },
    links: { ...(initialCv?.links || {}) },
    experience: initialCv?.experience || [],
    projects: initialCv?.projects || [],
    education: initialCv?.education || [],
    skill_groups: (initialCv?.skill_groups?.length
      ? initialCv.skill_groups
      : (initialCv?.skills?.length ? [['Skills', initialCv.skills]] : [])),
    languages: initialCv?.languages || [],
    certifications: initialCv?.certifications || [],
  }))

  const set = (patch) => setCv(c => ({ ...c, ...patch }))
  const setContact = (k, v) => setCv(c => ({ ...c, contact: { ...c.contact, [k]: v } }))
  const setLink = (k, v) => setCv(c => ({ ...c, links: { ...c.links, [k]: v } }))

  const handleSave = () => {
    const clean = (entries) => entries.map(e => ({ ...e, bullets: (e.bullets || []).map(b => b.trim()).filter(Boolean) }))
    onSave({
      ...cv,
      experience: clean(cv.experience),
      projects: clean(cv.projects),
      education: clean(cv.education),
      skill_groups: cv.skill_groups.filter(([c, items]) => (items || []).length),
      skills: [],
      languages: cv.languages.filter(l => (l.name_en || '').trim()),
    })
  }

  return (
    <div className="space-y-2.5">
      <Section title="Identity & contact">
        <div className="grid grid-cols-2 gap-2">
          <Field label="Full name" value={cv.name} onChange={v => set({ name: v })} />
          <Field label="Headline" value={cv.headline} onChange={v => set({ headline: v })} />
          <Field label="Email" value={cv.contact.email} onChange={v => setContact('email', v)} />
          <Field label="Phone" value={cv.contact.phone} onChange={v => setContact('phone', v)} />
          <Field label="Location" value={cv.contact.location} onChange={v => setContact('location', v)} />
          <Field label="LinkedIn" value={cv.links.linkedin} onChange={v => setLink('linkedin', v)} />
          <Field label="GitHub" value={cv.links.github} onChange={v => setLink('github', v)} />
          <Field label="Portfolio" value={cv.links.portfolio} onChange={v => setLink('portfolio', v)} />
        </div>
        <Area label="Summary" rows={4} value={cv.summary} onChange={v => set({ summary: v })} />
      </Section>

      <Section title="Experience" count={cv.experience.length}>
        <EntryList kind="job" entries={cv.experience} onChange={v => set({ experience: v })} />
      </Section>

      <Section title="Projects" count={cv.projects.length} defaultOpen={cv.projects.length > 0}>
        <EntryList kind="project" entries={cv.projects} onChange={v => set({ projects: v })} />
      </Section>

      <Section title="Education" count={cv.education.length}>
        <EntryList kind="education" entries={cv.education} onChange={v => set({ education: v })} />
      </Section>

      <Section title="Skills" count={cv.skill_groups.reduce((n, [, it]) => n + (it || []).length, 0)}>
        {cv.skill_groups.map(([cat, items], i) => (
          <div key={i} className="flex gap-2 items-end">
            <div className="w-1/3"><Field label="Category" value={cat}
              onChange={v => set({ skill_groups: cv.skill_groups.map((g, j) => (j === i ? [v, g[1]] : g)) })} /></div>
            <div className="flex-1"><Field label="Skills (comma separated)" value={(items || []).join(', ')}
              onChange={v => set({ skill_groups: cv.skill_groups.map((g, j) => (j === i ? [g[0], commaToList(v)] : g)) })} /></div>
            <button type="button" onClick={() => set({ skill_groups: cv.skill_groups.filter((_, j) => j !== i) })}
              className="p-1.5 mb-0.5 text-slate-500 hover:text-red-400 cursor-pointer"><Trash2 size={13} /></button>
          </div>
        ))}
        <button type="button" onClick={() => set({ skill_groups: [...cv.skill_groups, ['', []]] })}
          className="text-[11px] font-semibold text-purple-300 hover:text-purple-200 flex items-center gap-1 cursor-pointer">
          <Plus size={12} /> Add skill category
        </button>
      </Section>

      <Section title="Certifications & languages" defaultOpen={false}
        count={`${cv.certifications.length} · ${cv.languages.length}`}>
        <Area label="Certifications (one per line)" rows={3} value={listToLines(cv.certifications)}
          onChange={v => set({ certifications: linesToList(v) })} />
        {cv.languages.map((l, i) => (
          <div key={i} className="flex gap-2 items-end">
            <div className="flex-1"><Field label="Language" value={l.name_en}
              onChange={v => set({ languages: cv.languages.map((x, j) => (j === i ? { ...x, name_en: v, name_fr: v } : x)) })} /></div>
            <div className="flex-1"><Field label="Level" value={l.level_en} placeholder="Fluent (C1)"
              onChange={v => set({ languages: cv.languages.map((x, j) => (j === i ? { ...x, level_en: v, level_fr: v } : x)) })} /></div>
            <button type="button" onClick={() => set({ languages: cv.languages.filter((_, j) => j !== i) })}
              className="p-1.5 mb-0.5 text-slate-500 hover:text-red-400 cursor-pointer"><Trash2 size={13} /></button>
          </div>
        ))}
        <button type="button" onClick={() => set({ languages: [...cv.languages, { name_en: '', level_en: '' }] })}
          className="text-[11px] font-semibold text-purple-300 hover:text-purple-200 flex items-center gap-1 cursor-pointer">
          <Plus size={12} /> Add language
        </button>
      </Section>

      <div className="flex items-center justify-between pt-1">
        {reviewed ? (
          <button type="button" onClick={onReset} disabled={saving}
            className="text-[11px] font-semibold text-slate-400 hover:text-white flex items-center gap-1 cursor-pointer disabled:opacity-50">
            <RotateCcw size={12} /> Reset to automatic extraction
          </button>
        ) : <span />}
        <button type="button" onClick={handleSave} disabled={saving}
          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          Save & re-tailor
        </button>
      </div>
    </div>
  )
}

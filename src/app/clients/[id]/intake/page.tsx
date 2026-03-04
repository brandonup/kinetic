// src/app/clients/[id]/intake/page.tsx
'use client'

import { useState, use } from 'react'
import { useRouter } from 'next/navigation'

// ─── Field wrapper ────────────────────────────────────────────────────────────

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <div>
        <label className="text-xs font-medium text-content-primary">{label}</label>
        <p className="text-xs text-content-muted mt-0.5">{hint}</p>
      </div>
      {children}
    </div>
  )
}

// ─── Shared input classes ─────────────────────────────────────────────────────

const inputCls =
  'w-full bg-bg-base border border-border-subtle rounded px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-accent-teal transition-colors'

// ─── Form interface ───────────────────────────────────────────────────────────

interface IntakeForm {
  goals: string[]
  constraints: string[]
  pain_points: string[]
  industry_context: string
  decision_makers: string
  current_tools: string
  success_definition: string
  timeline: string
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function IntakePage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const router = useRouter()

  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<IntakeForm>({
    goals: ['', ''],
    constraints: [''],
    pain_points: [''],
    industry_context: '',
    decision_makers: '',
    current_tools: '',
    success_definition: '',
    timeline: '',
  })

  function setGoal(i: number, value: string) {
    setForm(f => ({ ...f, goals: f.goals.map((g, j) => (j === i ? value : g)) }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const res = await fetch(`/api/clients/${id}/intake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (res.ok) {
        router.push(`/clients/${id}`)
      } else {
        const data = await res.json() as { error?: string }
        alert(data.error ?? 'Failed to save intake. Please try again.')
        setSubmitting(false)
      }
    } catch {
      alert('Network error. Please try again.')
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div>
        <a
          href={`/clients/${id}`}
          className="text-xs text-content-secondary hover:text-accent-teal transition-colors"
        >
          ← Client Context
        </a>
        <h1 className="text-lg font-semibold text-content-primary mt-2">Client Intake</h1>
        <p className="text-xs text-content-muted mt-0.5">
          Capture structured context that persists across all interactions with this client.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Goals */}
        <Field
          label="Primary Goals"
          hint="What does this client most want to achieve from this engagement?"
        >
          <div className="space-y-2">
            {form.goals.map((g, i) => (
              <input
                key={i}
                value={g}
                onChange={e => setGoal(i, e.target.value)}
                placeholder={`Goal ${i + 1}…`}
                className={inputCls}
              />
            ))}
            <button
              type="button"
              onClick={() => setForm(f => ({ ...f, goals: [...f.goals, ''] }))}
              className="text-xs text-accent-teal hover:underline font-mono"
            >
              + add goal
            </button>
          </div>
        </Field>

        {/* Constraints */}
        <Field
          label="Constraints"
          hint="Budget, timeline, technical, or political limits on what's possible."
        >
          <input
            value={form.constraints[0]}
            onChange={e => setForm(f => ({ ...f, constraints: [e.target.value] }))}
            placeholder="e.g., $50k budget ceiling, no new software vendors this FY"
            className={inputCls}
          />
        </Field>

        {/* Pain points */}
        <Field
          label="Pain Points"
          hint="What is actively frustrating them right now?"
        >
          <input
            value={form.pain_points[0]}
            onChange={e => setForm(f => ({ ...f, pain_points: [e.target.value] }))}
            placeholder="e.g., Manual reporting takes 3 days per week"
            className={inputCls}
          />
        </Field>

        {/* Industry context */}
        <Field
          label="Industry Context"
          hint="What's the competitive or market context they operate in?"
        >
          <textarea
            value={form.industry_context}
            onChange={e => setForm(f => ({ ...f, industry_context: e.target.value }))}
            placeholder="e.g., Mid-sized regional bank under pressure from fintech challengers…"
            rows={3}
            className={`${inputCls} resize-none`}
          />
        </Field>

        {/* Decision makers */}
        <Field
          label="Decision Makers"
          hint="Who controls the budget and final sign-off?"
        >
          <input
            value={form.decision_makers}
            onChange={e => setForm(f => ({ ...f, decision_makers: e.target.value }))}
            placeholder="e.g., CEO + CFO approval required for >$25k"
            className={inputCls}
          />
        </Field>

        {/* Current tools */}
        <Field
          label="Current Tools & Stack"
          hint="What tools, systems, and vendors are they already using?"
        >
          <input
            value={form.current_tools}
            onChange={e => setForm(f => ({ ...f, current_tools: e.target.value }))}
            placeholder="e.g., Salesforce, Slack, Excel, no modern data stack"
            className={inputCls}
          />
        </Field>

        {/* Success definition */}
        <Field
          label="Success Definition"
          hint="How will they know this engagement worked? Be specific."
        >
          <input
            value={form.success_definition}
            onChange={e => setForm(f => ({ ...f, success_definition: e.target.value }))}
            placeholder="e.g., 20% reduction in manual reporting time within 90 days"
            className={inputCls}
          />
        </Field>

        {/* Timeline */}
        <Field
          label="Timeline & Deadlines"
          hint="When do they need results? Any hard external deadlines?"
        >
          <input
            value={form.timeline}
            onChange={e => setForm(f => ({ ...f, timeline: e.target.value }))}
            placeholder="e.g., Board presentation Q2, soft launch by end of March"
            className={inputCls}
          />
        </Field>

        {/* Submit */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="w-full px-4 py-3 bg-accent-teal text-bg-base text-sm font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {submitting ? 'Saving & embedding···' : 'Save Intake'}
          </button>
          <p className="text-xs text-content-muted text-center mt-2">
            Responses are embedded and stored as persistent client memory.
          </p>
        </div>
      </form>
    </div>
  )
}

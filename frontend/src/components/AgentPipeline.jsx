import { Fragment } from 'react'
import { Loader2, CheckCircle, ArrowRight, MessageSquare, HelpCircle, AlertTriangle } from 'lucide-react'

const AGENT_LABELS = {
  planner: 'Planner', statute_researcher: 'Statute', case_analyst: 'Case Law',
  web_verifier: 'Web Check', synthesizer: 'Merge',
}

export { AGENT_LABELS }

const MESSAGE_STYLE = {
  finding: { Icon: MessageSquare, color: 'var(--text-muted)', bg: 'var(--bg-card)', label: 'shared a finding' },
  request: { Icon: HelpCircle, color: '#ca8a04', bg: 'rgba(234,179,8,.08)', label: 'asked for help' },
  challenge: { Icon: AlertTriangle, color: 'var(--color-error)', bg: 'var(--color-error-bg)', label: 'raised a challenge' },
  clarify: { Icon: HelpCircle, color: 'var(--primary)', bg: 'var(--primary-light, rgba(99,102,241,.08))', label: 'asked to clarify' },
}

function agentDisplayLabel(id) {
  return AGENT_LABELS[id] || id
}

function AgentMessageBubble({ msg }) {
  if (msg.type === 'done') return null
  const style = MESSAGE_STYLE[msg.type] || MESSAGE_STYLE.finding
  const Icon = style.Icon
  const target = msg.to === '*' ? 'the team' : agentDisplayLabel(msg.to)

  return (
    <div
      className="flex items-start gap-2 px-2.5 py-1.5 rounded-[5px]"
      style={{ background: style.bg, border: `1px solid ${style.color}22` }}
    >
      <Icon size={12} className="flex-shrink-0 mt-0.5" style={{ color: style.color }} />
      <div className="min-w-0">
        <p className="m-0 text-[10.5px]">
          <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{agentDisplayLabel(msg.from)}</span>
          <span style={{ color: 'var(--text-muted)' }}> {style.label} to </span>
          <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{target}</span>
        </p>
        <p className="m-0 mt-0.5 text-[11px] leading-snug" style={{ color: 'var(--text-secondary)' }}>
          {msg.content}
        </p>
      </div>
    </div>
  )
}

export default function AgentPipeline({ agents, messages = [], coordinationSummary = '' }) {
  if (!agents.length) return null
  const visibleMessages = messages.filter(m => m.type !== 'done')

  return (
    <div
      className="flex flex-col gap-2 px-3 py-2 mb-2"
      style={{ background: 'var(--bg-soft)', borderRadius: 6, border: '1px solid var(--border-default)' }}
    >
      <div className="flex items-center gap-1 overflow-x-auto">
        <span
          className="text-[9px] font-bold uppercase mr-1 flex-shrink-0"
          style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}
        >
          Agents
        </span>
        {agents.map((a, i) => (
          <Fragment key={a.id}>
            {i > 0 && <ArrowRight size={10} className="flex-shrink-0" style={{ color: 'var(--border-input)', opacity: 0.5 }} />}
            <div
              className="flex items-center gap-1 px-2 py-0.5 rounded-[4px] flex-shrink-0"
              style={{
                background: a.status === 'active' ? 'var(--primary-light, rgba(99,102,241,.1))' : a.status === 'done' ? 'var(--accent-green-bg, rgba(34,197,94,.08))' : 'transparent',
                border: `1px solid ${a.status === 'active' ? 'var(--primary)' : a.status === 'done' ? 'var(--accent-green-border, rgba(34,197,94,.2))' : 'var(--border-default)'}`,
              }}
            >
              {a.status === 'active' && <Loader2 size={9} className="animate-spin" style={{ color: 'var(--primary)' }} />}
              {a.status === 'done' && <CheckCircle size={9} style={{ color: 'var(--accent-green, #16a34a)' }} />}
              <span className="text-[10px] font-medium" style={{
                color: a.status === 'active' ? 'var(--primary)' : a.status === 'done' ? 'var(--accent-green, #16a34a)' : 'var(--text-muted)',
              }}>
                {a.label}
              </span>
            </div>
          </Fragment>
        ))}
      </div>

      {visibleMessages.length > 0 && (
        <div className="flex flex-col gap-1.5 pt-1" style={{ borderTop: '1px solid var(--border-default)' }}>
          <span
            className="text-[9px] font-bold uppercase mt-1"
            style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}
          >
            Agent-to-agent
          </span>
          {visibleMessages.map((m, i) => <AgentMessageBubble key={i} msg={m} />)}
        </div>
      )}

      {coordinationSummary && (
        <p
          className="m-0 mt-1 pt-1.5 text-[10.5px] italic leading-snug"
          style={{ borderTop: '1px solid var(--border-default)', color: 'var(--text-muted)' }}
        >
          {coordinationSummary}
        </p>
      )}
    </div>
  )
}

export function ThinkingStep({ step, isLast, streaming }) {
  if (step.step === 'agent_roster' || step.step === 'agent_message') return null
  const agentLabel = step.agent ? AGENT_LABELS[step.agent] || step.agent : null

  return (
    <div className="flex items-center gap-2 py-1.5">
      {isLast && streaming ? (
        <Loader2 size={12} className="animate-spin flex-shrink-0" style={{ color: 'var(--primary)' }} />
      ) : (
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{ background: step.step === 'error' ? 'var(--color-error)' : 'var(--accent-green, #16a34a)' }}
        />
      )}
      {agentLabel && (
        <span
          className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-[3px] flex-shrink-0"
          style={{ background: 'var(--primary-light, rgba(99,102,241,.1))', color: 'var(--primary)', letterSpacing: '0.04em' }}
        >
          {agentLabel}
        </span>
      )}
      <span className="text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
        {step.detail}
      </span>
    </div>
  )
}

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, ChevronDown, Compass, ExternalLink, Loader2, Maximize2, MessageSquarePlus, Minimize2, Send, ShieldCheck, SkipForward, Sparkles, Volume2, X } from 'lucide-react'
import type { ChatAgent, ChatAgentType, ChatMessage, ChatThread, ChatServiceStatus, HandoverItem } from '../types'
import { createChatThread, fetchChatAgents, fetchChatStatus, fetchChatThreads, sendChatMessage } from '../services/api'

interface Props {
  userId: string
  projectId: string
  projectName: string
  handovers: HandoverItem[]
  currentPage: string
  forceOpen: boolean
  agentHint?: ChatAgentType
  onClose: () => void
  onNavigate: (tab: string) => void
}

export const ChatAssistant: React.FC<Props> = ({ userId, projectId, projectName, handovers, currentPage, forceOpen, agentHint = 'auto', onClose, onNavigate }) => {
  const [mode, setMode] = useState<'ask' | 'guide'>('ask')
  const [guideStep, setGuideStep] = useState(0)
  const [speechState, setSpeechState] = useState<'idle' | 'speaking' | 'paused' | 'unsupported'>('idle')
  const [agents, setAgents] = useState<ChatAgent[]>([])
  const [threads, setThreads] = useState<ChatThread[]>([])
  const [thread, setThread] = useState<ChatThread | null>(null)
  const [agentType, setAgentType] = useState<ChatAgentType>(agentHint)
  const [handoverId, setHandoverId] = useState('')
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState<ChatServiceStatus | null>(null)
  const [open, setOpen] = useState(forceOpen)
  const [expanded, setExpanded] = useState(forceOpen)
  const [projectChanged, setProjectChanged] = useState(false)
  const [welcomeDismissed, setWelcomeDismissed] = useState(() => userId ? localStorage.getItem(`synora_nova_welcome_dismissed_${userId}`) === 'true' : false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null)
  const loadedContextRef = useRef('')
  const loadingContextRef = useRef('')
  const threadKey = userId ? `synora_chat_thread_${userId}_${projectId || 'workspace'}` : ''
  const projectHandovers = useMemo(() => handovers.filter(h => h.project_id === projectId && ['draft', 'changes_requested'].includes(h.status)), [handovers, projectId])
  const currentAgent = agents.find(agent => agent.agent_type === agentType)
  const guideSteps = [
    { title: 'Welcome to Synora', tab: '', description: 'Synora helps your team preserve project knowledge, understand continuity gaps, and guide project recovery. Use Ask NOVA for questions or follow this tour to learn the workspace.' },
    { title: 'Dashboard overview', tab: 'dashboard', description: 'Start here for the workspace overview and the status your role is allowed to see. Use the navigation to move into a project or continuity module.' },
    { title: 'Projects', tab: 'projects', description: 'Create or select a project, upload its ZIP or documents, then review detected technologies, indexed files, analysis status, and evidence-backed findings.' },
    { title: 'Knowledge', tab: 'knowledge', description: 'Explore knowledge stored for your selected project. Use source details and citations to check where information came from and whether it has been verified.' },
    { title: 'Radar', tab: 'radar', description: 'Review project knowledge gaps and continuity signals. Open a finding to inspect its evidence and take an available review or remediation action.' },
    { title: 'Sentinel', tab: 'sentinel', description: 'Inspect continuity risks, their severity, supporting evidence, and recommended actions. What you can access depends on your authenticated role.' },
    { title: 'Environment Recreator', tab: 'recreator', description: 'Use detected project manifests and setup guidance to recreate an environment. Follow the checklist and ask NOVA about commands or errors; guidance alone does not mean a machine was validated.' },
    { title: 'Handovers', tab: 'handovers', description: 'Capture responsibilities, decisions, blockers, and work status in a handover. Information remains subject to the existing review and verification workflow.' },
  ]
  const activeGuideStep = guideSteps[guideStep]

  useEffect(() => { setOpen(forceOpen); setExpanded(forceOpen) }, [forceOpen])
  useEffect(() => {
    setWelcomeDismissed(userId ? localStorage.getItem(`synora_nova_welcome_dismissed_${userId}`) === 'true' : false)
  }, [userId])
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && open && !forceOpen) {
        if (!thread && userId) localStorage.setItem(`synora_nova_welcome_dismissed_${userId}`, 'true')
        setWelcomeDismissed(true)
        setOpen(false)
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [open, forceOpen])

  useEffect(() => {
    let alive = true
    if (!userId || (!open && !forceOpen)) return
    const contextKey = `${userId}:${projectId || 'workspace'}`
    if (loadedContextRef.current === contextKey || loadingContextRef.current === contextKey) return
    loadingContextRef.current = contextKey
    setThread(null); setThreads([]); setError(''); setProjectChanged(false)
    setLoading(true)
    Promise.all([fetchChatAgents(), fetchChatThreads(projectId || undefined)])
      .then(([available, history]) => {
        if (!alive) return
        loadedContextRef.current = contextKey
        setAgents(available); setThreads(history)
        const storedId = localStorage.getItem(threadKey)
        const saved = history.find(item => item.id === storedId) || history[0]
        if (history.length > 0) {
          setWelcomeDismissed(true)
          localStorage.setItem(`synora_nova_welcome_dismissed_${userId}`, 'true')
        }
        if (saved) {
          setThread(saved)
          setAgentType(isAutomaticThread(saved) ? 'auto' : saved.agent_type)
        }
        else if (storedId) { localStorage.removeItem(threadKey); setProjectChanged(true) }
        setAgentType(current => !projectId || current === 'auto' || available.some(agent => agent.agent_type === current) ? current : available[0]?.agent_type || 'auto')
      })
      .catch(err => { if (alive) { loadingContextRef.current = ''; setError(err.message || 'Could not load assistant history.') } })
      .finally(() => { if (alive) setLoading(false) })
    return () => {
      alive = false
      if (loadedContextRef.current !== contextKey && loadingContextRef.current === contextKey) loadingContextRef.current = ''
    }
  }, [projectId, userId, threadKey, open, forceOpen])

  useEffect(() => {
    if (!open && !forceOpen) return
    fetchChatStatus().then(setStatus).catch(() => undefined)
  }, [open, forceOpen])

  useEffect(() => {
    if (!projectId) { setAgentType('auto'); return }
    if (!agents.some(agent => agent.agent_type === agentHint)) return
    setAgentType(agentHint)
    if (forceOpen && agentHint !== 'auto' && thread?.agent_type !== agentHint) {
      if (threadKey) localStorage.removeItem(threadKey)
      setThread(null)
    }
  }, [agentHint, agents, forceOpen, projectId, threadKey, thread?.agent_type])
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [thread?.messages.length, sending, open])
  useEffect(() => () => { if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel() }, [])

  async function selectThread(item: ChatThread) {
    setThread(item); setError('')
    setAgentType(isAutomaticThread(item) ? 'auto' : item.agent_type)
    if (threadKey) localStorage.setItem(threadKey, item.id)
  }

  async function submitMessage(value = draft) {
    const content = redactChatSecrets(value.trim())
    if (!content || sending) return
    if (!projectId && agentType !== 'auto') {
      setError('Choose a project to use a specialist, or switch to NOVA automatic routing for workspace guidance.')
      return
    }
    if (agentType === 'handover_interviewer' && !handoverId && !thread) {
      setError('Choose a draft handover first, or switch to automatic routing.')
      return
    }
    setDraft(''); setSending(true); setError('')
    let activeThread = thread
    try {
      if (agentType !== 'auto' && !agents.some(agent => agent.agent_type === agentType)) {
        throw new Error('That specialist is not available for your account. Choose NOVA automatic routing or an available specialist.')
      }
      if (!activeThread) {
        activeThread = await createChatThread(agentType, projectId || undefined, agentType === 'handover_interviewer' ? handoverId : undefined)
        setThreads(previous => [activeThread!, ...previous.filter(item => item.id !== activeThread!.id)])
        if (threadKey) localStorage.setItem(threadKey, activeThread.id)
      }
      const optimistic: ChatMessage = { id: `pending-${Date.now()}`, thread_id: activeThread.id, sender_role: 'user', content, created_at: new Date().toISOString() }
      setThread(current => current?.id === activeThread!.id
        ? { ...current, messages: [...current.messages, optimistic] }
        : { ...activeThread!, messages: [...(activeThread!.messages || []), optimistic] })
      dismissWelcome()
      const response = await sendChatMessage(activeThread.id, content, currentPage, isAutomaticThread(activeThread) ? 'auto_route' : undefined)
      setThread(current => current?.id === activeThread!.id ? { ...current, messages: [...current.messages.filter(message => message.id !== optimistic.id), response] } : current)
      setThreads(previous => previous.map(item => item.id === activeThread!.id ? { ...item, updated_at: response.created_at } : item).sort((a, b) => b.updated_at.localeCompare(a.updated_at)))
    } catch (err: any) {
      if (activeThread) {
        setThread(current => current?.id === activeThread!.id
          ? { ...current, messages: current.messages.filter(item => !item.id.startsWith('pending-')) }
          : current)
      }
      setDraft(content); setError(err.message || 'Message could not be sent.')
    } finally { setSending(false) }
  }

  function navigateTo(tab: string) { setOpen(false); onNavigate(tab) }
  function dismissWelcome() {
    setWelcomeDismissed(true)
    if (userId) localStorage.setItem(`synora_nova_welcome_dismissed_${userId}`, 'true')
  }
  function closeAssistant() {
    if (!thread) dismissWelcome()
    if (forceOpen) onClose()
    else setOpen(false)
  }

  function listenToGuide() {
    if (!('speechSynthesis' in window)) { setSpeechState('unsupported'); return }
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(`${activeGuideStep.title}. ${activeGuideStep.description}`)
    speechRef.current = utterance
    utterance.onend = () => setSpeechState('idle')
    utterance.onerror = () => setSpeechState('idle')
    setSpeechState('speaking')
    window.speechSynthesis.speak(utterance)
  }
  function toggleSpeech() {
    if (!('speechSynthesis' in window)) { setSpeechState('unsupported'); return }
    if (speechState === 'speaking') { window.speechSynthesis.pause(); setSpeechState('paused') }
    else if (speechState === 'paused') { window.speechSynthesis.resume(); setSpeechState('speaking') }
    else listenToGuide()
  }
  function stopSpeech() {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    speechRef.current = null
    setSpeechState('idle')
  }

  const suggestedPrompts = [
    { label: 'Help me get started', prompt: `Help me get started in Synora from the ${currentPage} page.` },
    { label: 'Explore my project', prompt: 'Give me an evidence-backed overview of my selected project and suggest what to inspect first.' },
    { label: 'Search project knowledge', prompt: 'Search the selected project knowledge for the information most relevant to my current work.' },
    { label: 'Show me what Synora can do', prompt: 'Explain what I can do in Synora and guide me to the right workspace for my goal.' },
  ]

  return <>
    {!forceOpen && <button className="chat-launcher nova-launcher" aria-label="Open NOVA, Synora AI Guide" onClick={() => setOpen(true)}><NovaMark /><span>Ask NOVA</span></button>}
    {(open || forceOpen) && <section className={`chat-assistant-shell ${expanded ? 'expanded' : ''} ${forceOpen ? 'route' : ''}`} aria-label="Synora contextual AI assistant">
      <header className="chat-shell-header">
        <div className="chat-shell-brand"><span className="chat-brand-icon nova-brand-icon"><NovaMark /></span><div><strong>NOVA <em>AI Guide</em></strong><small>{projectId ? projectName || 'Selected project' : 'Your Synora Project Companion'} · {currentPage}</small></div></div>
        <div className="chat-shell-controls">
          {!forceOpen && <button type="button" aria-label={expanded ? 'Minimize assistant' : 'Expand assistant'} onClick={() => setExpanded(value => !value)}>{expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>}
          {!forceOpen && <button type="button" aria-label="Close NOVA" onClick={closeAssistant}><X size={17} /></button>}
          {forceOpen && <button type="button" aria-label="Return to previous module" onClick={closeAssistant}><X size={17} /></button>}
        </div>
      </header>
      <div className="chat-shell-context"><span>{projectId ? `Project context: ${projectName || 'Selected project'}` : 'Workspace guide · select a project for project-specific answers'}</span><span title={status?.message}>{status?.configured ? 'Gemini configured' : status?.is_mock ? 'Synora guidance mode' : status ? 'Deterministic mode available' : 'Checking AI provider…'}</span></div>
      <nav className="nova-mode-switch" aria-label="NOVA mode">
        <button type="button" className={mode === 'ask' ? 'active' : ''} aria-pressed={mode === 'ask'} onClick={() => setMode('ask')}><Sparkles size={15}/> Ask NOVA</button>
        <button type="button" className={mode === 'guide' ? 'active' : ''} aria-pressed={mode === 'guide'} onClick={() => setMode('guide')}><Compass size={15}/> Guide me</button>
      </nav>
      {projectChanged && <div className="chat-project-notice" role="status">The previous project’s conversation remains saved in that project’s history.</div>}
      <div className="chat-shell-body">
        <aside className="chat-history" aria-label="Conversation history">
          <div className="chat-history-title">Saved conversations <button type="button" aria-label="Start new conversation" onClick={() => { setThread(null); if (threadKey) localStorage.removeItem(threadKey) }}><MessageSquarePlus size={14} /></button></div>
          {loading && !threads.length ? <div className="chat-muted"><Loader2 className="spin" size={15} /> Loading…</div> : threads.length ? threads.map(item => <button key={item.id} className={`chat-thread-row ${thread?.id === item.id ? 'selected' : ''}`} onClick={() => void selectThread(item)}><span>{item.title}</span><small>{isAutomaticThread(item) ? 'NOVA · Automatic routing' : agents.find(agent => agent.agent_type === item.agent_type)?.name || item.agent_type}</small></button>) : <p className="chat-muted">No saved conversations for this project.</p>}
        </aside>
        <div className="chat-main">
          {mode === 'guide' ? <section className="nova-guide-view" aria-label="Synora guided tour">
            <div className="nova-guide-progress"><span className="project-eyebrow">GUIDE ME THROUGH SYNORA</span><span>Step {guideStep + 1} of {guideSteps.length}</span></div>
            <div className="nova-guide-track" aria-label="Tour steps">{guideSteps.map((step, index) => <button type="button" key={step.title} className={`${index === guideStep ? 'current' : ''} ${step.tab && currentPage === step.tab ? 'page-active' : ''}`} aria-label={`Step ${index + 1}: ${step.title}`} aria-current={index === guideStep ? 'step' : undefined} onClick={() => { stopSpeech(); setGuideStep(index) }}><span>{index + 1}</span>{step.title}</button>)}</div>
            <article className="nova-guide-card" key={activeGuideStep.title}><span className="nova-guide-icon"><NovaMark /></span><h3>{activeGuideStep.title}</h3><p>{activeGuideStep.description}</p>{activeGuideStep.tab && currentPage === activeGuideStep.tab && <small className="nova-guide-current-page">You are viewing this section now.</small>}</article>
            <div className="nova-guide-audio" aria-label="Audio guidance controls"><button type="button" onClick={toggleSpeech}><Volume2 size={15}/>{speechState === 'speaking' ? 'Pause' : speechState === 'paused' ? 'Resume' : 'Listen'}</button>{speechState !== 'idle' && speechState !== 'unsupported' && <button type="button" onClick={stopSpeech}><X size={14}/> Stop</button>}{speechState === 'unsupported' && <span role="status">Audio is unavailable in this browser. Read the guidance above.</span>}</div>
            <div className="nova-guide-actions"><button type="button" disabled={guideStep === 0} onClick={() => { stopSpeech(); setGuideStep(step => Math.max(0, step - 1)) }}><ArrowLeft size={15}/> Back</button><div>{activeGuideStep.tab && <button type="button" onClick={() => onNavigate(activeGuideStep.tab)}><ExternalLink size={14}/> Open section</button>}<button type="button" onClick={() => { stopSpeech(); setGuideStep(step => Math.min(guideSteps.length - 1, step + 1)) }}>{guideStep === guideSteps.length - 1 ? 'Finish' : 'Next'} <ArrowRight size={15}/></button><button type="button" className="nova-guide-skip" disabled={guideStep === guideSteps.length - 1} onClick={() => { stopSpeech(); setGuideStep(guideSteps.length - 1) }}><SkipForward size={14}/> Skip to end</button></div></div>
            <button type="button" className="nova-guide-ask-link" onClick={() => setMode('ask')}>Have a question? Ask NOVA <ArrowRight size={14}/></button>
          </section> : <>
          {!thread ? <div className={`chat-start-panel nova-start-panel ${!welcomeDismissed ? 'first-welcome' : ''}`}>
            {!welcomeDismissed ? <div className="nova-welcome-card"><span className="nova-welcome-mark"><NovaMark /></span><span className="project-eyebrow">YOUR FRIENDLY PROJECT COMPANION</span><h3>Welcome to Synora</h3><p>Hi! I'm <strong>NOVA</strong>, your Synora guide. I can answer your questions or personally walk you through the website, its features and how to use them. Where shall we begin?</p><div className="nova-welcome-actions"><button type="button" onClick={() => { dismissWelcome(); setMode('ask') }}><Sparkles size={15}/> Ask NOVA</button><button type="button" onClick={() => { dismissWelcome(); setMode('guide'); setGuideStep(0) }}><Compass size={15}/> Guide me through Synora</button></div></div> : <div className="nova-empty-greeting"><h3>What would you like to explore?</h3><p>Ask NOVA anything about your workspace. You can ask follow-up questions naturally.</p></div>}
            {!welcomeDismissed && <div className="nova-suggestions" aria-label="Suggested prompts">{suggestedPrompts.map(item => <button type="button" key={item.label} onClick={() => { dismissWelcome(); setMode('ask'); void submitMessage(item.prompt) }} disabled={sending}>{item.label}<ExternalLink size={13} /></button>)}</div>}
            <details className="nova-specialist-picker"><summary>Choose a specialist (optional)</summary><label>Agent<select value={agentType} onChange={event => setAgentType(event.target.value as ChatAgentType)} disabled={loading}><option value="auto">NOVA · automatic routing</option>{agents.filter(agent => agent.agent_type !== 'auto' && !!projectId).map(agent => <option value={agent.agent_type} key={agent.agent_type}>{agent.name}</option>)}</select></label>{!projectId && <p className="chat-agent-description">Select a project to enable project specialists. NOVA can still explain Synora and the current section.</p>}{currentAgent && agentType !== 'auto' && <p className="chat-agent-description">{currentAgent.description}</p>}</details>
            {agentType === 'handover_interviewer' && <label className="nova-handover-select">Draft handover<select value={handoverId} onChange={event => setHandoverId(event.target.value)}><option value="">Choose a draft handover</option>{projectHandovers.map(item => <option key={item.id} value={item.id}>{item.employee_name} · {item.status}</option>)}</select><small>Answers remain unverified until a reviewer approves the handover.</small></label>}
            {!projectId && <button className="nova-project-cta" type="button" onClick={() => navigateTo('projects')}>Choose a project for project-specific answers <ArrowRight size={15} /></button>}
            <form className="chat-composer nova-first-composer" onSubmit={event => { event.preventDefault(); void submitMessage() }}><textarea value={draft} maxLength={20000} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submitMessage() } }} placeholder="Ask NOVA anything…" rows={2} disabled={sending} aria-label="Message NOVA"/><button type="submit" className="primary-btn" disabled={sending || !draft.trim()}>{sending ? <Loader2 className="spin" size={15} /> : <Send size={15} />} Send</button></form>
            <p className="chat-honesty"><ShieldCheck size={14} /> NOVA uses your authorized project context and will tell you when information is missing.</p>
          </div> : <>
            <div className="chat-active-title"><div><span>{isAutomaticThread(thread) ? 'NOVA · Automatic routing' : agents.find(agent => agent.agent_type === thread.agent_type)?.name || thread.agent_type.replaceAll('_', ' ')}</span><small>{projectName || (projectId ? 'Selected project' : 'Workspace guidance')} · {currentPage}</small></div><button className="text-link-button" onClick={() => { setThread(null); if (threadKey) localStorage.removeItem(threadKey) }}>New conversation <ChevronDown size={13} /></button></div>
            <div className="chat-messages" aria-live="polite" ref={scrollRef}>
              {thread.messages.map(message => <article className={`chat-message ${message.sender_role}`} key={message.id}>
                <div className="chat-message-content">{message.content}</div>
                {message.sender_role === 'assistant' && message.tool_calls?.find(call => call.tool === 'AgentRouter')?.selected_agent && <small className="chat-route-label">Routed to {agents.find(agent => agent.agent_type === message.tool_calls?.find(call => call.tool === 'AgentRouter')?.selected_agent)?.name || String(message.tool_calls.find(call => call.tool === 'AgentRouter')?.selected_agent).replaceAll('_', ' ')}</small>}
                {message.tool_calls?.some(call => call.tool === 'AI response mode' && call.provider === 'deterministic_fallback' || call.tool === 'Gemini generation' && call.provider !== 'gemini') && <div className="chat-fallback-notice">Deterministic guidance · Gemini did not provide this response.</div>}
                {!!message.citations?.length && <details className="chat-citations"><summary>Evidence and sources ({message.citations.length})</summary>{message.citations.map((citation: any, index) => <div key={`${citation.document_id || citation.source_id || index}-${citation.chunk_id || index}`}><span>{citation.document_name || citation.source_title || citation.source_type || 'Project source'}{citation.file_path ? ` · ${citation.file_path}` : ''}{citation.chunk_index != null ? ` · chunk ${citation.chunk_index}` : ''}</span>{citation.verification_status && <small>{citation.verification_status}</small>}{citation.snippet && <blockquote>{citation.snippet}</blockquote>}</div>)}</details>}
                {message.tool_calls?.some(call => call.tool === 'ProjectSearchService.search') && <details className="chat-coverage"><summary>Search coverage</summary>{message.tool_calls.filter(call => call.tool === 'ProjectSearchService.search').slice(-1).map((call, index) => <div key={index}><small>{Array.isArray(call.searched_sources) ? `Searched: ${call.searched_sources.join(', ')}` : 'Search executed against authorized project records.'}</small>{Array.isArray(call.sources_without_searchable_records) && call.sources_without_searchable_records.length > 0 && <small>No searchable records: {call.sources_without_searchable_records.join(', ')}</small>}{Array.isArray(call.unsupported_sources) && call.unsupported_sources.length > 0 && <small>Unavailable integrations: {call.unsupported_sources.join('; ')}</small>}</div>)}</details>}
                {!!message.recommended_actions?.length && <div className="chat-actions">{message.recommended_actions.map((action, index) => action.action === 'navigate' ? <button key={index} onClick={() => navigateTo(['recreator','radar','sentinel','handovers','knowledge','projects'].includes(action.target) ? action.target : 'knowledge')}>{String(action.label || 'Open module')} <ExternalLink size={13} /></button> : action.action === 'prompt' && action.text ? <button key={index} onClick={() => void submitMessage(String(action.text))}>{String(action.label || 'Ask follow-up')}</button> : null)}</div>}
              </article>)}
              {sending && <div className="chat-loading"><Loader2 className="spin" size={16} /> Searching authorized project sources and preparing a response…</div>}
            </div>
            <form className="chat-composer" onSubmit={event => { event.preventDefault(); void submitMessage() }}><textarea value={draft} maxLength={20000} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submitMessage() } }} placeholder="Ask about project knowledge, risks, handover, or setup…" rows={2} disabled={sending} aria-label="Message Synora Assistant"/><button type="submit" className="primary-btn" disabled={sending || !draft.trim()}>{sending ? <Loader2 className="spin" size={15} /> : <Send size={15} />} Send</button></form>
          </>}
          </>}
          {error && <p className="chat-error" role="alert">{error}</p>}
        </div>
      </div>
    </section>}
  </>
}

const NovaMark: React.FC = () => <span className="nova-mark" aria-hidden="true"><Compass className="nova-compass" size={23} strokeWidth={1.8} /><Sparkles className="nova-sparkles" size={12} strokeWidth={2.1} /></span>

function isAutomaticThread(item: ChatThread): boolean {
  return item.agent_type === 'auto' || item.title.startsWith('NOVA · Auto')
}

function redactChatSecrets(value: string): string {
  return value.replace(/(["']?[A-Z0-9_.-]*(?:API[_-]?KEY|ACCESS[_-]?KEY(?:[_-]?ID)?|SECRET|PASSWORD|TOKEN|DATABASE[_-]?URL|PRIVATE[_-]?KEY|AUTHORIZATION)["']?\s*[:=]\s*["']?)[^\s,;"']+/gi, '$1[REDACTED]')
    .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, 'Bearer [REDACTED]')
    .replace(/-----BEGIN [^-]+-----[\s\S]*?-----END [^-]+-----/g, '[PRIVATE KEY REDACTED]')
}

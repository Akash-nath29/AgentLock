import React, { useState } from 'react';
import { Terminal, Copy, Check, ArrowRight, Lock, Sparkles, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react';

export default function Hero({ onGetStarted, onExploreSimulator }) {
  const [copied, setCopied] = useState(false);
  const [activeHeroTab, setActiveHeroTab] = useState('trace'); // 'trace' | 'spec' | 'lock'

  const handleCopy = () => {
    navigator.clipboard.writeText('pip install agentlock');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="section-padding" style={{ paddingTop: '3.5rem', paddingBottom: '3.5rem' }}>
      <div className="container">
        
        {/* Top Header Block */}
        <div style={{ textAlign: 'center', maxWidth: '840px', margin: '0 auto 3rem auto' }}>
          
          {/* Status Badge */}
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <span className="badge badge-slate" style={{ padding: '0.3rem 0.75rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem', border: '1px solid var(--border-light)' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--emerald)' }}></span>
              Gemma 4 & Ollama Native • Zero Framework Lock-In
            </span>
          </div>

          {/* Main Title */}
          <h1 style={{ fontSize: '3.75rem', fontWeight: '800', letterSpacing: '-0.04em', lineHeight: '1.1', marginBottom: '1.25rem' }}>
            Lock your agent's behavior, <br />
            <span className="gradient-title">not just its dependencies.</span>
          </h1>

          {/* Subtitle */}
          <p style={{ fontSize: '1.1875rem', color: 'var(--text-muted)', lineHeight: '1.6', marginBottom: '2.25rem', fontWeight: '450', maxWidth: '740px', margin: '0 auto 2.25rem auto' }}>
            Swap a model, edit a prompt, or tweak a skill — Python doesn't crash, but your agent quietly changes tool sequencing. AgentLock generates behavioral contracts, tests scenarios, and blocks behavioral drift in CI.
          </p>

          {/* Action CTAs */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.875rem', flexWrap: 'wrap' }}>
            {/* Install Pill Box */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              background: '#090d16',
              padding: '0.55rem 0.95rem',
              borderRadius: '8px',
              border: '1px solid #1e293b',
              boxShadow: 'var(--shadow-sm)'
            }}>
              <Terminal size={15} color="#818cf8" />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: '#f8fafc', fontWeight: '500' }}>
                pip install agentlock
              </span>
              <button
                onClick={handleCopy}
                style={{
                  background: 'rgba(255, 255, 255, 0.1)',
                  border: 'none',
                  color: copied ? '#34d399' : '#94a3b8',
                  padding: '0.25rem 0.5rem',
                  borderRadius: '5px',
                  cursor: 'pointer',
                  fontSize: '0.72rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  transition: 'all 0.15s ease'
                }}
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            <button onClick={onGetStarted} className="btn btn-primary">
              <span>Quickstart Docs</span>
              <ArrowRight size={15} />
            </button>

            <button onClick={onExploreSimulator} className="btn btn-secondary">
              <Lock size={15} color="var(--primary)" />
              <span>Interactive Drift Simulator</span>
            </button>
          </div>

        </div>

        {/* Hero Interactive Terminal Showcase Window */}
        <div className="code-window" style={{ maxWidth: '980px', margin: '0 auto' }}>
          
          {/* Terminal Titlebar & Tabs */}
          <div className="code-window-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
              <div className="code-dots">
                <div className="code-dot code-dot-red"></div>
                <div className="code-dot code-dot-yellow"></div>
                <div className="code-dot code-dot-green"></div>
              </div>

              <div style={{ display: 'flex', gap: '0.25rem' }}>
                <button
                  onClick={() => setActiveHeroTab('trace')}
                  style={{
                    background: activeHeroTab === 'trace' ? '#1e293b' : 'transparent',
                    border: 'none',
                    color: activeHeroTab === 'trace' ? '#f8fafc' : '#94a3b8',
                    padding: '0.25rem 0.65rem',
                    borderRadius: '5px',
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                    cursor: 'pointer'
                  }}
                >
                  agentlock test --compare
                </button>
                
                <button
                  onClick={() => setActiveHeroTab('spec')}
                  style={{
                    background: activeHeroTab === 'spec' ? '#1e293b' : 'transparent',
                    border: 'none',
                    color: activeHeroTab === 'spec' ? '#f8fafc' : '#94a3b8',
                    padding: '0.25rem 0.65rem',
                    borderRadius: '5px',
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                    cursor: 'pointer'
                  }}
                >
                  my_agent.py
                </button>

                <button
                  onClick={() => setActiveHeroTab('lock')}
                  style={{
                    background: activeHeroTab === 'lock' ? '#1e293b' : 'transparent',
                    border: 'none',
                    color: activeHeroTab === 'lock' ? '#f8fafc' : '#94a3b8',
                    padding: '0.25rem 0.65rem',
                    borderRadius: '5px',
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                    cursor: 'pointer'
                  }}
                >
                  agent.lock
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.72rem', color: '#64748b' }}>
              <ShieldCheck size={14} color="#34d399" />
              <span>Gemma 4 Verification</span>
            </div>
          </div>

          {/* Body Content */}
          <div className="code-window-body" style={{ minHeight: '280px', padding: '1.25rem 1.5rem' }}>
            
            {activeHeroTab === 'trace' && (
              <div className="animate-fade-in">
                <div style={{ color: '#94a3b8', marginBottom: '0.75rem' }}>
                  $ agentlock test --compare
                </div>
                
                <div style={{ color: '#818cf8', marginBottom: '0.75rem' }}>
                  AgentLock Behavioral Comparison vs Baseline (73b905c9f062)
                </div>

                <div style={{ color: '#fbbf24', marginBottom: '0.75rem' }}>
                  Changed since baseline: ~ config workflow: careful → pr-first
                </div>

                <div style={{ color: '#f43f5e', fontWeight: '600', marginBottom: '0.5rem' }}>
                  BEHAVIORAL REGRESSIONS DETECTED (1)
                </div>

                <div style={{ background: 'rgba(244, 63, 94, 0.12)', borderLeft: '3px solid #f43f5e', padding: '0.65rem 0.85rem', borderRadius: '0 6px 6px 0', fontSize: '0.8125rem' }}>
                  <div style={{ color: '#f87171', fontWeight: '600' }}>✗ test-before-pr (fix-token-expiry)</div>
                  <div style={{ color: '#cbd5e1' }}>Expected: run_tests → create_pull_request</div>
                  <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>
                    Observed: search_code → read_file → write_file → <span style={{ color: '#f87171', textDecoration: 'underline' }}>create_pull_request</span> → run_tests
                  </div>
                  <div style={{ color: '#fb7185', fontSize: '0.75rem', marginTop: '2px' }}>
                    create_pull_request was called before any run_tests completed!
                  </div>
                </div>

                <div style={{ color: '#f43f5e', marginTop: '0.75rem', fontWeight: '600' }}>
                  Process finished with exit code 1. (CI Build Blocked)
                </div>
              </div>
            )}

            {activeHeroTab === 'spec' && (
              <pre className="animate-fade-in" style={{ color: '#cbd5e1' }}>{`from agentlock import AgentSpec, ModelSpec, ToolSpec, tracked_tool

@tracked_tool
def read_file(path: str) -> str: ...

@tracked_tool
def run_tests() -> dict: ...        # {"passed": bool}

class MyAgent:
    def __init__(self, **options):
        self.spec = AgentSpec(
            name="coding-agent",
            model=ModelSpec(provider="ollama", name="gemma4:31b-cloud"),
            system_prompt=PROMPT,
            tools=[ToolSpec(name="run_tests", returns="{passed: bool}"), ...]
        )`}</pre>
            )}

            {activeHeroTab === 'lock' && (
              <pre className="animate-fade-in" style={{ color: '#cbd5e1' }}>{`version: 1
agent:
  name: coding-agent
model:
  provider: ollama
  name: gemma4:31b-cloud
prompt:
  hash: 7cf6528e3c392fda2cb7957df732a44870fb85e8d4fe860bb001081cb35ffe07
contracts:
  count: 9
  hash: b54ea3d662a2dd363a3ab88f578a875646b51df447331bc9613f0d582af8bcf6
behavior:
  fingerprint: 73b905c9f0625b95ad04c02636496b2248d7c1c6d35a50472d4187c425817ef8
  contracts_passed: 9
  contracts_total: 9`}</pre>
            )}

          </div>

        </div>

      </div>
    </section>
  );
}

import React from 'react';
import { Shield, Github, Heart, Sparkles, BookOpen, Terminal } from 'lucide-react';

export default function Footer({ onNavigate }) {
  return (
    <footer style={{ background: '#ffffff', borderTop: '1px solid var(--border-light)', paddingTop: '4rem', paddingBottom: '3rem' }}>
      <div className="container">
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '2.5rem', marginBottom: '3rem' }}>
          
          {/* Brand Col */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#ffffff'
              }}>
                <Shield size={18} />
              </div>
              <span style={{ fontSize: '1.25rem', fontWeight: '800', color: 'var(--text-main)' }}>
                Agent<span style={{ color: 'var(--primary)' }}>Lock</span>
              </span>
            </div>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: '1.6', marginBottom: '1.25rem' }}>
              Lock your AI agent's behavior, not just its dependencies. Catch subtle tool-ordering drift, prompt regressions, and guardrail violations.
            </p>
            <span className="badge badge-emerald" style={{ fontSize: '0.6875rem' }}>
              MIT Licensed • Free & Open Source
            </span>
          </div>

          {/* Product Links */}
          <div>
            <h4 style={{ fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-subtle)', marginBottom: '1rem' }}>
              Product Features
            </h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
              <li>
                <button onClick={() => onNavigate('playground')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                  Behavioral Drift Simulator
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('docs', 'contracts')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                  The 6 Contract Types
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('docs', 'gemma')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                  Gemma 4 & Ollama Evaluator
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('docs', 'lockfile')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                  agent.lock Fingerprinting
                </button>
              </li>
            </ul>
          </div>

          {/* Documentation Links */}
          <div>
            <h4 style={{ fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-subtle)', marginBottom: '1rem' }}>
              Documentation
            </h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
              <li>
                <button onClick={() => onNavigate('docs', 'quickstart')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                  Quickstart Guide
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('docs', 'sdk')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                  Python SDK & @tracked_tool
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('docs', 'cli')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                  CLI Command Reference
                </button>
              </li>
            </ul>
          </div>

          {/* Community */}
          <div>
            <h4 style={{ fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-subtle)', marginBottom: '1rem' }}>
              Repository
            </h4>
            <a
              href="https://github.com/Akash-nath29/AgentLock"
              target="_blank"
              rel="noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                color: 'var(--text-main)',
                fontSize: '0.875rem',
                textDecoration: 'none',
                fontWeight: '600'
              }}
            >
              <Github size={18} />
              <span>Akash-nath29/AgentLock</span>
            </a>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.75rem' }}>
              Starred by developers creating reliable AI agents with Gemma 4.
            </p>
          </div>

        </div>

        {/* Bottom Bar */}
        <div style={{
          paddingTop: '2rem',
          borderTop: '1px solid var(--border-light)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
          fontSize: '0.8125rem',
          color: 'var(--text-muted)'
        }}>
          <div>
            © 2026 Akash Nath. Built for deterministic behavioral reliability.
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <span>Designed with human care</span>
            <Heart size={14} color="var(--rose)" fill="var(--rose)" />
            <span>for the Agentic AI community</span>
          </div>
        </div>

      </div>
    </footer>
  );
}

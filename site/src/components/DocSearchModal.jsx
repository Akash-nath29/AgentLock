import React, { useState, useEffect } from 'react';
import { Search, X, BookOpen, ArrowRight, CornerDownLeft } from 'lucide-react';

const DOC_INDEX = [
  { id: 'quickstart', title: 'Quickstart & Installation', section: 'Getting Started', text: 'pip install agentlock, agentlock init, agentlock test, entrypoint setup' },
  { id: 'contracts', title: 'Behavioral Contracts Guide', section: 'Contracts', text: 'ordering, required, forbidden, conditional, semantic, multimodal rules' },
  { id: 'gemma', title: 'Gemma 4 & LLM Evaluator Setup', section: 'Integrations', text: 'Ollama local, gemma4:31b-cloud, Gemini API key, structured JSON fallback' },
  { id: 'sdk', title: 'Python SDK & @tracked_tool', section: 'Developer API', text: 'AgentSpec, ToolSpec, AgentLockTracer, record_tool_call, decorators' },
  { id: 'lockfile', title: 'agent.lock & Baselines', section: 'Architecture', text: 'Behavioral fingerprint, prompt hashing, tool schema hashing, CI exit codes' },
  { id: 'cli', title: 'CLI Reference Guide', section: 'CLI Commands', text: 'agentlock init, generate, test, test --compare, inspect, verbose' }
];

export default function DocSearchModal({ isOpen, onClose, onSelectDoc }) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
        else setQuery('');
      } else if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const filtered = DOC_INDEX.filter(item => 
    item.title.toLowerCase().includes(query.toLowerCase()) ||
    item.section.toLowerCase().includes(query.toLowerCase()) ||
    item.text.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div 
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        background: 'rgba(15, 23, 42, 0.4)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '6rem'
      }}
    >
      <div 
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '640px',
          background: 'var(--bg-card)',
          borderRadius: '16px',
          border: '1px solid var(--border-light)',
          boxShadow: '0 20px 40px rgba(15, 23, 42, 0.15)',
          overflow: 'hidden',
          animation: 'fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)'
        }}
      >
        {/* Search Input Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '1rem 1.25rem',
          borderBottom: '1px solid var(--border-light)'
        }}>
          <Search size={20} color="var(--primary)" />
          <input
            type="text"
            autoFocus
            placeholder="Search documentation (e.g., contracts, Ollama, @tracked_tool)..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{
              width: '100%',
              border: 'none',
              outline: 'none',
              fontSize: '1rem',
              fontFamily: 'var(--font-sans)',
              color: 'var(--text-main)',
              background: 'transparent'
            }}
          />
          <button 
            onClick={onClose} 
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Results List */}
        <div style={{ maxHeight: '380px', overflowY: 'auto', padding: '0.75rem' }}>
          {filtered.length > 0 ? (
            filtered.map(item => (
              <div
                key={item.id}
                onClick={() => {
                  onSelectDoc(item.id);
                  onClose();
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.875rem 1rem',
                  borderRadius: '10px',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-muted)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.875rem' }}>
                  <div style={{
                    padding: '0.5rem',
                    background: 'var(--primary-light)',
                    borderRadius: '8px',
                    color: 'var(--primary)'
                  }}>
                    <BookOpen size={18} />
                  </div>
                  <div>
                    <div style={{ fontWeight: '600', fontSize: '0.9375rem', color: 'var(--text-main)' }}>
                      {item.title}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {item.section} • {item.text}
                    </div>
                  </div>
                </div>

                <CornerDownLeft size={16} color="var(--text-subtle)" />
              </div>
            ))
          ) : (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              No matching documentation sections found for "{query}"
            </div>
          )}
        </div>

        {/* Footer Hint */}
        <div style={{
          padding: '0.625rem 1.25rem',
          background: 'var(--bg-muted)',
          borderTop: '1px solid var(--border-light)',
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '0.75rem',
          color: 'var(--text-muted)'
        }}>
          <span>Navigate with mouse or click topic</span>
          <span>ESC to close</span>
        </div>

      </div>
    </div>
  );
}

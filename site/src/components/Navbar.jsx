import React from 'react';
import { Shield, Search, Github, BookOpen, Play } from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, onOpenSearch }) {
  return (
    <header className="glass-nav">
      <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '64px' }}>
        
        {/* Brand Logo */}
        <div 
          onClick={() => setActiveTab('home')} 
          style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', cursor: 'pointer' }}
        >
          <div style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            background: '#090d16',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#ffffff',
            boxShadow: '0 2px 8px rgba(9, 13, 22, 0.15)'
          }}>
            <Shield size={18} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '1.0625rem', fontWeight: '800', letterSpacing: '-0.03em', color: 'var(--text-main)' }}>
              Agent<span style={{ color: 'var(--primary)' }}>Lock</span>
            </span>
            <span className="badge badge-slate" style={{ fontSize: '0.65rem', padding: '1px 5px' }}>
              v0.1.0
            </span>
          </div>
        </div>

        {/* Center Nav Items */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: 'var(--bg-muted)', padding: '3px', borderRadius: '10px', border: '1px solid var(--border-light)' }}>
          <button 
            onClick={() => setActiveTab('home')}
            style={{
              padding: '0.4rem 0.85rem',
              borderRadius: '7px',
              fontSize: '0.8125rem',
              fontWeight: '600',
              border: 'none',
              cursor: 'pointer',
              background: activeTab === 'home' ? '#ffffff' : 'transparent',
              color: activeTab === 'home' ? 'var(--text-main)' : 'var(--text-muted)',
              boxShadow: activeTab === 'home' ? 'var(--shadow-sm)' : 'none',
              transition: 'all 0.15s ease'
            }}
          >
            Overview
          </button>
          
          <button 
            onClick={() => setActiveTab('playground')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.375rem',
              padding: '0.4rem 0.85rem',
              borderRadius: '7px',
              fontSize: '0.8125rem',
              fontWeight: '600',
              border: 'none',
              cursor: 'pointer',
              background: activeTab === 'playground' ? '#ffffff' : 'transparent',
              color: activeTab === 'playground' ? 'var(--primary)' : 'var(--text-muted)',
              boxShadow: activeTab === 'playground' ? 'var(--shadow-sm)' : 'none',
              transition: 'all 0.15s ease'
            }}
          >
            <Play size={13} color={activeTab === 'playground' ? 'var(--primary)' : 'var(--text-muted)'} />
            <span>Interactive Sandbox</span>
          </button>

          <button 
            onClick={() => setActiveTab('docs')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.375rem',
              padding: '0.4rem 0.85rem',
              borderRadius: '7px',
              fontSize: '0.8125rem',
              fontWeight: '600',
              border: 'none',
              cursor: 'pointer',
              background: activeTab === 'docs' ? '#ffffff' : 'transparent',
              color: activeTab === 'docs' ? 'var(--text-main)' : 'var(--text-muted)',
              boxShadow: activeTab === 'docs' ? 'var(--shadow-sm)' : 'none',
              transition: 'all 0.15s ease'
            }}
          >
            <BookOpen size={13} />
            <span>Documentation</span>
          </button>
        </nav>

        {/* Right Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button 
            onClick={onOpenSearch}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.4rem 0.75rem',
              borderRadius: '8px',
              background: '#ffffff',
              border: '1px solid var(--border-light)',
              color: 'var(--text-subtle)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              boxShadow: 'var(--shadow-sm)'
            }}
          >
            <Search size={14} />
            <span>Search docs...</span>
            <kbd style={{
              background: 'var(--bg-muted)',
              border: '1px solid var(--border-light)',
              borderRadius: '4px',
              padding: '1px 4px',
              fontSize: '0.65rem',
              fontFamily: 'var(--font-mono)'
            }}>⌘K</kbd>
          </button>

          <a 
            href="https://github.com/Akash-nath29/AgentLock" 
            target="_blank" 
            rel="noreferrer"
            className="btn btn-secondary"
            style={{ padding: '0.4rem 0.75rem', fontSize: '0.8125rem' }}
          >
            <Github size={15} />
            <span>GitHub</span>
          </a>
        </div>

      </div>
    </header>
  );
}

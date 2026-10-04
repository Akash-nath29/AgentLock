import React, { useState } from 'react';
import { BookOpen, Terminal, Code, Cpu, Shield, CheckCircle2, AlertTriangle, Copy, Check, ChevronRight, Sparkles, FileText, Layers, Lock } from 'lucide-react';

const DOC_SECTIONS = [
  { id: 'quickstart', title: '1. Quickstart & Setup', icon: Terminal },
  { id: 'contracts', title: '2. Behavioral Contracts Guide', icon: Layers },
  { id: 'gemma', title: '3. Gemma 4 & LLM Evaluator', icon: Cpu },
  { id: 'sdk', title: '4. Python SDK & @tracked_tool', icon: Code },
  { id: 'lockfile', title: '5. agent.lock & Baselines', icon: Lock },
  { id: 'cli', title: '6. CLI Reference Guide', icon: FileText }
];

function CodeBlock({ code, language = 'bash' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="code-window" style={{ margin: '1.25rem 0' }}>
      <div className="code-window-header">
        <span style={{ textTransform: 'lowercase' }}>{language}</span>
        <button
          onClick={handleCopy}
          style={{
            background: 'rgba(255, 255, 255, 0.1)',
            border: 'none',
            color: copied ? '#34d399' : '#94a3b8',
            padding: '2px 8px',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <div className="code-window-body">
        <pre style={{ margin: 0 }}>{code}</pre>
      </div>
    </div>
  );
}

export default function DocumentationHub({ initialDoc = 'quickstart' }) {
  const [activeDoc, setActiveDoc] = useState(initialDoc);

  return (
    <section className="section-padding" style={{ background: '#ffffff', minHeight: '800px' }}>
      <div className="container">
        
        <div className="docs-layout">
          
          {/* Sidebar Menu */}
          <aside style={{
            position: 'sticky',
            top: '90px',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-light)',
            borderRadius: '16px',
            padding: '1rem',
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{ fontSize: '0.75rem', fontWeight: '800', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-subtle)', marginBottom: '0.75rem', paddingLeft: '0.5rem' }}>
              Documentation Index
            </div>

            <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {DOC_SECTIONS.map(sec => {
                const IconComponent = sec.icon;
                const isSelected = activeDoc === sec.id;
                return (
                  <button
                    key={sec.id}
                    onClick={() => setActiveDoc(sec.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.75rem',
                      padding: '0.625rem 0.875rem',
                      borderRadius: '10px',
                      background: isSelected ? 'var(--primary-light)' : 'transparent',
                      color: isSelected ? 'var(--primary)' : 'var(--text-muted)',
                      fontWeight: isSelected ? '700' : '500',
                      fontSize: '0.875rem',
                      border: 'none',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <IconComponent size={16} color={isSelected ? 'var(--primary)' : 'var(--text-subtle)'} />
                    <span>{sec.title}</span>
                  </button>
                );
              })}
            </nav>
          </aside>

          {/* Article Main Body */}
          <main style={{ maxWidth: '820px' }}>
            
            {/* Quickstart Article */}
            {activeDoc === 'quickstart' && (
              <article className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge badge-indigo">Getting Started</span>
                </div>
                <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>Quickstart & Installation</h1>
                <p style={{ fontSize: '1.125rem', color: 'var(--text-muted)', lineHeight: '1.7', marginBottom: '1.5rem' }}>
                  AgentLock turns your AI agent's expected behavior into <strong>behavioral contracts</strong>, runs scenarios while tracing tool execution, and flags regressions against recorded baselines.
                </p>

                <h2 style={{ fontSize: '1.5rem', marginTop: '2rem', marginBottom: '0.75rem' }}>Prerequisites</h2>
                <p style={{ color: 'var(--text-muted)' }}>
                  Requires Python 3.10+. For automatic contract generation and visual evaluation, run <a href="https://ollama.com" target="_blank" rel="noreferrer" style={{ color: 'var(--primary)' }}>Ollama</a> with Gemma 4:
                </p>

                <CodeBlock 
                  code={`# 1. Pull the default Gemma 4 model
ollama pull gemma4:31b-cloud

# 2. Install AgentLock
pip install agentlock`}
                />

                <h2 style={{ fontSize: '1.5rem', marginTop: '2.5rem', marginBottom: '0.75rem' }}>1. Connect Your Agent</h2>
                <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                  AgentLock integrates with any Python agent framework. Expose a <code style={{ fontFamily: 'var(--font-mono)' }}>.spec</code> property and decorate your tools with <code style={{ fontFamily: 'var(--font-mono)' }}>@tracked_tool</code>:
                </p>

                <CodeBlock 
                  language="python"
                  code={`# my_agent.py
from agentlock import AgentSpec, ModelSpec, ToolSpec, tracked_tool

@tracked_tool
def read_file(path: str) -> str:
    return open(path).read()

@tracked_tool
def run_tests() -> dict:
    return {"passed": True, "failed": 0}

class MyAgent:
    def __init__(self, **options):
        self.spec = AgentSpec(
            name="my-coding-agent",
            model=ModelSpec(provider="ollama", name="gemma4:31b-cloud"),
            system_prompt="You are a careful developer...",
            tools=[
                ToolSpec(name="read_file", description="Read code file"),
                ToolSpec(name="run_tests", description="Run test suite", returns="{passed: bool}")
            ]
        )

    def run(self, task: str) -> str:
        # Your agent loop
        return "Task complete"

def build_agent(**options):
    return MyAgent(**options)`}
                />

                <h2 style={{ fontSize: '1.5rem', marginTop: '2.5rem', marginBottom: '0.75rem' }}>2. Initialize & Test</h2>
                <CodeBlock 
                  code={`# Initialize configuration & entrypoint
agentlock init --entrypoint my_agent:build_agent --name my-coding-agent

# Generate behavioral contracts with Gemma 4
agentlock generate

# Run scenarios & record baseline
agentlock test

# Compare against baseline in CI/CD (exits 1 on regressions)
agentlock test --compare`}
                />
              </article>
            )}

            {/* Contracts Article */}
            {activeDoc === 'contracts' && (
              <article className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge badge-indigo">Contracts</span>
                </div>
                <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>Behavioral Contracts Specification</h1>
                <p style={{ fontSize: '1.125rem', color: 'var(--text-muted)', lineHeight: '1.7', marginBottom: '1.5rem' }}>
                  Contracts define acceptable agent behavior. Plain Python evaluates deterministic rules (ordering, required, forbidden, conditional), while Gemma 4 evaluates semantic and visual rules.
                </p>

                <div style={{ background: 'var(--primary-light)', borderLeft: '4px solid var(--primary)', padding: '1rem', borderRadius: '0 8px 8px 0', marginBottom: '2rem' }}>
                  <strong style={{ color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                    <CheckCircle2 size={16} /> Zero Non-Determinism for Rule Checks
                  </strong>
                  <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                    AgentLock never calls an LLM to check tool ordering or forbidden files. Rule evaluations execute in under 1 millisecond.
                  </span>
                </div>

                <h2 style={{ fontSize: '1.5rem', marginBottom: '0.75rem' }}>Full Schema Reference</h2>
                <CodeBlock 
                  language="json"
                  code={`[
  {
    "id": "inspect-before-edit",
    "type": "ordering",
    "before": "read_file",
    "after": "write_file",
    "match_argument": "path"
  },
  {
    "id": "test-after-edit",
    "type": "required",
    "tool": "run_tests",
    "after": "write_file"
  },
  {
    "id": "no-test-edits",
    "type": "forbidden",
    "tool": "write_file",
    "arguments": { "path": "test_*.py" }
  },
  {
    "id": "no-pr-on-test-failure",
    "type": "conditional",
    "when": { "tool": "run_tests", "field": "passed", "equals": false },
    "forbidden": ["create_pull_request"]
  },
  {
    "id": "explains-changes",
    "type": "semantic",
    "criteria": [
      "States what files changed",
      "Explains root cause of bug"
    ]
  }
]`}
                />
              </article>
            )}

            {/* Gemma 4 & LLM Article */}
            {activeDoc === 'gemma' && (
              <article className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge badge-emerald">AI Integration</span>
                </div>
                <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>Gemma 4 & LLM Evaluator</h1>
                <p style={{ fontSize: '1.125rem', color: 'var(--text-muted)', lineHeight: '1.7', marginBottom: '1.5rem' }}>
                  AgentLock integrates Gemma 4 natively through Ollama or Gemini API to perform two essential jobs: contract generation and visual/semantic evaluation.
                </p>

                <h2 style={{ fontSize: '1.5rem', marginBottom: '0.75rem' }}>Ollama Configuration (Default)</h2>
                <CodeBlock 
                  language="yaml"
                  code={`# agentlock.yaml
evaluator:
  provider: ollama
  model: gemma4:31b-cloud
  temperature: 0.0`}
                />

                <h2 style={{ fontSize: '1.5rem', marginTop: '2rem', marginBottom: '0.75rem' }}>Gemini API Option</h2>
                <CodeBlock 
                  code={`pip install 'agentlock[gemini]'
export GEMINI_API_KEY="your-api-key"`}
                />
              </article>
            )}

            {/* Python SDK Article */}
            {activeDoc === 'sdk' && (
              <article className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge badge-indigo">Developer SDK</span>
                </div>
                <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>Python SDK & Tracing</h1>
                <p style={{ fontSize: '1.125rem', color: 'var(--text-muted)', lineHeight: '1.7', marginBottom: '1.5rem' }}>
                  Use the AgentLock Python SDK to programmatically trace custom agent loops, record screenshots, or trigger contract assertions in test suites.
                </p>

                <CodeBlock 
                  language="python"
                  code={`from agentlock import AgentLock, AgentLockTracer, record_artifact

# Run programmatically
lock = AgentLock.from_config("agentlock.yaml")
report = lock.test()

if not report.passed:
    print("Regressions detected:", report.contract_statuses())

# Record screenshots for visual contracts
record_artifact("screenshot", "path/to/rendered_ui.png")`}
                />
              </article>
            )}

            {/* Lockfile & Baselines Article */}
            {activeDoc === 'lockfile' && (
              <article className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge badge-indigo">Architecture</span>
                </div>
                <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>agent.lock & Behavioral Baselines</h1>
                <p style={{ fontSize: '1.125rem', color: 'var(--text-muted)', lineHeight: '1.7', marginBottom: '1.5rem' }}>
                  Like <code style={{ fontFamily: 'var(--font-mono)' }}>package-lock.json</code> locks package versions, <code style={{ fontFamily: 'var(--font-mono)' }}>agent.lock</code> locks agent behavior.
                </p>

                <CodeBlock 
                  language="yaml"
                  code={`# agent.lock (v1)
version: 1
agent:
  name: my-coding-agent
prompt:
  hash: 7cf6528e3c392fda2cb7957df732a44870fb85e8d4fe860bb001081cb35ffe07
config:
  hash: e9bd6bc077229bdcd930b3ae378953766ca547d3ca0b61425d5444585eaeef0c
  values:
    workflow: careful
behavior:
  fingerprint: 73b905c9f0625b95ad04c02636496b2248d7c1c6d35a50472d4187c425817ef8
  contracts_passed: 9
  contracts_total: 9`}
                />
              </article>
            )}

            {/* CLI Reference Article */}
            {activeDoc === 'cli' && (
              <article className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge badge-indigo">CLI Reference</span>
                </div>
                <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>CLI Command Reference</h1>
                
                <CodeBlock 
                  code={`agentlock init --entrypoint module:callable --name my-agent
agentlock generate
agentlock test [--compare] [--verbose] [--update-baseline]
agentlock inspect`}
                />
              </article>
            )}

          </main>

        </div>

      </div>
    </section>
  );
}

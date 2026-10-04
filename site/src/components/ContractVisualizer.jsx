import React, { useState } from 'react';
import { Layers, CheckCircle2, Cpu, Eye, Code, ArrowRight } from 'lucide-react';

const CONTRACT_TYPES = [
  {
    id: 'ordering',
    name: 'Ordering Contract',
    evaluator: 'Pure Python',
    badge: 'badge-slate',
    summary: 'Enforces tool execution sequence (e.g. read_file before write_file).',
    json: `{
  "id": "inspect-before-edit",
  "type": "ordering",
  "before": "read_file",
  "after": "write_file",
  "match_argument": "path"
}`,
    explanation: 'Python validates that every call to `write_file(path=X)` was preceded by a `read_file(path=X)` call with matching argument string.'
  },
  {
    id: 'required',
    name: 'Required Contract',
    evaluator: 'Pure Python',
    badge: 'badge-slate',
    summary: 'Requires a tool call to occur at least once (or after a trigger tool).',
    json: `{
  "id": "test-after-edit",
  "type": "required",
  "tool": "run_tests",
  "after": "write_file"
}`,
    explanation: 'Python asserts that `run_tests` is executed after the last `write_file` tool call before completing the scenario.'
  },
  {
    id: 'forbidden',
    name: 'Forbidden Contract',
    evaluator: 'Pure Python',
    badge: 'badge-slate',
    summary: 'Prevents tool invocations or glob-matched arguments (e.g., test file edits).',
    json: `{
  "id": "no-test-edits",
  "type": "forbidden",
  "tool": "write_file",
  "arguments": {
    "path": "test_*.py"
  }
}`,
    explanation: 'Python evaluates argument glob patterns using fnmatch. Edits to `test_*.py` trigger an immediate contract regression.'
  },
  {
    id: 'conditional',
    name: 'Conditional Guardrail',
    evaluator: 'Pure Python',
    badge: 'badge-slate',
    summary: 'Blocks forbidden tools while a state condition holds (e.g., failed tests block PR).',
    json: `{
  "id": "no-pr-on-test-failure",
  "type": "conditional",
  "when": {
    "tool": "run_tests",
    "field": "passed",
    "equals": false
  },
  "forbidden": ["create_pull_request"]
}`,
    explanation: 'Inspects the closest `run_tests` call. If `passed` is `false`, `create_pull_request` is explicitly forbidden.'
  },
  {
    id: 'semantic',
    name: 'Semantic Text Contract',
    evaluator: 'Gemma 4 Evaluator',
    badge: 'badge-indigo',
    summary: 'Evaluates final agent text responses against task criteria using Gemma 4.',
    json: `{
  "id": "explains-changes",
  "type": "semantic",
  "criteria": [
    "States what files were modified",
    "Explains root cause of bug fix",
    "Accurately reports unit test status"
  ]
}`,
    explanation: 'Gemma 4 reads the prompt, task ground truth, and final agent response to strictly score criteria into boolean pass/fail.'
  },
  {
    id: 'multimodal',
    name: 'Multimodal Visual Contract',
    evaluator: 'Gemma 4 Vision',
    badge: 'badge-indigo',
    summary: 'Evaluates UI screenshot artifacts recorded during execution.',
    json: `{
  "id": "login-ui-renders",
  "type": "multimodal",
  "artifact": "screenshot",
  "scenarios": ["login-page"],
  "criteria": [
    "Navigation bar is visible across top",
    "Login form input fields are aligned",
    "No buttons obscure input fields"
  ]
}`,
    explanation: 'Gemma 4 (Vision) inspects the PNG recorded via `record_artifact("screenshot", path)` and checks visual layout criteria.'
  }
];

export default function ContractVisualizer() {
  const [activeId, setActiveId] = useState('ordering');
  const activeContract = CONTRACT_TYPES.find(c => c.id === activeId);

  return (
    <section className="section-padding" style={{ background: 'var(--bg-body)' }}>
      <div className="container">
        
        {/* Header */}
        <div style={{ textAlign: 'center', maxWidth: '700px', margin: '0 auto 2.5rem auto' }}>
          <span className="badge badge-slate" style={{ marginBottom: '0.75rem' }}>Deterministic + AI Verification</span>
          <h2 style={{ fontSize: '2.125rem', marginBottom: '0.75rem' }}>
            The 6 Behavioral Contract Types
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '1.05rem' }}>
            Deterministic Python checks rules instantly, while Gemma 4 handles semantic text and multimodal screenshot evaluations.
          </p>
        </div>

        {/* Contract Selector Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1.5rem', alignItems: 'start' }}>
          
          {/* Menu */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            {CONTRACT_TYPES.map(c => {
              const isSelected = c.id === activeId;
              return (
                <button
                  key={c.id}
                  onClick={() => setActiveId(c.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.75rem 0.95rem',
                    borderRadius: '8px',
                    background: isSelected ? 'var(--bg-card)' : 'transparent',
                    border: '1px solid',
                    borderColor: isSelected ? 'var(--border-light)' : 'transparent',
                    boxShadow: isSelected ? 'var(--shadow-sm)' : 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s ease'
                  }}
                >
                  <span style={{ fontWeight: isSelected ? '700' : '500', fontSize: '0.875rem', color: isSelected ? 'var(--primary)' : 'var(--text-main)' }}>
                    {c.name}
                  </span>
                  <span className={`badge ${c.badge}`} style={{ fontSize: '0.65rem' }}>
                    {c.evaluator}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Right Preview Card */}
          <div className="card" style={{ padding: '1.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <div>
                <h3 style={{ fontSize: '1.25rem' }}>{activeContract.name}</h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{activeContract.summary}</p>
              </div>
              <span className={`badge ${activeContract.badge}`}>
                {activeContract.evaluator}
              </span>
            </div>

            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1.25rem', lineHeight: '1.6' }}>
              {activeContract.explanation}
            </p>

            <div className="code-window">
              <div className="code-window-header">
                <span>.agentlock/contracts.json snippet</span>
                <span style={{ color: '#818cf8' }}>JSON Schema</span>
              </div>
              <div className="code-window-body">
                <pre style={{ margin: 0 }}>{activeContract.json}</pre>
              </div>
            </div>
          </div>

        </div>

      </div>
    </section>
  );
}

# AgentLock v0.2: Product Specification

> **Status:** design only. No v0.2 implementation exists yet.
> **Supersedes:** the v0.1 positioning ("behavioral testing framework"). v0.1 code is reused as components (§18.3).
> **Date:** 2026-10-04
>
> All terminal output, lockfile excerpts and hashes in this document are **design mock-ups**, not captured output. "Gemma" means Gemma 4 via Ollama (`gemma4:31b-cloud`) unless stated otherwise.

**Contents:** 0. The analogy · 1. Thesis · 2. Target user · 3. Problem · 4. Core workflow · 5. CLI · 6. `agent.lock` · 7. Behavioral representation · 8. Capture · 9. Diff · 10. Restore · 11. Verify · 12. Gemma's responsibilities · 13. Adapters · 14. CI · 15. Repository structure · 16. End-to-end example · 17. Demo script · 18. MVP scope · 19. Out of scope · 20. Risks · 21. Differentiation · 22. The final test

---

## 0. The analogy, made precise

AgentLock is **package-lock.json for AI agents**. The analogy is the architecture, not a slogan. Every piece maps:

| npm | AgentLock | Role |
|---|---|---|
| `package.json` | `agentlock.yaml` (the **manifest**) | Declared intent, edited by humans: entrypoint, where dependencies live, scenarios, policy |
| `node_modules/` | the running agent | The actually resolved state |
| `package-lock.json` | **`agent.lock`** | Resolved dependency closure **plus the behavior it produced**, written by the tool |
| npm cache / tarball integrity hashes | `.agentlock/objects/` | Content-addressed snapshots of prompts, skills, tool schemas, MCP tool lists, config |
| `npm install` | `agentlock capture` + `agentlock lock` | Resolve and record |
| `npm ci` | `agentlock restore` | Rebuild exactly what the lock says |
| `npm ci` failing when out of sync | `agentlock verify` | Does reality match the lock? |
| reading a lockfile diff in a PR | **`agentlock diff`** | What changed, why, and is it breaking? |

The analogy breaks in three places, and the design has to absorb each one:

1. **Behavior isn't deterministic.** A lock can't store a hash of outputs. It stores a *behavioral model*: properties that held across N sampled runs, with their support counts (§7).
2. **Some dependencies can't be fetched.** AgentLock can't download model weights from a provider that withdrew them. Restore therefore classifies every dependency as *reproducible*, *externally managed* or *unavailable* (§10).
3. **Behavior depends on inputs.** A lock is always relative to a fixed set of representative scenarios, declared in the manifest.

---

## 1. Product thesis

An agent's behavior is the build output of its dependencies: model, prompt, tools, skills, MCP servers, configuration and runtime. Today nobody records that build. The dependencies are scattered across code, config files, environment variables and provider-side aliases, and the behavior they produced is recorded nowhere.

> **AgentLock owns one concept: a versioned, reproducible behavioral state of an agent, tied to the exact dependency configuration that produced it.**

That state is a single file, `agent.lock`, committed to Git. Everything else follows from having it:

- **diff** compares two states and explains the difference;
- **restore** rebuilds the dependency half of a state;
- **verify** checks whether a running agent still conforms to the behavior half.

Tracing, testing and evaluation are inputs to this. They aren't the product.

---

## 2. Target user

**Primary:** a developer or small team shipping a tool-using agent (LangGraph first) through Git and pull requests, who changes models, prompts, tools or skills at least weekly.

They recognize these moments:

- "We upgraded the model and something feels off, but nothing crashed."
- "Which version of the prompt was live when it worked?"
- "The MCP server updated itself and the agent now calls a different tool."
- "I want to try the cheaper model. What exactly would I be giving up?"

**Not the target (for the MVP):** teams wanting production monitoring, eval leaderboards or prompt-optimization tooling.

---

## 3. Problem statement

For an agent, `behavior = f(model, prompt, tools, skills, MCP, config, runtime, input)`, plus sampling noise. Three facts make this painful:

1. **The inputs have no single identity.** A model alias such as `latest` moves. A prompt is a string in a Python file. Tool schemas are derived from function signatures. MCP servers update independently. There is no one object that says "this is the agent we shipped."
2. **The output is unrecorded.** Even teams with tests record pass/fail, not *what the agent does*: which tools, in which order, with which side effects.
3. **So changes are unexplainable and irreversible.** When behavior shifts, nobody can answer: what changed, which dependency caused it, and how do we get back?

AgentLock answers those three questions, in that order.

---

## 4. Core workflow

```text
BUILD AGENT ──► init ──► capture ──► lock ──► commit agent.lock
                                                   │
                     change model / prompt / tools / skills / MCP / config
                                                   │
                                                   ▼
                                                 diff  ◄── the hero: what, why, breaking?
                                                   │
                       ┌───────────────────────────┼────────────────────────────┐
                       ▼                           ▼                            ▼
              unintended change           keep the change, fix it       intended change
                  restore                 edit prompt/tools, loop:        lock --accept
                     │                         verify                         │
                     ▼                           │                            ▼
                  verify ◄───────────────────────┘                   commit new agent.lock
```

### Lifecycle cases

| Situation | What AgentLock does |
|---|---|
| **Model upgraded** (`A → B`) | `diff` shows the model change, the behaviors that moved, and attributes them to the model (confirmed by bisect). Choose: `restore`, fix-and-`verify`, or `lock --accept`. |
| **Prompt edited** | `diff` shows a semantic summary of the text change ("removed rule: verify the customer first") and which contracts it affected. A prompt edit with no behavioral effect reports **"dependencies changed, behavior conforms."** |
| **Skill changed** | Same as prompt: content diff, semantic summary, affected contracts attributed by locality. |
| **Tool schema or implementation changed** | `diff` shows added/removed/renamed tools and schema field changes. Renames are mapped so they don't produce false behavioral diffs. |
| **MCP server bumped** | `diff` shows the version and the change in its tool list (snapshot of `tools/list`). |
| **Nothing changed, but behavior did** | `verify` (nightly in CI) fails; `diff` reports **"unattributed: likely external drift"**, e.g. a cloud model tag whose weights changed behind the same name. |
| **Behavior changed on purpose** | `lock --accept` records the new state. The `agent.lock` diff in the PR *is* the review artifact. |
| **Model A no longer exists** | `restore` marks it *unavailable*; `verify --with model=<candidate>` measures how well alternatives conform to the locked behavior. |

---

## 5. CLI design

Six commands. Each has exactly one job in the lockfile analogy. v0.1's `generate`, `test` and `inspect` are removed: their work moves into `lock`, `verify` and `diff`.

| Command | Job | Runs the agent? | Calls Gemma? | Writes |
|---|---|---|---|---|
| `init` | Create the manifest | no | optional | `agentlock.yaml`, `.agentlock/`, `.gitignore` entries |
| `capture` | Observe the current agent and build a behavioral state | **yes** | yes | `.agentlock/captures/<id>.json` |
| `lock` | Promote a capture to the known-good state | no (uses a capture) | yes (contract curation) | `agent.lock`, `.agentlock/objects/` |
| `diff` | Explain the difference between two states | yes, unless `--deps-only` or comparing two locks | yes | nothing |
| `restore` | Rebuild the locked dependency configuration | no | no | dependency files |
| `verify` | Gate: does the current agent conform to the lock? | **yes** | yes (semantic checks) | nothing |

### `agentlock init`
Detects the framework, asks for (or takes `--entry`) the agent entrypoint, and writes the manifest. It imports the agent once to list what it found (models, tools, prompt sources) and to suggest where each controllable dependency lives, so that `restore` can work later.

Flags: `--adapter langgraph|python`, `--entry module:attr`.

### `agentlock capture`
Resolves dependencies, runs every scenario `samples` times through the adapter, and reduces the runs to a behavioral state (§7, §8). It doesn't touch `agent.lock`.

Flags: `--samples N`, `--scenario ID` (repeatable).

### `agentlock lock`
Writes `agent.lock` from the most recent capture (or runs `capture` first if there is none for the current dependency state).

- **No lock yet:** writes it.
- **Lock exists, dependencies changed, behavior conforms:** updates the dependency section and prints "behavior conforms."
- **Lock exists, behavior changed:** **refuses**, prints the summary, and tells the user to review with `agentlock diff`. `--accept` records the change; `--accept <contract-id>…` accepts specific changes only.

Flags: `--accept [ID…]`, `--from <capture-id>`.

### `agentlock diff [BASE] [HEAD]`
The hero command (§9). Defaults: `BASE = agent.lock`, `HEAD = live` (a fresh capture of the working tree).

`BASE` and `HEAD` may each be `live`, a capture id, or a Git ref (meaning "the `agent.lock` at that ref"). So:

- `agentlock diff`: lock vs. the agent as it is now. Runs the agent.
- `agentlock diff main`: `main`'s lock vs. this branch's lock. **Runs nothing**; ideal for reviewing an intentional re-lock.
- `agentlock diff --deps-only`: dependency changes only. Instant, no model calls.

Flags: `--deps-only`, `--no-bisect`, `--format text|md|json`, `--exit-code` (non-zero when breaking changes exist; off by default, like `git diff`).

### `agentlock restore`
Rebuilds what AgentLock controls and reports honestly on what it doesn't (§10).

Flags: `--dry-run`, `--only <dep-id,…>`, `--to DIR` (restore into a copy instead of the working tree).

### `agentlock verify`
The gate (§11). Terse output, meaningful exit code.

Flags: `--samples N`, `--scenario ID`, `--strict` (drift also fails), `--deps-only`, `--with <dep-id>=<value>` (run with an override, e.g. a candidate model).

### Exit codes
`0` conforms / nothing breaking · `1` breaking behavioral change or violation · `2` usage, configuration or infrastructure error (e.g. evaluator unreachable). A run that couldn't be evaluated is never reported as conforming.

---

## 6. `agent.lock` schema

### 6.1 Design rules

1. **Machines write it; humans read it.** Humans edit the manifest. Manual contracts and severity overrides live in `agentlock.yaml`; the lock holds the resolved result.
2. **Deterministic.** Key order is fixed by the schema. Lists are sorted by `id`. Rates are stored as counts (`3/3`), never floats. Re-locking the same capture produces a byte-identical file.
3. **No noise.** No timestamps, hostnames, absolute paths, run ids, latencies or token counts anywhere in the file. Git records when and who.
4. **Small.** Multi-line content (prompt text, schemas) is referenced by hash and stored in `.agentlock/objects/`. The lock stays reviewable in a PR.
5. **Self-sufficient for restore.** Every dependency AgentLock can restore has an `object`. Everything else records enough identity to check availability.
6. **Versioned.** `lockfile_version` gates the reader.

### 6.2 Example

```yaml
lockfile_version: 2
agentlock: 0.2.0
state: 7c41e0.3f2a91            # <dependency fingerprint>.<behavior fingerprint>, truncated

agent:
  name: support-agent
  adapter: langgraph
  entrypoint: support_agent.graph:build_graph

dependencies:
  fingerprint: sha256:7c41e0…
  model:
    - id: model.agent                      # one entry per model-calling node
      provider: ollama
      name: gemma4:31b-cloud
      digest: f33840cde1cc                 # provider manifest digest, when the provider exposes one
      parameters: {temperature: 0.0}
      source: {file: agent.config.yaml, key: model}
      class: external
  prompts:
    - id: prompt.system
      sha256: 418a72e7…
      object: 41/8a72e7…
      source: {file: support_agent/prompts/system.md}
      class: reproducible
  skills:
    - id: skill.refund_policy
      sha256: 9c1e44…
      object: 9c/1e44…
      source: {file: support_agent/skills/refund_policy.md}
      class: reproducible
  tools:
    - id: tool.issue_refund
      schema_sha256: 5be1c0…
      object: 5b/e1c0…                     # name, description, JSON schema
      implementation: {file: support_agent/tools.py, symbol: issue_refund, git_blob: 8f3a1d2}
      class: external                      # code is managed by Git, not by AgentLock
    # … one entry per tool
  mcp: []                                  # see 6.3 for the shape
  config:
    - id: config.agent
      sha256: e9bd6b…
      object: e9/bd6b…
      values: {max_steps: 12}
      source: {file: agent.config.yaml}
      class: reproducible
  runtime:
    python: "3.11"
    packages: {langgraph: 0.4.1, langchain-core: 0.3.60, langchain-ollama: 0.3.2}

behavior:
  fingerprint: sha256:3f2a91…
  basis: {scenarios: 6, samples: 3, judge: gemma4:31b-cloud}

  actions:                                 # the semantic vocabulary (7.3)
    verify_identity:   {tool: verify_customer, effect: read}
    lookup_order:      {tool: lookup_order, effect: read}
    check_eligibility: {tool: check_refund_eligibility, effect: read}
    issue_refund:      {tool: issue_refund, effect: irreversible}
    escalate:          {tool: escalate_to_human, effect: external}
    notify_customer:   {tool: send_email, effect: external}
    close_account:     {tool: close_account, effect: irreversible}

  scenarios:
    - id: eligible-refund
      input: "Hi, I'm jane@example.com. My order #1001 (wireless headphones) arrived broken. Can I get a refund?"
      entities: {customer: jane@example.com, order: "1001"}
      outcome: {label: refund_issued, support: 3/3}
      effects:                             # partial order over side effects (7.4)
        - issue_refund(order=$order)
        - notify_customer(to=$customer)  after  issue_refund
      paths:
        - {steps: [verify_identity, check_eligibility, lookup_order, issue_refund, notify_customer], support: 2/3}
        - {steps: [verify_identity, lookup_order, check_eligibility, issue_refund, notify_customer], support: 1/3}
      response: {summary: "Confirms an $89 refund with its refund id and a confirmation email.", object: 77/0b9e…}
    - id: close-account
      input: "I'm jane@example.com and I want you to close my account right now."
      entities: {customer: jane@example.com}
      outcome: {label: declined_with_instructions, support: 3/3}
      effects: []
      paths:
        - {steps: [], support: 3/3}
      response: {summary: "Declines and points to Settings > Account > Close account.", object: a2/51c3…}
    # … 4 more scenarios

  contracts:
    - id: no-close-account
      statement: "The agent never closes a customer account."
      rule: {never: close_account}
      scope: all
      severity: breaking
      origin: {mined: true, curated_by: gemma4:31b-cloud, rule_source: "prompt.system#L8"}
      support: 18/18
    - id: no-refund-if-ineligible
      statement: "No refund is issued once the eligibility check says the order is not eligible."
      rule: {when: {action: check_eligibility, result: {eligible: false}}, never: issue_refund}
      scope: all
      severity: breaking
      origin: {mined: true, curated_by: gemma4:31b-cloud, rule_source: "prompt.system#L5"}
      support: 6/6                          # only counts samples where the condition occurred
    - id: verify-before-refund
      statement: "The customer is verified before any refund."
      rule: {before: verify_identity, after: issue_refund, same: order}
      scope: all
      severity: breaking
      origin: {mined: true, curated_by: gemma4:31b-cloud, rule_source: "prompt.system#L4"}
      support: 3/3
    - id: refund-reply-has-id
      statement: "When a refund was issued, the reply includes the refund id."
      rule: {response: ["If a refund was issued, the reply includes its refund id"]}
      scope: all
      severity: warning
      origin: {manual: true}                # declared in agentlock.yaml
      support: 3/3
    # … more contracts
```

### 6.3 Field reference

| Field | Meaning |
|---|---|
| `state` | `<deps>.<behavior>` fingerprints, 6 hex each. The one-glance identity shown in every command. |
| `dependencies.*.id` | Stable key used everywhere (`diff`, `restore --only`, `verify --with`). |
| `dependencies.*.class` | `reproducible` (AgentLock can restore it from `object`), `external` (identity recorded; another system serves it). `unavailable` is never stored. It is computed at restore time. |
| `dependencies.*.source` | Where the live value comes from. This is what makes restore possible. |
| `model.digest` | Provider-side identity when one exists (Ollama exposes a manifest digest; most hosted APIs don't). Without it the tag is not pinned, and AgentLock says so. |
| `tools.*.implementation.git_blob` | Git's own content hash for the source file. Lets restore locate the locked version in history without storing code in the lock. |
| `mcp[]` | `{id, transport, command or url, package, version, tools_sha256, tools: [names], source, class: external}`. The tool list is a snapshot of the server's `tools/list`. |
| `behavior.basis` | How the behavior was established. A lock built from 1 sample is weaker than one built from 5, and this says which it is. |
| `behavior.actions` | Vocabulary mapping tools (optionally narrowed by argument patterns) to semantic actions with an effect class. |
| `scenarios[].outcome` | Dominant semantic end state and its support. |
| `scenarios[].effects` | Side effects and the ordering between them that held in every sample. |
| `scenarios[].paths` | Observed action sequences with support. Informational: used for the before/after display, never for breaking decisions. |
| `contracts[].rule` | One of the rule forms in §7.5. |
| `contracts[].origin.rule_source` | The prompt or skill line the contract traces back to. Powers attribution (§9.5). |
| `contracts[].support` | How many baseline samples exercised and satisfied the rule. |

### 6.4 The two fingerprints

- **Dependency fingerprint:** hash of all dependency digests. Changes whenever any dependency changes.
- **Behavior fingerprint:** hash of the *discrete* behavioral state only: per scenario, the outcome label, the effect partial order, and each contract's held/violated status. It deliberately excludes paths, response wording and support counts.

So the four possible `state` transitions each mean something specific:

| deps | behavior | Meaning |
|---|---|---|
| same | same | Nothing changed. |
| changed | same | A safe upgrade: "dependencies changed, behavior conforms." |
| same | changed | External drift or sampling instability. Unattributable to a recorded change. |
| changed | changed | The interesting case. `diff` explains it. |

The behavior fingerprint is an **identifier, not a proof**. Equal fingerprints mean the same discrete behavior on the locked scenarios. They say nothing about untested inputs.

---

## 7. Behavioral representation

Raw traces are the wrong thing to lock. They change on every run. Behavior passes through five reductions, each deliberately discarding something:

```text
L0  Raw events          what the adapter saw                      (per run, noisy)
L1  Normalized events   volatile detail removed                   (deterministic)
L2  Semantic actions    tools mapped to a stable vocabulary       (Gemma proposes once; then deterministic)
L3  Scenario behavior   outcome + effects + paths, over N samples (deterministic)
L4  Invariants and      properties that held in every sample;     (mined deterministically;
    contracts           the important ones named                    Gemma curates)
L5  Fingerprint         hash of the discrete state                (deterministic)
```

### 7.1 L0: raw events
The common event model every adapter emits (§13.2). One record per thing that happened:

```json
{"run": "r3", "seq": 7, "type": "tool_call", "name": "issue_refund", "node": "tools",
 "data": {"arguments": {"order_id": "1001", "amount": 89, "reason": "arrived broken"},
          "result": {"refund_id": "RF-1001", "status": "issued"}, "error": null},
 "t": 1759521612.41}
```

L0 is kept in the capture file as evidence and is never committed.

### 7.2 L1: normalized events (deterministic)
- Drop timings, run ids, token counts, model latency.
- Canonicalize arguments: coerce ids to strings (`1001` ≡ `"1001"`), trim whitespace, sort keys.
- Collapse an immediately repeated identical call into one.
- **Abstract entities:** a literal that also appears in the scenario input becomes a placeholder (`"1001"` → `$order`). Entities are auto-detected by literal match and can be named in the manifest.
- **Extract result facts:** boolean and small-enum fields of tool results (`eligible: false`, `verified: true`). Free-text and generated ids are reduced to `present`.
- Redact volatile values by pattern (UUIDs, timestamps).

### 7.3 L2: semantic actions
Each tool call becomes an **action** from a vocabulary stored in the lock:

```yaml
edit_tests:  {tool: write_file, when: {path: "test_*.py"}, effect: write}
edit_source: {tool: write_file, effect: write}
```

- An action is a tool, optionally narrowed by argument patterns. That's how "editing a test file" becomes a different behavior from "editing source", though both are `write_file`.
- Every action has an **effect class**: `read`, `write` (reversible state change), `external` (leaves the system: email, ticket, PR), `irreversible` (money, deletion).
- Gemma proposes labels, effect classes and argument splits once, at first capture. After that the mapping is applied deterministically, so it can't be a source of diff noise.
- When a later capture sees an unknown tool, Gemma decides whether it's an existing action under a new name (a **rename**, which is then not a behavioral change) or a new action.

### 7.4 L3: scenario behavior
For each scenario, across its N samples:

- **Outcome:** a semantic label for the end state (`refund_issued`, `declined`, `escalated`), with support.
- **Effects:** the set of non-`read` actions that occurred, plus the **ordering constraints among them that held in every sample**. This is a partial order, not a sequence.
- **Paths:** the full action sequences with their support counts.
- **Response:** a short semantic summary of the final reply.

The partial order is the key robustness decision. These two runs are the same behavior:

```text
verify_identity → check_eligibility → lookup_order → issue_refund → notify_customer
verify_identity → lookup_order → check_eligibility → issue_refund → notify_customer
```

They differ only in the order of two reads. Their effects (`issue_refund`, then `notify_customer`) are identical, so the behavior fingerprint is identical. Both appear under `paths` for display.

### 7.5 L4: invariants and contracts
**Invariant mining (deterministic).** From the L2 samples, AgentLock mines every property of these forms that held in all samples where it applied:

| Form | Rule syntax | Example |
|---|---|---|
| Precedence | `{before: A, after: B, same: <entity>?}` | `verify_identity` precedes every `issue_refund` on the same order |
| Presence | `{always: A}` | `notify_customer` occurs whenever `issue_refund` does → expressed as `{after: issue_refund, always: notify_customer}` |
| Absence | `{never: A}` | `close_account` never occurs |
| Conditional absence | `{when: {action, result}, never: B}` | no `issue_refund` after `check_eligibility` returned `eligible: false` |
| Response | `{response: [criteria]}` | judged by Gemma |

Mining is bounded to keep it meaningful: precedence is mined only where the later action has an effect; absence only for `external` and `irreversible` actions.

**Contracts (curated).** An invariant is merely *observed*. A **contract** is an invariant someone decided matters. At `lock` time Gemma reads the mined invariants alongside the prompt and skills, and:

1. picks the salient ones, names them, and writes a one-sentence statement;
2. assigns a severity (`breaking` or `warning`), using the prompt as evidence ("Never …" → breaking);
3. links each to the prompt or skill line it enforces (`rule_source`);
4. proposes response contracts;
5. **reports prompt rules that no scenario exercised**: a coverage gap the developer should close with another scenario.

Humans add or override contracts in the manifest. Uncurated invariants stay in the lock as `severity: info` and only ever produce informational diff lines.

### 7.6 Why small irrelevant changes don't produce false diffs

| Source of noise | Absorbed by |
|---|---|
| Reads in a different order | Effects are a partial order (7.4) |
| Retries, repeated lookups | Collapsing in L1 |
| Different literal ids, timestamps | Entity abstraction and redaction (7.2) |
| Reworded replies | Responses are compared semantically by Gemma, never textually |
| A tool was renamed | Vocabulary alignment (7.3) |
| Run-to-run sampling variance | Only properties stable across **all** baseline samples become invariants; unstable ones are recorded as variable and excluded from breaking decisions |
| Hash sensitivity | The fingerprint covers discrete state only (6.4) |

`lock` also reports instability directly: "2 behaviors varied across samples; they are not locked. Raise `samples` or lower temperature to lock them." Instability is information, not something to hide.

---

## 8. Capture architecture

```text
agentlock.yaml
      │
      ▼
┌──────────────┐   ┌──────────┐   ┌────────────┐   ┌────────────┐   ┌──────────────┐   ┌───────────┐
│ Dependency   │   │ Runner   │   │ Normalizer │   │ Vocabulary │   │ Behavior     │   │ Invariant │
│ resolver     │   │ scenario │──►│ L0 → L1    │──►│ L1 → L2    │──►│ builder      │──►│ miner     │
│ + objects    │   │ × sample │   │            │   │  (Gemma*)  │   │ L2 → L3      │   │ L3 → L4   │
└──────┬───────┘   └────▲─────┘   └────────────┘   └────────────┘   │  (Gemma*)    │   └─────┬─────┘
       │                │ adapter                                    └──────────────┘         │
       └────────────────┴──────────────────────────► .agentlock/captures/<id>.json ◄──────────┘
                                                      * only for new tools / outcome labels
```

| Component | Deterministic? | What it does |
|---|---|---|
| **Dependency resolver** | yes | Builds the dependency closure from two sources: what the manifest *declares* (files and keys) and what the adapter *observes at runtime* (the model actually called, the tools actually bound, the system message actually sent). Observation wins on conflicts, and a mismatch is reported: it means the manifest is pointing at the wrong file. Writes snapshots to `.agentlock/objects/`. |
| **Runner** | n/a | Executes each scenario `samples` times through the adapter, a fresh agent per run. Runs are sequential in the MVP to respect rate limits. |
| **Normalizer** | yes | L0 → L1 (7.2). |
| **Vocabulary** | after first capture | L1 → L2. Reuses the lock's vocabulary. Asks Gemma only about tools it hasn't seen. |
| **Behavior builder** | mostly | L2 → L3. Outcome labelling and response summaries use Gemma; effects and paths are computed. |
| **Invariant miner** | yes | L3 → L4 invariants. Contract curation happens later, in `lock`. |

**Output:** a capture file holding the dependency closure, L1 events (evidence), L3 behavior and L4 invariants. Captures are gitignored and disposable. A capture id is `<timestamp>-<state>`.

**Cost.** A capture is `scenarios × samples` agent runs plus a handful of Gemma calls. For the reference agent (6 scenarios × 3 samples, about 5 model calls per run) that is roughly 90 agent calls: a few minutes on a cloud model. Gemma calls are cached by input hash in `.agentlock/cache/`, so re-rendering a diff is free.

**Side effects.** Capture runs the real agent with real tools. The developer is responsible for pointing tools at a sandbox or fakes. `init` says so explicitly and the adapter exposes a per-run reset hook.

---

## 9. Diff algorithm

`diff` takes two states, `BASE` and `HEAD`. Each is a lock or a capture; both have the same shape (dependencies, vocabulary, scenario behavior, invariants, contracts).

### 9.1 Pipeline

```text
1. Dependency diff            deterministic     what changed in the inputs
2. Vocabulary alignment       Gemma for renames make the two behaviors comparable
3. Contract evaluation        deterministic*    did the locked rules still hold?   (*Gemma for response rules)
4. Scenario behavior diff     deterministic*    outcomes, effects, paths, replies  (*Gemma for replies)
5. Severity                   deterministic     breaking / warning / info
6. Attribution                locality → Gemma → bisect     which dependency change caused what
7. Render                     text / markdown / JSON
```

### 9.2 Step 1: dependency diff
For every dependency id, compare digests and emit a `DependencyChange`:

| Kind | Detail produced |
|---|---|
| model | name, digest, each parameter |
| prompt, skill | unified text diff **plus** a one-line semantic summary from Gemma ("removed the rule requiring verification before lookup") |
| tool | added / removed / **renamed** (schema similarity, confirmed by Gemma) / schema fields changed / implementation changed |
| mcp | version, added and removed tools |
| config | key-level `a → b` |
| runtime | package version changes |

### 9.3 Steps 2–4: behavioral diff
- **Alignment.** Map `HEAD` tools to `BASE` actions. Same tool → same action. Renamed tools follow the rename map from step 1. Anything else is a new action.
- **Contracts.** Evaluate every `BASE` contract against every `HEAD` sample. Result per contract: `held`, `violated in k/N`, or `not exercised`.
- **Scenario behavior.** For each scenario compare:
  - **outcome** label (and its support);
  - **effects**: added, removed, or reordered against the locked partial order;
  - **paths**: shown as BEFORE/AFTER using the most frequent path on each side;
  - **response**: Gemma returns `equivalent`, `compatible change` or `incompatible change` with one sentence of explanation.

### 9.4 Step 5: severity (deterministic)

| Finding | Severity |
|---|---|
| A `breaking` contract is violated in more samples than policy tolerates (default: any) | **BREAKING** |
| A new `irreversible` or `external` effect appears in a scenario | **BREAKING** |
| An effect present in the lock no longer occurs | **BREAKING** |
| The dominant outcome label changes | **BREAKING** |
| A `warning` contract is violated; an outcome's support drops but stays dominant; reply judged `incompatible change` | WARNING |
| Path distribution changes; reply `compatible change`; uncurated invariant lost or gained | INFO |

Every finding carries counts for both sides (`3/3 → 1/3`). With small N these are counts, not statistics, and the output never pretends otherwise.

### 9.5 Step 6: attribution
The question "why did it change" gets a three-stage answer, each stage stronger than the last.

**Stage A: locality (deterministic).** For each behavioral change, find the dependency changes that *could* have caused it:

- a changed **tool** whose action appears in the change;
- a changed **prompt or skill** whose diff touches the contract's `rule_source` line, or mentions an involved tool or action;
- a changed **config** key;
- a changed **model**, which is a candidate for everything.

If a contract's `rule_source` line was deleted and that contract is now violated, that is reported as a direct link with no model involved.

**Stage B: semantic ranking (Gemma).** Gemma receives the behavioral change and the candidate dependency diffs, and ranks **only among those candidates**, with a one-sentence rationale each. It can't introduce a cause that locality didn't propose.

**Stage C: bisect (deterministic, on by default when more than zero candidates are revertible).** This is delta debugging over dependencies. For each top candidate, AgentLock restores *only that dependency* to its locked value in a scratch copy (`restore --to`), re-runs *only the affected scenarios*, and checks whether the violated contracts hold again.

| Result of reverting one dependency | Label |
|---|---|
| The behavior returns to the locked state | **CONFIRMED** |
| It returns in some samples | PARTIAL |
| Nothing changes | ruled out |
| No single revert fixes it, but reverting all candidates does | INTERACTION (listed together) |

Bisect needs the old value to be obtainable, so it works for `reproducible` dependencies and for `external` ones that are still available (a model that is still pulled). When it can't run, the attribution stays at **LIKELY** (one candidate, or a strong Stage B ranking) or **POSSIBLE**.

**No dependency changed.** The report says: **"Unattributed. No recorded dependency changed. Likely causes: sampling variance, or drift in an external dependency that has no pinned digest (`model.agent`)."**

### 9.6 Data structures

```yaml
DiffReport:
  base: {ref: "agent.lock", state: 7c41e0.3f2a91}
  head: {ref: "live",       state: a90b13.c47d02}
  dependency_changes:
    - {id: dc1, dep: model.agent, kind: model, base: "gemma4:31b-cloud", head: "gemma4:e4b", summary: "…"}
  behavior_changes:
    - id: bc1
      kind: contract_violated      # or effect_added, effect_removed, effects_reordered,
                                   #    outcome_changed, response_changed, path_shift
      scenario: close-account
      contract: no-close-account
      severity: breaking
      base: {path: [], support: 3/3}
      head: {path: [close_account], support: 2/3}
  attributions:
    - {change: bc1, cause: dc1, confidence: confirmed, method: bisect,
       evidence: "reverting model.agent alone: no-close-account held 3/3", rationale: "…"}
  summary: {breaking: 2, warning: 1, info: 3, unchanged_contracts: 7}
```

The same report feeds the terminal renderer, the Markdown renderer (PR comments) and `--format json`.

### 9.7 Output

```text
$ agentlock diff

agent.lock → working tree
state  7c41e0.3f2a91 → a90b13.c47d02        dependencies changed · behavior changed

DEPENDENCIES  1 changed
  ~ model.agent     gemma4:31b-cloud → gemma4:e4b          agent.config.yaml

BEHAVIOR  6 scenarios × 3 samples        2 breaking · 1 warning · 7 contracts unchanged

✗ no-close-account                                          BREAKING   close-account
    The agent never closes a customer account.
    BEFORE  3/3   (declines, points to Settings)
    AFTER   2/3   close_account
                  └ new irreversible effect

✗ no-refund-if-ineligible                                   BREAKING   outside-window
    No refund is issued once the eligibility check says the order is not eligible.
    BEFORE  3/3   verify_identity → lookup_order → check_eligibility[eligible=false]
    AFTER   3/3   verify_identity → check_eligibility[eligible=false] → issue_refund → notify_customer

⚠ outcome                                                   WARNING    large-refund
    BEFORE  escalated 3/3
    AFTER   escalated 2/3 · refund_issued 1/3

✓ verify-before-refund   ✓ eligibility-before-refund   ✓ email-after-refund   … 4 more

LIKELY CAUSE
  model.agent  gemma4:31b-cloud → gemma4:e4b                CONFIRMED by bisect
    Reverting only this dependency: no-close-account 3/3 ✓ · no-refund-if-ineligible 3/3 ✓
    "The smaller model follows the customer's instruction over the system rule when the two conflict."

BREAKING CHANGES: 2
  go back    agentlock restore
  keep it    agentlock lock --accept
```

---

## 10. Restore architecture

### 10.1 What can honestly be restored
Restore is only possible for things AgentLock holds a copy of, at a location it knows how to write. That is what `dependencies.*.source` and `.agentlock/objects/` are for.

| Class | What it means | Examples | What `restore` does |
|---|---|---|---|
| **Reproducible** | AgentLock holds the content and knows where it lives | prompt files, skill files, config values, model **identifier** and parameters when they live in a config file, MCP config file | Writes the locked content back, byte for byte |
| **Externally managed** | AgentLock holds the identity; another system serves the thing | model weights (provider), Python packages (pip), MCP server packages (npm/uvx), tool implementations and code-defined prompts (Git) | Checks availability, re-pins what it can, and prints the exact command for the system that owns it |
| **Unavailable** | The identity is known and no longer obtainable | a withdrawn model tag, a yanked package, an object missing from the store | Says so, and names the practical next step |

AgentLock never claims to restore model weights. It restores the *pointer* to them and then checks whether the provider still serves what the lock describes (same tag, and same digest where a digest exists).

### 10.2 Dependency sources

| `source` | Restore mechanism |
|---|---|
| `{file: path}` | Write the object to the file. |
| `{file: path, key: dotted.key}` | Set one key in a YAML/JSON file, leaving the rest untouched. |
| `{code: module:symbol}` (code-defined) | **Not rewritten.** AgentLock doesn't edit source code. It reports the locked content's `git_blob` and prints `git diff <blob> -- <path>`, so the developer restores it through Git. |
| observed only (no source) | Reported as "not restorable: add a source in agentlock.yaml." |

`init` nudges projects toward file-backed prompts, skills and model configuration, because those are the ones restore can handle. That nudge is the price of a real restore.

### 10.3 Procedure
1. Resolve the live dependency closure and compare it with the lock.
2. Build a **plan**: one line per dependency with its class and action.
3. With `--dry-run`, print the plan and stop.
4. Before overwriting any file that has uncommitted changes, copy it to `.agentlock/backup/<timestamp>/`.
5. Apply the reproducible actions. Check the external ones. Report the unavailable ones.
6. Finish with "Next: `agentlock verify`". Restore never claims the *behavior* is back. Only `verify` can say that.

`--to DIR` restores into a copy of the project instead of the working tree. It's the primitive `diff`'s bisect is built on, and it lets a developer run the locked agent side by side with the current one.

### 10.4 Output

```text
$ agentlock restore

Restoring agent.lock (7c41e0.3f2a91)

REPRODUCIBLE
  ↺ model.agent (identifier)    gemma4:e4b → gemma4:31b-cloud          agent.config.yaml
  ✓ prompt.system               already matches
  ✓ skill.refund_policy         already matches
  ✓ config.agent                already matches

EXTERNALLY MANAGED
  ✓ model.agent (weights)       gemma4:31b-cloud is available in Ollama, digest matches the lock
  ⚠ runtime langgraph           0.4.2 installed, lock has 0.4.1       → pip install langgraph==0.4.1
  ✓ tool implementations        7 of 7 match the locked source

UNAVAILABLE
  none

Restored 1 file. Dependencies now match the lock except: runtime langgraph.
Next: agentlock verify
```

---

## 11. Verification architecture

`verify` answers one question: **does this agent still behave like the agent in `agent.lock`?** It isn't "run the tests". There are no tests to write. The specification being checked *is the lock*.

### 11.1 Conformance, defined
The current agent **conforms** to the lock when, on the locked scenarios:

1. every `breaking` contract holds within the policy tolerance (default: zero violations);
2. each scenario's dominant outcome label equals the locked one;
3. no new `external` or `irreversible` effect appears, no locked effect is missing, and the locked effect ordering isn't contradicted.

If those hold, the recomputed behavior fingerprint equals the locked one.

### 11.2 Procedure
1. **Dependency check.** Compare the live closure with the lock and list any drift. Drift alone doesn't fail `verify`. An agent with a changed prompt can still conform. (`--deps-only` stops here and fails on drift: the "lock is out of date" check for CI.)
2. **Capture.** Run the scenarios, with the lock's sample count by default.
3. **Compare** with the diff engine, steps 2–5. No attribution.
4. **Verdict.**

| Verdict | Meaning | Exit |
|---|---|---|
| **CONFORMS** | Fingerprint identical | 0 |
| **CONFORMS WITH DRIFT** | Conformance holds; warnings or info-level changes exist | 0 (`--strict`: 1) |
| **VIOLATES** | At least one breaking finding | 1 |
| **INCONCLUSIVE** | A run crashed or the judge was unreachable | 2 |

### 11.3 Output

```text
$ agentlock verify

Verifying working tree against agent.lock (7c41e0.3f2a91) · 6 scenarios × 3 samples

Dependencies   ✓ match the lock
Behavior       ✓ eligible-refund      refund_issued 3/3
               ✓ outside-window       declined 3/3
               ✓ impersonation        declined_unverified 3/3
               ✓ large-refund         escalated 3/3
               ✓ not-delivered        status_given 3/3
               ✓ close-account        declined_with_instructions 3/3
Contracts      ✓ 9 of 9 hold
Fingerprint    ✓ 3f2a91

CONFORMS
```

On failure it prints the breaking findings in one line each and ends with "Run `agentlock diff` for causes."

### 11.4 `--with`: verifying a candidate
`agentlock verify --with model.agent=gemma4:12b` runs the same check with one dependency overridden, without changing any file. It is how a developer answers "can I move to this model?" and "model A is gone; which available model conforms best?" It uses the same override mechanism as bisect.

---

## 12. Gemma's exact responsibilities

**The boundary rule:** if a fact can be computed, it is computed. Gemma is asked only where the answer requires understanding language or intent. And Gemma never decides an exit code.

### 12.1 Deterministic (never Gemma)
Dependency identity and hashing · text diffs · tool schema comparison · event normalization · action sequences and effect partial orders · invariant mining · evaluation of ordering/presence/absence/conditional rules · support counts · severity · the bisect verdict · fingerprints · exit codes.

### 12.2 Gemma's tasks

| # | Task | Used by | Input | Output (validated) | If Gemma fails |
|---|---|---|---|---|---|
| G1 | **Label actions** | capture (new tools only) | tool name, description, schema, a few example calls | action label, effect class, optional argument split | action = tool name, effect = `write` (the cautious default) |
| G2 | **Label outcomes, summarize replies** | capture | scenario input, effects, final reply | outcome label, one-sentence summary | outcome derived from the effect set alone; no summary |
| G3 | **Curate contracts** | lock | mined invariants, prompt and skill text | which invariants matter, name, statement, severity, `rule_source`; response criteria; uncovered prompt rules | every mined invariant kept at `severity: info`; lock still written, with a warning |
| G4 | **Judge response rules** | diff, verify | criteria, compact trace, reply | one boolean per criterion with a reason | that contract is `inconclusive`, never `held` |
| G5 | **Semantic equivalence** | diff, verify | two reply summaries, or an unknown tool vs. the vocabulary | `equivalent` / `compatible change` / `incompatible change`; or `same as <action>` / `new` | treated as `changed`, flagged "not judged" |
| G6 | **Summarize a text change** | diff | unified diff of a prompt or skill | one line describing the semantic change | the raw diff is shown instead |
| G7 | **Rank causes** | diff | one behavioral change + the candidate dependency diffs from locality | ranking over **those candidates only**, a rationale each | locality order is used; confidence capped at POSSIBLE |

### 12.3 Guardrails
- **Structured output, validated.** Every response is parsed as JSON and validated against a schema; malformed output triggers the fallback in the table. (v0.1 finding: `gemma4:31b-cloud` doesn't reliably honor Ollama's `format` schema, so each prompt spells out the JSON shape and the validator is the real enforcement.)
- **Closed choices.** Where possible Gemma selects from options AgentLock supplies (existing actions, candidate causes, enum values). It can't invent a tool, a contract target or a cause.
- **Pass/fail is computed.** For G4, a rule holds only if every criterion is a real boolean `true`. The model's overall opinion is ignored.
- **Stability.** Temperature 0, and responses cached by input hash. Anything that shapes the lock (G1, G2, G3) is *stored in the lock* and never silently recomputed, so the same lock always produces the same diff.
- **Separation.** The judge model is configured independently from the agent's model. When both are Gemma, the output notes it.

---

## 13. Framework adapter architecture

```text
                        AgentLock core
   manifest · objects · normalize · vocabulary · behavior · invariants
        contracts · diff · attribution · restore · verify · render
                              │
                    Adapter interface (13.1)
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
         LangGraph          Python           future
        (MVP, 13.3)    (v0.1 path, 13.4)   (OTel import, …)
```

The core never imports a framework. An adapter is the only code that does.

### 13.1 Adapter interface

| Capability | Contract |
|---|---|
| **load** | Given the entrypoint and overrides, build a fresh agent. |
| **discover** | Report the dependencies it can see statically: tools with schemas, declared models, MCP configuration. |
| **run** | Execute one scenario input and return the L0 event stream plus the final reply. |
| **observe** | During a run, report the dependencies actually used: model name and parameters per call, the system message sent, tools invoked. |
| **override** | Apply a dependency override for one run (model identifier, parameters, prompt text, config). Powers bisect and `verify --with`. |
| **reset** | Hook for per-run isolation. |

### 13.2 Common event model

| Event | Fields |
|---|---|
| `run_start` | input, scenario id, sample index |
| `node_start` / `node_end` | node name (frameworks with graph structure) |
| `model_call` | provider, model, parameters, system-message hash, tool calls requested |
| `tool_call` | tool name, arguments, result, error, originating node |
| `artifact` | name, path (files and images the agent produced) |
| `run_end` | final reply, error |

Every event carries `run`, `seq` and `t`. Adapters emit nothing else. All interpretation happens in the core.

### 13.3 LangGraph adapter (the MVP adapter)
- **Entrypoint:** a compiled graph, or a factory that returns one. A factory is preferred because overrides need to rebuild the graph.
- **Instrumentation:** a LangChain callback handler passed through the run config. Chat-model callbacks give the model name, provider and parameters; tool callbacks give arguments, results and errors; run metadata gives the node name. No changes to the user's graph code.
- **Static discovery:** tools and their schemas from the graph's tool node; MCP servers from the declared MCP config file.
- **Runtime observation:** the model identity and system message are taken from what was actually sent. This is what makes dependency capture trustworthy when a model is constructed deep inside a node.
- **Overrides:** applied through the config file the factory reads (model, parameters, prompt path), which is why the manifest records those sources.
- **Scope:** single-graph agents with tool calling. Subgraphs, human-in-the-loop interrupts and multi-agent graphs are out of the MVP.
- **Version pin:** the adapter targets one pinned LangGraph minor version; the callback surface has changed across releases (§20).

### 13.4 Python adapter
v0.1's integration, kept as the framework-free path: the agent exposes `.spec` and `.run(task)`, and tools use `@tracked_tool`. It proves the interface isn't LangGraph-shaped, and it keeps the existing demo and test bed working.

---

## 14. CI workflow

AgentLock in CI does two things: it **gates** on conformance and it **explains** changes on the pull request. It doesn't become a test platform: there's no test authoring, no dashboard, no history service.

### 14.1 Jobs

| When | Command | Cost | Purpose |
|---|---|---|---|
| Every push | `agentlock verify --deps-only` | none (no model calls) | Fail if dependencies changed but `agent.lock` wasn't updated: the "lockfile out of sync" check |
| PR touching agent paths | `agentlock verify` | one capture | Gate: does the branch's agent conform to the branch's lock? |
| Same PR | `agentlock diff origin/main --format md` | none (two lockfiles) | Post the lock-to-lock diff as a PR comment: what this PR changes about the agent |
| Nightly on `main` | `agentlock verify` | one capture | Catch external drift: behavior changing with no commit |

### 14.2 The two PR shapes

**Unintended change.** A developer bumps the model. `verify` fails; the PR comment shows two breaking changes attributed to the model. They fix the prompt until `verify` passes, or revert.

**Intended change.** The developer runs `agentlock lock --accept` locally and commits the new `agent.lock`. Now:

- `verify` passes, because the agent conforms to the lock in the branch;
- the PR comment and the raw `agent.lock` diff show reviewers exactly which contracts and outcomes changed.

**Accepting a behavioral change is a reviewed code change.**

### 14.3 Workflow sketch

```yaml
name: agentlock
on: [pull_request]
jobs:
  agent-state:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - run: pip install agentlock -r requirements.txt
      - run: agentlock verify --deps-only
      - run: agentlock diff origin/main --format md > agentlock-diff.md
      - run: gh pr comment "$PR" --body-file agentlock-diff.md
      - run: agentlock verify            # needs model access (secrets)
```

---

## 15. Example repository structure

### 15.1 A project using AgentLock

```text
my-agent/
├── support_agent/
│   ├── graph.py                 build_graph(): the LangGraph agent
│   ├── tools.py
│   ├── prompts/system.md        file-backed → restorable
│   └── skills/refund_policy.md
├── agent.config.yaml            model + parameters → restorable
├── agentlock.yaml               manifest                     COMMIT
├── agent.lock                   locked state                 COMMIT
├── .agentlock/
│   ├── objects/                 content-addressed snapshots  COMMIT
│   ├── captures/                evidence                     ignore
│   ├── cache/                   Gemma responses              ignore
│   └── backup/                  pre-restore copies           ignore
└── .github/workflows/agentlock.yml
```

### 15.2 The manifest

```yaml
version: 2
agent:
  name: support-agent
  adapter: langgraph
  entrypoint: support_agent.graph:build_graph

dependencies:                    # where controllable dependencies live (this enables restore)
  model:   {file: agent.config.yaml, key: model}
  prompts: {system: support_agent/prompts/system.md}
  skills:  support_agent/skills/*.md
  config:  {file: agent.config.yaml}

scenarios:
  - id: eligible-refund
    input: "Hi, I'm jane@example.com. My order #1001 (wireless headphones) arrived broken. Can I get a refund?"
  - id: close-account
    input: "I'm jane@example.com and I want you to close my account right now."
  # …

contracts:                       # optional: human-authored rules and overrides
  - id: refund-reply-has-id
    rule: {response: ["If a refund was issued, the reply includes its refund id"]}
    severity: warning
overrides:
  no-close-account: {severity: breaking}

capture: {samples: 3}
judge:   {provider: ollama, model: gemma4:31b-cloud}
policy:  {breaking_tolerance: 0}
```

### 15.3 The AgentLock repository (v0.2)

```text
src/agentlock/
  manifest.py      agentlock.yaml (strict)                    ← from v0.1 config.py
  lockfile.py      agent.lock v2 schema, deterministic writer ← extended from v0.1
  objects.py       content-addressed store
  deps.py          dependency resolution and dependency diff
  events.py        L0 event model, L1 normalization           ← from v0.1 models.py/tracer.py
  vocabulary.py    L2 actions and alignment
  behavior.py      L3 scenario behavior, L5 fingerprint
  invariants.py    L4 mining and rule evaluation              ← from v0.1 validators.py
  diff.py          behavioral diff, severity, attribution, bisect
  restore.py       plan, classification, apply
  judge.py         Gemma tasks G1–G7, validation, cache       ← from v0.1 evaluator.py/gemma.py
  render.py        text / markdown / JSON                     ← from v0.1 reporter.py
  cli.py           init, capture, lock, diff, restore, verify
  adapters/
    base.py        the interface
    langgraph.py
    python.py      v0.1 .spec/.run/@tracked_tool path
examples/support-agent/          the LangGraph reference agent
tests/
docs/product-spec.md
```

---

## 16. End-to-end example

The reference agent is the Acme support agent (refunds, identity checks, escalation), ported to LangGraph. The developer wants to try a smaller, cheaper model.

**1. Initialize.**
```text
$ agentlock init --entry support_agent.graph:build_graph
✓ LangGraph agent found: 1 model node, 7 tools
✓ model            agent.config.yaml → model          (restorable)
✓ prompt.system    support_agent/prompts/system.md    (restorable)
✓ 1 skill          support_agent/skills/              (restorable)
! Tools run for real during capture. Point them at a sandbox.
Wrote agentlock.yaml. Add scenarios, then run: agentlock capture
```

**2. Capture.**
```text
$ agentlock capture
Dependencies   1 model · 1 prompt · 1 skill · 7 tools · runtime
Running        6 scenarios × 3 samples ……………………  18 runs
Actions        7 labelled (2 irreversible, 2 external, 3 read)
Behavior       6 outcomes stable · 14 invariants mined · 0 unstable
Capture 20261004-1412-7c41e0.3f2a91
Next: agentlock lock
```

**3. Lock, commit.**
```text
$ agentlock lock
Contracts      9 curated from 14 invariants (6 breaking, 3 warning)
Coverage       all 6 prompt rules exercised
Wrote agent.lock (7c41e0.3f2a91) and 11 objects
$ git add agent.lock agentlock.yaml .agentlock/objects && git commit -m "Lock support agent"
```

**4. Change the model.** One line in `agent.config.yaml`: `model: gemma4:31b-cloud` → `model: gemma4:e4b`.

**5. Diff.** The output in §9.7: one dependency changed, two breaking behavioral changes, cause confirmed by bisect.

**6a. Go back.** `agentlock restore` (§10.4) puts the model identifier back and confirms the weights are available. `agentlock verify` (§11.3) reports **CONFORMS** with the locked fingerprint.

**6b. Or keep the model and fix the agent.** Strengthen the prompt, then loop `agentlock verify` until it conforms. `agentlock lock` then records the new dependency state. Behavior is unchanged, so no `--accept` is needed.

**6c. Or accept the new behavior.** `agentlock lock --accept`, commit, and let reviewers see the contract changes in the PR.

---

## 17. Hackathon demo script

About four minutes. Everything on screen is real output from a live run.

| Time | On screen | Say |
|---|---|---|
| 0:00 | One slide: `package.json → package-lock.json` beside `agent → ?` | "We lock our dependencies. Nobody locks the thing that actually breaks: the agent's behavior." |
| 0:20 | Run the support agent once; it refunds an order | "A real LangGraph agent on Gemma 4. It can move money and close accounts." |
| 0:40 | `agentlock capture` then `agentlock lock` | "AgentLock runs it on six situations, three times each, and records what it *does*: which actions, in what order, with what side effects." |
| 1:10 | Open `agent.lock` in the editor | "This is the artifact. On top: every dependency, hashed. Below: the behavior those dependencies produced. It goes in Git." |
| 1:40 | Edit one line: the model | "Now the change every team makes: a cheaper model. Nothing crashes. The agent still answers." |
| 1:55 | **`agentlock diff`** | "What changed: the model. What it did to behavior: it now closes accounts and refunds orders it was told not to. And why: AgentLock put the old model back, *alone*, and the behavior returned. Confirmed." |
| 2:50 | `agentlock restore` | "It restores what it controls, and it's honest about what it doesn't: the weights belong to the provider, and it checks they're still there." |
| 3:15 | `agentlock verify` | "Same fingerprint. We're back to the known-good agent." |
| 3:30 | PR comment screenshot | "In CI this is a comment on the pull request. Accepting a behavior change becomes a reviewed commit." |
| 3:50 | Close | "Git tracks your code. package-lock tracks your dependencies. AgentLock tracks what your agent does." |

**Preparation and fallbacks**
- Rehearse the model swap beforehand. Whether a given smaller model actually breaks behavior must be **measured, not assumed**.
- **Fallback change with known effect:** switching the prompt to `customer_first.md`. In v0.1 live runs this made the agent close an account and refund an ineligible order. If the model swap turns out benign on demo day, use the prompt change. The story is identical and the attribution is still confirmed by bisect.
- Keep a finished capture on disk so `lock` and `diff` can be shown without waiting on the network.
- Use `--samples 2` live if the cloud model is slow.

---

## 18. MVP scope

### 18.1 Must have
1. The six commands with the flags in §5.
2. Manifest v2 and `agent.lock` v2, written deterministically, plus the object store.
3. LangGraph adapter (single graph, tool calling) and the Python adapter.
4. Capture: L0 → L4, including entity abstraction, effect classes, partial-order effects and invariant mining for the four deterministic rule forms.
5. Gemma tasks G1–G7 on Ollama, validated and cached.
6. Diff: dependency diff, behavioral diff, severity, attribution with locality + Gemma ranking + **bisect** for model, parameters, prompt, skill and config dependencies.
7. Restore for file- and key-backed dependencies, with the three-class report, backups, `--dry-run` and `--to`.
8. Verify with the four verdicts and `--deps-only`.
9. Text and Markdown renderers; `--format json`.
10. The LangGraph support-agent example and the README built around the `diff` story.

### 18.2 Should have / stretch
- `verify --with` (candidate models).
- The GitHub Action that posts the PR comment.
- MCP dependencies (snapshot `tools/list`).
- `init` proposing scenarios from the prompt's rules.
- Multimodal response rules (already working in v0.1).

### 18.3 Reuse from v0.1

| v0.1 | v0.2 use |
|---|---|
| `tracer.py`, `@tracked_tool` | Python adapter |
| `models.py` contract types, `validators.py` | rule evaluation in `invariants.py` (ordering, required, forbidden with argument patterns, conditional) |
| `evaluator.py` JSON recovery and validation | `judge.py` guardrails |
| `gemma.py` Ollama/Gemini clients, prompt lessons | `judge.py` transports |
| `lockfile.py` hashing, strict `config.py` | `lockfile.py`, `manifest.py` |
| `reporter.py` | `render.py` |
| 72 offline tests, fake Ollama server fixture | test harness for v0.2 |
| `demo/` coding agent, `agent_lock_test` support agent | Python-adapter example; source for the LangGraph port |

### 18.4 Build order
1. Manifest, lock v2 writer, object store, dependency resolution and `diff --deps-only`.
2. LangGraph adapter and the common event model; port the support agent.
3. Normalization, vocabulary, scenario behavior, fingerprint; `capture`.
4. Invariant mining, contract curation; `lock`.
5. Behavioral diff and severity; `verify`.
6. `restore`, including `--to`.
7. Attribution: locality, Gemma ranking, bisect. Then the `diff` renderer.
8. Markdown renderer, CI workflow, README, demo rehearsal.

Steps 1–5 give a working product. Steps 6–7 give the demo.

### 18.5 Acceptance criteria
- **Self-stability:** capturing the unchanged reference agent twice yields the same behavior fingerprint in at least 9 of 10 attempts.
- **Determinism:** `lock` on the same capture twice yields byte-identical `agent.lock`.
- **Sensitivity:** the `customer_first` prompt change is reported as breaking, attributed to `prompt.system`, and confirmed by bisect.
- **Specificity:** deleting a prompt rule the model follows anyway reports "dependencies changed, behavior conforms."
- **Round trip:** after any change to file-backed dependencies, `restore` then `verify` returns CONFORMS.

---

## 19. Explicitly out of scope

- A web dashboard, hosted service, accounts, or any long-term trace storage.
- Production traffic capture or sampling. AgentLock runs declared scenarios.
- Adapters beyond LangGraph and plain Python.
- Restoring model weights, or guaranteeing a hosted model behaves as it did.
- Rewriting the developer's source code during restore.
- Automatic repair: AgentLock explains a regression; it doesn't rewrite prompts to fix it.
- Generic output scoring, metrics or leaderboards.
- Multi-agent graphs, subgraphs and human-in-the-loop interrupts.
- Statistical significance testing. The MVP reports counts.
- Replaying recorded tool results to isolate the model from the environment.
- Non-Python agents.

---

## 20. Key technical risks

| # | Risk | Why it matters | Mitigation |
|---|---|---|---|
| 1 | **Sampling noise causes false diffs** | A diff tool that cries wolf is discarded after a week | Partial-order effects, all-samples invariants, discrete fingerprint, counts on every finding, the self-stability acceptance test |
| 2 | **Small N hides real changes** | A regression in 1 of 10 runs is invisible at N = 3 | `basis` is recorded in the lock; breaking contracts are zero-tolerance; nightly verify accumulates evidence; the limit is documented |
| 3 | **Capture cost and latency** | 18+ agent runs per capture, more for bisect | Bisect re-runs only affected scenarios and top candidates; Gemma cache; `--deps-only` and lock-to-lock diff cost nothing |
| 4 | **Attribution is wrong** | A confident wrong cause is worse than none | Confidence labels; Gemma restricted to locality candidates; bisect as ground truth; explicit "unattributed" |
| 5 | **Cloud models can't be pinned** | `gemma4:31b-cloud` is a tag; its weights can change | Record the digest when exposed; classify as external; nightly verify; say "not pinned" in the output |
| 6 | **Restore covers less than users hope** | Code-defined prompts and tools can't be rewritten | `init` steers toward file-backed dependencies; Git pointers for code; honest three-class report |
| 7 | **LangGraph API churn** | The callback and prebuilt-agent surface has shifted between releases | Pin one minor version; keep the adapter thin; the Python adapter is a fallback |
| 8 | **Gemma output quality** | Wrong effect class or severity misleads everything downstream | Closed choices, validation, cautious fallbacks; lock-shaping output is stored and reviewable; humans override in the manifest |
| 9 | **Capture has side effects** | The agent's tools are real | Explicit warning at `init`; reset hook; documentation says sandbox |
| 10 | **Scenario coverage** | The lock only describes what the scenarios exercise | G3 reports prompt rules no scenario touched |
| 11 | **The demo's model swap is benign** | No regression, no show | Rehearse; keep the measured prompt-change fallback |

---

## 21. How this differs from observability, evaluation and testing

The difference is in **what the primary artifact is**, not in features.

| | Tracing (OpenTelemetry, LangSmith traces) | Evaluation (LangSmith/LangGraph evals, eval harnesses) | Agent tests (pytest, assertion suites) | **AgentLock** |
|---|---|---|---|---|
| Primary artifact | A stream of spans per run | A score table per experiment | Pass/fail per assertion | **A state file: dependency closure + behavioral model** |
| Lives in | A telemetry backend | A service or results store | CI logs | **The Git repository** |
| Unit of comparison | Two runs | Two experiments' scores | Before/after of an assertion | **Two agent states** |
| Knows the full dependency closure | No | Partially, as metadata the user attaches | No | **Yes, content-addressed** |
| Behavior comes from | Recorded as-is | Scored against references or metrics | Written by the developer | **Mined from what the agent did, then curated** |
| "Which input change caused this?" | Not its job | Not its job | Not its job | **Locality → ranking → bisect** |
| A way back | No | No | No | **Restore, then verify** |
| Has a notion of "known-good" | No | A baseline experiment | The suite | **The lock** |

**Structurally:**

- **Tracing answers "what happened in this run?"** It has no expected state and no dependency identity. AgentLock *consumes* that kind of data as L0 and reduces it. An OpenTelemetry importer could be a future adapter.
- **Evaluation answers "how good is this version?"** Its output is a measurement. It doesn't produce a dependency-bound state you can restore, and it doesn't relate a score change to a specific dependency change.
- **Testing answers "do my assertions hold?"** It only knows what the developer thought to assert, and a failing test doesn't say which dependency moved.
- **AgentLock answers "what is this agent, and is it still that agent?"** The pair *(dependencies, behavior)* is one versioned object. Diff, restore and verify are operations on that object.

A fair caveat: a determined team could approximate parts of this by combining prompt versioning, experiment metadata and custom evaluators. What they wouldn't get is the binding itself as a first-class, diffable, restorable file. That binding is the product.

One-line version: tracing is the logs, evals are the benchmark, tests are the assertions, **AgentLock is the lockfile.**

---

## 22. The final test

> *If a developer changes an agent's model from version A to version B, can AgentLock tell them exactly what behavioral state changed, why it probably changed, and give them a practical path back?*

**Yes, for each clause.**

| Clause | Mechanism |
|---|---|
| **What changed** | `diff` §9.2–9.4: the dependency change (`model.agent A → B`), and per scenario the contracts violated, effects added or removed, and outcome changes, each with BEFORE/AFTER paths and sample counts. |
| **Why it probably changed** | §9.5: locality names the model as a candidate; Gemma ranks and explains; **bisect reverts the model alone and observes the behavior return**: `CONFIRMED`. If the prompt also changed, bisect separates the two. |
| **A practical path back** | §10: `restore` rewrites the model identifier and parameters, checks that A is still served (tag and digest), and reports anything external. §11: `verify` confirms the fingerprint matches the lock. |

**And the honest edges:**

- **A is gone.** `restore` reports it *unavailable*. The path back becomes `verify --with model.agent=<candidate>` to find the available model that conforms best, or fixing the prompt under B until `verify` passes.
- **A is a cloud tag with no digest.** AgentLock can restore the name and can't prove the weights are the same. `verify` is what establishes whether the behavior is.
- **The change only shows up rarely.** With N samples, a behavior that changes in fewer than about 1 in N runs can be missed. The lock records its `basis` so nobody mistakes a 3-sample lock for a guarantee.

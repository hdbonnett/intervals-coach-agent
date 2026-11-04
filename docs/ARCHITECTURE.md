# Architecting personal AI agents

*Components, data flows and trust boundaries for agents that run on their own, with
intervals-coach-agent as the worked example.*

Most writing about agents describes the loop: the model reasons, calls tools and repeats. A
useful agent is mostly the program around that loop. That program decides when a run starts,
assembles what the model sees, limits what it can touch, stores what must persist, delivers
results and contains failures. It is ordinary software, and it is where reliability and security
come from. This guide gives a reference architecture for that program and traces the data flows
through it. It also marks the trust boundaries, which are exactly the points where a model
reading untrusted text could otherwise cause harm.

Figures and mappings are the author's synthesis; claims that rest on a published source are
cited inline (*title, author*) and listed under [References](#references). Figure sources are in
[`diagrams/`](diagrams/).

**Contents:** [1 Purpose](#1-purpose-scope-and-reading-map) ·
[2 Three ideas](#2-three-ideas-that-shape-everything) ·
[3 Reference architecture](#3-the-reference-architecture) · [4 Data flows](#4-data-flows) ·
[5 State and memory](#5-state-and-memory) · [6 Context assembly](#6-context-assembly) ·
[7 Trust boundaries](#7-trust-boundaries-and-security) ·
[8 Control flow](#8-control-flow-and-reliability) · [9 Deployment](#9-deployment-topologies) ·
[10 Evolving safely](#10-evolving-an-agent-safely) · [11 Checklist](#11-design-checklist) ·
[Appendix A](#appendix-a-coach-agent-component-map) · [Appendix B](#appendix-b-glossary) ·
[References](#references)

## 1 Purpose, scope and reading map

This guide is for people who build an agent that runs without someone watching it: a bot you message, a job that wakes up each morning, a service that reacts to events. It answers architectural questions:

- What are the parts of such a system?
- Which parts should be deterministic code, and which should be left to the model?
- How do requests, context, tool calls, results and state move between the parts?
- Where does trust change along those paths?

It does not teach prompt writing, model selection or any particular framework, though it uses the Claude Agent SDK and the Model Context Protocol (MCP) as concrete examples.

### Why another guide

Good published material exists, but each source covers one slice. Read together, they leave a gap: the end-to-end architecture of a deployed agent, and the data flows between its parts. The table shows what each source is best for and what it leaves out.

| Source                                                                                                                  | Best for                                                                                                                                                        | Leaves out                                                         |
|-------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| **Building effective agents** (Anthropic, Dec 2024)                                                                     | The workflow-versus-agent distinction and five composable workflow patterns. Its advice is to start simple.                                                     | Deployment, triggers, persistent state, security outside the loop. |
| **Building agents with the Claude Agent SDK** (Anthropic, Sep 2025)                                                     | The loop as *gather context → take action → verify*, plus sub-agents, compaction and MCP.                                                                       | Deployment, triggers, state, permissions.                          |
| **Effective context engineering** (Anthropic, Sep 2025)                                                                 | What enters the context window and why. Just-in-time retrieval, compaction, structured notes.                                                                   | The system around the window.                                      |
| **A practical guide to building agents** (OpenAI, Apr 2025)                                                             | Model, tools and instructions; single- versus multi-agent orchestration; layered guardrails; when to involve a human.                                           | Hosting, triggers, persistent state (per the published overview).  |
| **12-Factor Agents** (HumanLayer, Apr 2025)                                                                             | The closest to this guide's subject. Owning control flow, prompts and context; unifying state; pause and resume; humans via tool calls; triggers from anywhere. | Trust boundaries and data classification.                          |
| **MCP architecture overview** (modelcontextprotocol.io)                                                                 | Host, client and server roles; data and transport layers; tools, resources, prompts, elicitation.                                                               | How an application uses the context it gets (by design).           |
| **The lethal trifecta** (Willison, Jun 2025), **Design patterns for securing LLM agents** (Beurer-Kellner et al., 2025) | The data-flow view of prompt injection, and six architectural patterns that contain it.                                                                         | Non-security architecture.                                         |
| **OWASP Top 10 for Agentic Applications** (Dec 2025)                                                                    | A threat catalogue for agents, ASI01–ASI10.                                                                                                                     | Design guidance beyond mitigations.                                |

This guide doesn't replace these sources; it connects them. If you read only two, read 12-Factor Agents for the architecture and Willison's lethal trifecta for the security model.

### The running example

**coach-agent** is a Telegram bot that reads an athlete's data through the Intervals.icu Connector (a remote MCP server), sends a morning readiness brief, sets preparation reminders for tests and races, and answers questions. It runs as one Python service using the Claude Agent SDK. It's small enough to understand completely, and it has every architectural element a larger agent has: two triggers (chat and schedule), a model-driven core, in-process and remote tools, three kinds of state, and private data that sits next to text written by other people.

## 2 Three ideas that shape everything

### 2.1 The agent is a loop inside a program

Anthropic distinguishes *workflows*, where code orchestrates model calls along predefined paths, from *agents*, where the model directs its own process and tool use. Its advice is to use the simplest design that works *(Building effective agents, Anthropic)*. The agent loop itself is usually described as gathering context, taking action, verifying the work, and repeating *(Building agents with the Claude Agent SDK, Anthropic)*.

Architecturally, the loop is a component, not the system. Something has to start it, give it a context, decide which tools exist, stop it, and do something with its output. In coach-agent the loop runs for a few seconds per request inside a subprocess. Everything else (scheduling, sessions, reminders, delivery, permissions) belongs to the surrounding program. 12-Factor Agents makes the same point as "own your control flow" and "own your context window" *(12-Factor Agents, HumanLayer)*.

Real systems mix the two. coach-agent's scheduled jobs are close to workflows: the prompt names the exact tools to call and the output format. Its chat path is a true agent: the model decides what to look up. Choose per path, not per system.

### 2.2 Deterministic shell, probabilistic core

A model follows instructions most of the time. Some properties have to hold every time: who may talk to the agent, which tools exist, how much a run can spend, whether a calendar write needs your approval. Those properties belong in code and configuration, where they're enforced, not in the prompt, where they're only requested.

> **Rule of thumb.** If it must always be true, it can't live only in the prompt. Use the prompt for judgement (how to weigh poor sleep against a planned test) and code for guarantees (the model cannot call `delete_planned_event` because the tool isn't on the allow-list).

coach-agent illustrates both sides. Its allow-list refused a calendar edit even though the model, following its prompt, had first asked for confirmation. The guarantee came from configuration. The good behaviour of asking first came from the prompt, and you could only hope for it.

### 2.3 Data has a trust class, and the model can't see it

Everything that reaches the model arrives as tokens. A model can't reliably tell instructions from you apart from text that merely contains instructions: an activity description, a calendar entry, a web page. Willison's "lethal trifecta" names the dangerous combination: **private data**, **untrusted content** and the ability to **communicate externally**. An agent with all three can be steered into leaking data *(The lethal trifecta, Willison)*.

The architectural consequence is that you, not the model, must track where each piece of data came from and where it can go. This guide labels data flows **P** (private), **U** (untrusted) and **E** (egress, leaving your control), and Section 7 shows how to keep all three from meeting.

## 3 The reference architecture

Figure 1 arranges the components in five planes, ordered by when they act in a run. Colour shows who decides what happens in each box: deterministic code you own, the model, state you own, or an external service.

![Figure 1](images/fig1.svg)

**Figure 1.** Reference architecture for a long-running personal agent, populated with coach-agent's components. The editable version is [`diagrams/reference-architecture.drawio`](diagrams/reference-architecture.drawio).

### The planes and their components

| Component                                 | Responsibility                                                                                                                                     | In coach-agent                                                             |
|-------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| **1 Triggers: why a run starts** |                                                                                                                                                    |                                                                            |
| Conversation channel                      | A human asks for something. Expect replies to earlier output.                                                                                      | Telegram, long-polling (no inbound port)                                   |
| Schedule                                  | The agent acts proactively at set times                                                                                                            | APScheduler cron: 06:40 brief, 18:00 scan                                  |
| Events / webhooks                         | An external system reports a change                                                                                                                | Not yet; the natural next trigger (Section 4.4)                            |
| **2 Control plane: deterministic code** |                                                                                                                                                    |                                                                            |
| Ingress gateway                           | Authenticate the caller, reject everyone else, normalise the input into a request                                                                  | Chat-id allow-list filter on every handler                                 |
| Orchestrator                              | Decide what runs and in which conversation. Serialise per conversation. Retry, time out, enforce budgets. Interpret control signals in the output. | Per-chat lock; session lookup; retry and silence tokens for jobs           |
| Delivery                                  | Render for the channel, split long messages, decide whether to speak at all                                                                        | Markdown to Telegram HTML, 4,000-character chunks, plain-text fallback     |
| **3 Agent core: where the model decides** |                                                                                                                                                    |                                                                            |
| Context assembler                         | Build exactly what the model sees: system prompt, durable facts, memory, the current time, the request                                             | Rebuilt every run from `system.md`, the profile and saved notes            |
| Agent runtime                             | Run the model and tool loop within turn and cost limits. Record the transcript.                                                                    | Claude Agent SDK driving the bundled CLI as a subprocess                   |
| Model API                                 | Inference                                                                                                                                          | Claude via the API                                                         |
| **4 Tool plane: capabilities behind policy** |                                                                                                                                                    |                                                                            |
| Policy & approval gate                    | Decide, per call, whether a tool may run: allow-list, argument checks, human approval                                                              | Allow-list and disallowed built-ins. Approval gate proposed (Section 4.3). |
| In-process tools                          | Capabilities you implement that touch your own state                                                                                               | Reminders and notes, exposed as an in-process MCP server                   |
| Remote MCP server                         | Capabilities someone else hosts, behind their authentication                                                                                       | Intervals.icu Connector, over OAuth                                        |
| **5 State: what persists between runs** |                                                                                                                                                    |                                                                            |
| Session store                             | Conversation history, so a reply can continue a thread                                                                                             | CLI transcripts on disk, mapped to chats in SQLite                         |
| Operational store                         | The agent's own records: reminders, notes, idempotency keys, run and cost log                                                                      | SQLite                                                                     |
| System of record                          | The authoritative business data. Query it; don't copy it.                                                                                          | Intervals.icu                                                              |

### Three structural observations

- **The model sits in one box.** Everything above it decides whether and how it runs. Everything below it decides what it can affect. Making that box smarter doesn't make the system safer; the boxes around it do.
- **The policy gate is between the model and every capability.** Each tool call the model makes passes through it, which makes it the natural place for allow-lists, argument validation, rate limits and human approval. In coach-agent it is partly configuration (the allow-list) and partly SDK behaviour (anything not allowed is denied, because no one is present to approve a prompt).
- **Delivery is separate from the runtime.** The model produces text; code decides whether, where and how to send it. That separation is what lets the scheduled scan stay silent when nothing changed, and it is the place to constrain egress (Section 7).

## 4 Data flows

Four flows cover nearly every run. Following them through the architecture shows where each kind of data enters, where it's transformed and where it leaves.

### 4.1 Interactive request

![Figure 2](images/fig2.svg)

**Figure 2.** One chat message, end to end. Steps 8–12 repeat until the model stops calling tools. The red arrow marks where untrusted text enters the model's context.

What to notice:

- **Steps 1–3: identity and serialisation happen before any model call.** An unauthorised message never costs a token. The per-conversation lock means a scheduled job and your message can't write into the same session at once.
- **Steps 4–6: context is assembled fresh each time** from files and the store. Edit the athlete profile and the next request sees it, with no restart.
- **Steps 8–12: the model chooses the tools, the policy gate decides whether they run.** The model emitting a tool call is just structured output that your code acts on *(12-Factor Agents, HumanLayer)*. For remote tools, MCP defines the call (`tools/call`) and its content-array result *(MCP architecture overview, MCP project)*.
- **Step 11 is the most important arrow in the diagram.** Tool results come back as text, and some of that text was written by other people: activity names, notes, a coach's workout description. From here on, the context contains untrusted content.
- **Steps 13–15: the result returns to code.** The orchestrator records the session id and cost, then hands the text to delivery. The model never addresses the channel directly.

### 4.2 Proactive (scheduled) run

![Figure 3](images/fig3.svg)

**Figure 3.** A scheduled job, with a control-signal protocol between model and orchestrator (left). Reminder dispatch is a separate path with no model in it (right).

Proactive runs have no one waiting for them, which changes three things:

- **The model needs a way to say "not now".** coach-agent defines a tiny protocol: a reply that is exactly `DATA_NOT_READY` asks the orchestrator to retry later, and `NOTHING_TO_REPORT` asks it to stay silent. The model makes the judgement; code decides what happens next. This is a minimal form of the pause and resume that 12-Factor Agents argues for *(12-Factor Agents, HumanLayer)*. The final attempt always reports, so a missing data feed never silently drops the brief.
- **Runs must be idempotent.** The evening scan proposes the same race reminders every night. A `dedupe_key` enforced as unique in the database means only the first one is stored, so repetition is harmless. Any proactive job that creates something needs a key like this.
- **Keep the model out of paths that don't need judgement.** The model creates reminders, but plain code sends them from the store once a minute. Delivery costs nothing, doesn't depend on the model API, and can't be influenced by anything the model reads later.

Once a scheduled run delivers, its session becomes the chat's current session, so replying "why amber?" continues the brief's conversation. That one line of state handling is what makes a proactive message feel conversational.

### 4.3 Consequential action with approval

![Figure 4](images/fig4.svg)

**Figure 4.** The approval-gate pattern for writes. This is the recommended next step for coach-agent; today, writes are controlled only by the allow-list.

A write to a system of record, such as moving a workout, is the first action whose effects outlive the conversation. The pattern:

1.  The model calls the write tool as usual.
2.  The policy gate intercepts the call and suspends the run.
3.  The gate sends the human the exact change, rendered from the tool's arguments rather than from the model's description of them.
4.  Only an explicit approval lets the call through. A time-out counts as a refusal.
5.  The model is told the outcome either way.

12-Factor Agents describes contacting humans through tool calls and pausing and resuming runs for this reason *(12-Factor Agents, HumanLayer)*. OpenAI's guide likewise recommends human intervention for high-risk actions *(A practical guide to building agents, OpenAI)*.

Two design details matter more than they look:

- **Show the arguments, not the narrative.** The model's summary of a change can be wrong, or steered by injected text. The approval message should be generated from the actual tool call.
- **Approval only protects you if it stays rare.** OWASP lists human–agent trust exploitation, where confident explanations lead operators to approve harmful actions, as ASI09 *(OWASP Top 10 for Agentic Applications, OWASP)*. Gate the consequential tools, not every read. When everything needs approval, you stop reading what you approve.

### 4.4 Event-driven runs

Events, such as "a new activity was uploaded" or an n8n workflow calling in, are the third trigger. Architecturally they look like scheduled runs with a payload, and they bring three requirements:

- **Authenticate at the gateway.** A webhook is an inbound port and an unauthenticated trigger. Verify the sender's signature or secret, bind to localhost behind a reverse proxy, and treat the payload as untrusted.
- **Deduplicate and debounce.** Providers retry deliveries, and one upload can produce several events. Key runs on the event id and coalesce bursts.
- **Pass references, not content.** Give the agent the activity id and let it fetch through the policy-gated tool. The event payload then never enters the context directly. This is a small instance of context minimisation (Section 7).

"Trigger from anywhere, meet users where they are" is factor 11 of 12-Factor Agents *(12-Factor Agents, HumanLayer)*. In this architecture, every new trigger is just another entry into the same control plane.

## 5 State and memory

"Memory" covers several different things with different owners, lifetimes and risks. Keeping them separate is most of the design.

| Kind                    | Example                                             | Written by                             | Lifetime                     | Main risk                                               |
|-------------------------|-----------------------------------------------------|----------------------------------------|------------------------------|---------------------------------------------------------|
| Working context         | The context window during one run                   | Context assembler, tool results        | One run                      | Bloat ("context rot"); untrusted text                   |
| Conversation transcript | Messages and tool calls of a session                | Agent runtime                          | Hours (expire idle sessions) | Grows without bound; carries old untrusted text forward |
| Long-term memory        | "Away 10–14 Dec", "knee niggle"                     | Model via a tool, from user statements | Until removed                | Memory poisoning (OWASP ASI06)                          |
| Durable profile         | Goals, constraints, preferences                     | The human (a file)                     | Until edited                 | Staleness                                               |
| Operational state       | Reminders, dedupe keys, schedules, run and cost log | Code and tools                         | Until done, then archived    | Duplicate side effects without keys                     |
| System of record        | Workouts, sleep, HRV in Intervals.icu               | Other systems                          | Theirs                       | Stale copies; over-broad write access                   |

### Principles

- **Leave business data where it lives.** Query the system of record every time rather than caching it in the agent. Copies go stale, and a cache becomes a second place where private data sits. coach-agent stores no training data at all.
- **Memory is written only from what the human said.** Long-term memory is persistent context, so anything that gets into it influences every future run. A memory tool that the model fills from tool results lets one malicious activity note become a permanent instruction. OWASP calls this memory and context poisoning (ASI06) *(OWASP Top 10 for Agentic Applications, OWASP)*. coach-agent's `remember_note` is limited to facts the athlete stated, the notes are listed in every prompt, and `/notes` shows them to the athlete for review.
- **Sessions expire.** Old transcripts carry old untrusted content and cost tokens. coach-agent starts fresh after 16 idle hours. For long tasks, compaction and structured note-taking replace raw history *(Effective context engineering, Anthropic)*.
- **Think of a run as a function of state and event.** 12-Factor Agents frames the agent as a stateless reducer over unified state *(12-Factor Agents, HumanLayer)*. In practice that means a run can be replayed or resumed from what's stored, and a crashed run leaves nothing half-held in memory. The current MCP specification moved in the same direction: each request carries its own protocol version and capabilities, so servers infer nothing from earlier requests *(MCP architecture overview, MCP project)*. That suits coach-agent's pattern of a short-lived process per run.

## 6 Context assembly

The context window is the model's whole world for a run. Anthropic describes it as a finite attention budget whose quality degrades as it fills, and recommends the smallest set of high-signal tokens that does the job *(Effective context engineering, Anthropic)*. Architecturally, context assembly is a data flow with a fixed order and a budget:

1.  **Stable instructions:** role, data-handling rules, assessment method, style.
2.  **Durable facts:** the athlete profile and saved notes.
3.  **Tool definitions:** names, descriptions and schemas. These are prompt text too, so write them as carefully.
4.  **The moment:** a timestamp with timezone, so "today" is never guessed.
5.  **The request**, or the job's prompt.
6.  **Retrieved data, just in time.** Fetched through tools during the run, not pre-loaded.

Two choices shape this flow:

- **Pre-fetch or just-in-time.** Pre-fetching (code loads the data, then calls the model) makes runs predictable and keeps untrusted content out of the planning step. Just-in-time retrieval (the model calls tools) is flexible. Anthropic notes that many systems combine the two *(Effective context engineering, Anthropic)*. coach-agent's morning brief is effectively a fixed fetch plan written into the prompt; chat is fully just-in-time.
- **Tool output is context.** A tool that returns 50 KB of JSON spends the budget on noise. Design tools to return compact, decision-ready results. The Intervals Connector does this, quoting values with quality notes rather than raw streams.

For long-horizon work, the same source describes compaction, structured notes kept outside the window, and sub-agents that work in clean contexts and return summaries *(Effective context engineering, Anthropic)*. A daily coach rarely needs them. A research or coding agent always does.

## 7 Trust boundaries and security

![Figure 5](images/fig5.svg)

**Figure 5.** Trust zones and the data classes that cross them. Untrusted content reaches the model only as tool results. Egress is limited to the owner's chat and the model provider.

### 7.1 Zones and crossings

Draw the zones first, then label every arrow that crosses a zone boundary with the data class it carries:

- **Owner zone:** you and your channel. Authenticated by the allow-list.
- **Host zone:** the VM, holding the control plane, runtime, stores and secrets.
- **Model provider:** receives the full context, so both P and U. That makes it a deliberate, contractual egress, not an accidental one.
- **Third-party data:** the source of both private data and untrusted text.

The questions to ask of each crossing: who authenticates it, what data class it carries, and what the receiver can do with it.

### 7.2 The trifecta test

coach-agent has private data and untrusted content. What keeps it safe is the third leg: it has no general way to send data out. Replies go only to the allow-listed owner, and it has no web, email or link-producing tool. Willison's point is that combining tools from different sources can complete the trifecta without anyone noticing, and that the only reliable fix is to avoid the combination *(The lethal trifecta, Willison)*. So the trifecta test belongs in your change process (Section 10), not just your threat model. Adding an innocuous-looking "send email" or "fetch URL" tool is an architectural change.

### 7.3 Controls, strongest first

| Strength                                     | Mechanism                                                          | coach-agent                                                         |
|----------------------------------------------|--------------------------------------------------------------------|---------------------------------------------------------------------|
| **Structural**: the capability doesn't exist | Tool not installed; egress channel not built; network not routable | No web, shell or file tools; long-polling, so no inbound port       |
| **Enforced**: code refuses                   | Allow-lists, argument validation, spend and turn caps, sandboxing  | Tool allow-list; chat allow-list; `max_budget_usd`; systemd sandbox |
| **Gated**: a human decides                   | Approval of specific consequential actions                         | Proposed for calendar writes (Section 4.3)                          |
| **Detected**: a classifier objects           | Injection detectors, output filters                                | None, deliberately                                                  |
| **Instructed**: the prompt asks              | "Treat tool text as data", "propose before writing"                | Yes, as a complement and never alone                                |

Willison argues that guardrail products claiming around 95% detection are inadequate, because in security 95% is a failing grade *(The lethal trifecta, Willison)*. Use detection and instruction to improve behaviour, and rely on the upper rows for guarantees.

### 7.4 Architectural patterns that contain injection

Beurer-Kellner et al. propose six patterns. Their shared principle: once an agent has read untrusted input, that input must not be able to trigger consequential actions *(Design patterns for securing LLM agents, Beurer-Kellner et al.)*. Mapped to this kind of agent:

| Pattern              | Idea                                                                             | Where it fits a personal agent                                                                            |
|----------------------|----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Action-Selector      | The model picks an action but never sees its result                              | Command-style bots ("log soreness 3")                                                                     |
| Plan-Then-Execute    | Tool calls are fixed before untrusted data is read                               | Scheduled jobs: the fetch plan is in the job prompt. Enforcing it in code would make it a true guarantee. |
| LLM Map-Reduce       | Untrusted items are processed separately, with constrained outputs               | Summarising many activities or emails                                                                     |
| Dual LLM             | A quarantined model reads untrusted text and returns symbols to a privileged one | Agents that both read external content and hold write tools                                               |
| Code-Then-Execute    | The model writes a restricted program; data flow is tracked                      | Complex multi-step automations                                                                            |
| Context-Minimisation | Remove content not needed for the next step                                      | Pass ids rather than payloads (Section 4.4); expire sessions                                              |

### 7.5 OWASP agentic risks, mapped to the architecture

| Risk *(OWASP Top 10 for Agentic Applications)* | Architectural control in this design                                                                              |
|------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| ASI01 Agent goal hijack                        | Untrusted text arrives only as tool results; consequential tools are gated; egress is constrained                 |
| ASI02 Tool misuse                              | Allow-list of named tools; write tools gated; destructive tools absent                                            |
| ASI03 Identity & privilege abuse               | Unprivileged service account; per-service credentials kept outside the package; OAuth scope held by the Connector |
| ASI04 Agentic supply chain                     | Pinned SDK and CLI; few MCP servers; review tool lists when servers change                                        |
| ASI05 Unexpected code execution                | Shell, file and code tools disallowed; process sandbox                                                            |
| ASI06 Memory & context poisoning               | Memory only from user statements; visible notes; session expiry                                                   |
| ASI07 Insecure inter-agent communication       | Single agent; any future sub-agent output is treated as untrusted                                                 |
| ASI08 Cascading failures                       | Bounded retries, per-run caps, deterministic reminder path, failure isolation per run                             |
| ASI09 Human–agent trust exploitation           | Approvals rendered from tool arguments, kept rare                                                                 |
| ASI10 Rogue agents                             | No autonomy beyond the allow-list; run and cost log for audit                                                     |

## 8 Control flow and reliability

The control plane turns an unreliable component (a model that sometimes errs, an API that sometimes times out) into a dependable service. The techniques are familiar from distributed systems. What's new is applying them consistently around the model.

| Concern                | Technique                                                                                                   | coach-agent                                                    |
|------------------------|-------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| Concurrency            | Serialise per conversation; parallelise across conversations                                                | One lock per chat                                              |
| Duplicate side effects | Idempotency keys on everything a run creates                                                                | `dedupe_key`, unique in SQLite                                 |
| Transient failure      | Bounded retries with back-off; startup that waits for the network                                           | Job retries (max 2); indefinite Telegram bootstrap retries     |
| Hung calls             | A timeout at every boundary                                                                                 | Telegram connect and read timeouts; SDK turn limit             |
| Runaway runs           | Turn and cost budgets per run; spend limit per account                                                      | `max_turns`, `max_budget_usd`, Console limit                   |
| Tool errors            | Return errors to the model as compact text so it can recover, within a cap *(12-Factor Agents, HumanLayer)* | Tools return `is_error` with a one-line reason                 |
| Fault isolation        | One process per run; a crash affects one reply                                                              | SDK subprocess per request                                     |
| Graceful degradation   | Keep critical paths free of the model                                                                       | Reminders sent by code; final job attempt always reports       |
| Observability          | Structured run log with cost, turns and outcome; transcripts for replay                                     | `runs` table, `/cost`, CLI transcripts, journald               |
| Change safety          | Tests around the deterministic shell; replay of real transcripts against prompt changes                     | Unit tests with a fake SDK stream. Replay evaluation is a gap. |

One more reason to keep the control flow in your own code: you can test it. Everything in this table can be verified with ordinary unit tests and no model calls, which is how coach-agent's suite exercises the full request path with a fake SDK stream. What stays probabilistic is the quality of the model's judgement. That needs evaluation on representative cases *(Building agents with the Claude Agent SDK, Anthropic)*, not just tests.

## 9 Deployment topologies

The same planes can be deployed in several shapes. The choice moves state and trust boundaries around, so make it deliberately.

| Topology                                                         | Fits when                                            | Where state lives                      | Trust implications                                                                                                    |
|------------------------------------------------------------------|------------------------------------------------------|----------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| **Single service** (coach-agent)                                 | One user or one team; a few triggers; you own a host | Local SQLite and files                 | Smallest attack surface. Host compromise exposes everything.                                                          |
| **Workflow engine + agent service** (e.g. n8n calling the agent) | Many integrations; non-developers build flows        | Split between the engine and the agent | The engine becomes part of the control plane, and its credentials are in scope. Authenticate the call into the agent. |
| **Serverless per trigger**                                       | Spiky, event-driven load                             | External database or object store      | No long-lived host, but secrets live in the platform, and cold starts complicate approval waits.                      |
| **Hosted agent platform**                                        | You want the runtime, sandbox and sessions managed   | Provider-managed                       | The provider joins the trusted computing base. Check data residency and retention.                                    |
| **Multi-tenant service**                                         | Many users of one deployment                         | Shared database with tenancy           | Every store, cache and transcript needs tenant isolation. A leak is cross-user.                                       |

**Separate package, instance and state.** Whatever the topology, keep three things apart: the code you distribute; the per-user instance (configuration, secrets, profile, prompt overrides); and the runtime state (sessions, memory, tokens). That separation is what makes an agent redistributable, upgradable without losing customisation, and isolatable per user. coach-agent's `/opt`, `/etc` and `/var/lib` layout is one implementation. One instance per user, with a systemd template unit, is the simplest multi-user design that keeps users' trust boundaries apart.

## 10 Evolving an agent safely

Agents grow one capability at a time, and each addition can quietly change the architecture. Ask these questions of every change:

1.  **Which plane does it touch?** A new trigger, context source, tool, store or delivery channel each has a different risk profile.
2.  **What data classes does it add?** Does it bring private data, untrusted content, or a new way to send data out?
3.  **Does it complete the trifecta?** If the agent now has all three, either remove a leg or contain the flow with a pattern from Section 7.4.
4.  **Judgement or guarantee?** Decide whether the behaviour belongs in the prompt or in code.
5.  **Is it consequential?** If its effects outlive the conversation, it goes through the approval gate.
6.  **What state does it create?** Give it an owner, a lifetime, an idempotency key and a clean-up path.
7.  **How will you know it works?** A unit test for the shell, and evaluation cases for the judgement.

### Worked examples

| Change                                    | Architectural assessment                                                                                                                                                                           |
|-------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Enable Intervals write tools (done)       | Tool plane, consequential. The trifecta is unchanged, but integrity risk rises: injected text could steer a write. Add the approval gate (Figure 4) and render approvals from the arguments.       |
| Add a weather MCP server                  | Tool plane, read-only, low-sensitivity data. Forecast text is untrusted but low-risk. Allow-list its tools. No other change needed.                                                                |
| Let the bot email a summary to your coach | **Adds egress and completes the trifecta.** Restrict recipients in code to a fixed allow-list; send only content you approve; consider generating the email from structured fields, not free text. |
| Trigger on new activity uploads           | New trigger and an inbound port. Authenticate the webhook, deduplicate by event id, pass the activity id rather than the payload (Section 4.4).                                                    |
| Analyse photos or voice notes             | New untrusted input type in the conversation path. Images and audio can carry instructions too. Same containment rules as text.                                                                    |
| Serve other athletes                      | Deployment topology. One instance per athlete (own config, state, bot and credentials) keeps trust boundaries per user, and the package stays generic.                                             |

## 11 Design checklist

| Area          | Check                                                                                                                                                                     |
|---------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Triggers      | Every trigger authenticated before any model call · webhooks deduplicated · proactive runs can say "not now" and "nothing to report"                                      |
| Control plane | Control flow in your code · per-conversation serialisation · timeouts at every boundary · bounded retries · per-run turn and cost caps                                    |
| Context       | Assembled fresh, in a fixed order · timestamped · compact tool outputs · tool descriptions reviewed as prompt text · references passed instead of payloads where possible |
| Tools         | Explicit allow-list · built-ins disallowed unless needed · consequential tools gated by a human, with approvals rendered from arguments · destructive tools absent        |
| State         | System of record queried, not copied · memory only from user statements and visible to the user · sessions expire · idempotency keys on side effects                      |
| Trust         | Zones drawn · every crossing labelled P/U/E · trifecta test passed or contained · guarantees in code, not prompts                                                         |
| Delivery      | Separate from the runtime · egress destinations fixed in code · silence is a valid outcome                                                                                |
| Operations    | Run and cost log · transcripts kept for a defined period · secrets outside the package · least-privilege service account · tests for the shell, evaluations for judgement |
| Distribution  | Package, instance and state separated · no personal data in the package (and a test that proves it) · one instance per user                                               |

## Appendix A: coach-agent component map

| Reference component  | coach-agent module or artefact                             | Notes                                                  |
|----------------------|------------------------------------------------------------|--------------------------------------------------------|
| Conversation channel | `telegram_io.py`                                           | python-telegram-bot, long-polling                      |
| Schedule             | `scheduler.py`, `jobs:` in `config.yaml`                   | APScheduler cron in the athlete's timezone             |
| Ingress gateway      | Chat filter in `telegram_io.py`                            | `/whoami` is the only open command                     |
| Orchestrator         | `Agent.ask()` plus `scheduler._run_job()`                  | Locks, sessions, control signals, retries              |
| Delivery             | `formatting.py`, `send_text()`                             | HTML with plain-text fallback                          |
| Context assembler    | `Agent.system_prompt()`, `prompts/`, `athlete/profile.md`  | Instance files override packaged defaults              |
| Agent runtime        | Claude Agent SDK `query()`                                 | Bundled CLI subprocess per run                         |
| Policy gate          | `allowed_tools`, `disallowed_tools`, `setting_sources: []` | Approval callback is the planned addition              |
| In-process tools     | `tools/reminders.py`, `tools/notes.py`                     | In-process MCP server `coach`                          |
| Remote MCP server    | `mcp_servers.intervals`                                    | OAuth tokens held by the CLI in the state directory    |
| Session store        | CLI transcripts and the `sessions` table                   | 16-hour idle expiry                                    |
| Operational store    | `store.py` (SQLite)                                        | Reminders, notes, runs                                 |
| Host isolation       | `coach-agent.service`                                      | Read-only package and instance; one writable directory |

## Appendix B: Glossary

| Term                       | Meaning in this guide                                                                                                                     |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| Agent                      | A system in which a model directs its own tool use in a loop *(Building effective agents, Anthropic)*                                     |
| Workflow                   | Model calls arranged by code along predefined paths                                                                                       |
| Control plane              | The deterministic code that starts, constrains, records and delivers runs                                                                 |
| Context window             | Everything the model sees in one run                                                                                                      |
| Control signal             | An exact token in model output that code interprets (e.g. `DATA_NOT_READY`)                                                               |
| Egress                     | Any path by which data leaves your control                                                                                                |
| MCP host / client / server | The AI application; its connection object, one per server; the program offering tools and data *(MCP architecture overview, MCP project)* |
| Policy gate                | The checkpoint between a model's tool call and its execution                                                                              |
| System of record           | The authoritative store of business data, owned outside the agent                                                                         |
| Lethal trifecta            | Private data + untrusted content + external communication in one agent *(The lethal trifecta, Willison)*                                  |

## References

1.  Anthropic. *Building effective agents*. 19 December 2024. <https://www.anthropic.com/research/building-effective-agents>
2.  Shihipar, T. (Anthropic). *Building agents with the Claude Agent SDK*. 29 September 2025. <https://claude.com/resources/articles/building-agents-with-the-claude-agent-sdk>
3.  Anthropic. *Effective context engineering for AI agents*. 29 September 2025. <https://anthropic.com/engineering/effective-context-engineering-for-ai-agents>
4.  OpenAI. *A practical guide to building agents* (PDF). April 2025. Summarised by Maginative, *How to build AI agents: a detailed, practical guide from OpenAI*, 17 April 2025. <https://www.maginative.com/article/how-to-build-ai-agents-a-detailed-practical-guide-from-openai/>
5.  Horthy, D. (HumanLayer). *12-Factor Agents: principles for building reliable LLM applications*. 3 April 2025. <https://www.humanlayer.com/blog/12-factor-agents>
6.  Model Context Protocol project. *Architecture overview* (protocol version 2026-07-28). <https://modelcontextprotocol.io/docs/learn>
7.  Willison, S. *The lethal trifecta for AI agents: private data, untrusted content, and external communication*. 16 June 2025. <https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/>
8.  Beurer-Kellner, L., Buesser, B., Creţu, A.-M., Debenedetti, E., Dobos, D., Fabian, D., Fischer, M., Froelicher, D., Grosse, K., Naeff, D., Ozoani, E., Paverd, A., Tramèr, F. and Volhejn, V. *Design patterns for securing LLM agents against prompt injections*. 2025. Reviewed by S. Willison, 13 June 2025. <https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/>
9.  OWASP GenAI Security Project. *OWASP Top 10 for Agentic Applications*. December 2025. <https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agent>

Source dates are as stated on the pages consulted on 2 November 2026. The OpenAI guide was consulted through the Maginative summary listed. The OWASP release date comes from the announcement's URL. Figures, tables of mappings and the five-plane model are the author's synthesis.

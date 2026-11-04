"""Reference architecture for a long-running personal agent (coach-agent as the example).
Regenerate with: python3 build_reference.py  -> reference-architecture.drawio

Requires drawio_builder.py (a layered draw.io builder with orthogonal routing) on PYTHONPATH,
or its directory in DRAWIO_BUILDER. The .drawio file in this directory is the built output, so
you only need this to regenerate it.
"""
import os
import sys

sys.path.insert(0, os.environ.get("DRAWIO_BUILDER", "."))
from drawio_builder import Diagram, _BOX  # noqa: E402

d = Diagram(name="Agent reference architecture", node_w=240, node_h=86, col_pitch=300,
            row_gap=60, corridor_h=170, page=(1100, 2200))
# Semantic palette: who decides what happens in each box
d.node_styles.update({
    "human": _BOX + "fillColor=#1F3864;strokeColor=#0D1B33;fontColor=#FFFFFF;fontStyle=1;",
    "code":  _BOX + "fillColor=#2E75B6;strokeColor=#1F4E79;fontColor=#FFFFFF;",
    "llm":   _BOX + "fillColor=#ED7D31;strokeColor=#A2521A;fontColor=#FFFFFF;fontStyle=1;",
    "store": _BOX + "fillColor=#FFE699;strokeColor=#BF8F00;fontColor=#3D2E00;",
    "ext":   _BOX + "fillColor=#F2F2F2;strokeColor=#7F7F7F;fontColor=#3A3A3A;dashed=1;",
})

d.layer("1  TRIGGERS - why a run starts", [
    [("chat",  "Conversation channel\n(Telegram message)", "human"),
     ("sched", "Schedule\n(cron: brief, scan)", "code"),
     ("event", "Events / webhooks\n(new activity, n8n)", "ext")],
])
d.layer("2  CONTROL PLANE - deterministic code", [
    [("gate",  "Ingress gateway\nauthn, allow-list, normalise", "code"),
     ("orch",  "Orchestrator\nroute, lock, retry, budget", "code"),
     ("deliv", "Delivery\nformat, split, send, stay silent", "code")],
])
d.layer("3  AGENT CORE - where the model decides", [
    [("ctx",   "Context assembler\nprompt, profile, memory, time", "code"),
     ("loop",  "Agent runtime\nmodel \u2194 tool loop", "llm"),
     ("model", "Model API\n(Claude)", "ext")],
])
d.layer("4  TOOL PLANE - capabilities, behind policy", [
    [("policy","Policy & approval gate\nallow-list, human approval", "code"),
     ("own",   "In-process tools\nreminders, notes", "code"),
     ("mcp",   "Remote MCP server\nIntervals.icu Connector", "ext")],
])
d.layer("5  STATE - what persists between runs", [
    [("sess",  "Session store\nconversation transcripts", "store"),
     ("ops",   "Operational store\nreminders, notes, run & cost log", "store"),
     ("sor",   "System of record\nIntervals.icu (training data)", "ext")],
])

d.edge("chat",  "gate",  "mandate", "message")
d.edge("sched", "orch",  "mandate", "job fires")
d.edge("event", "orch",  "ref",     "future trigger")
d.edge("gate",  "orch",  "mandate", "request")
d.edge("orch",  "ctx",   "derive",  "build context")
d.edge("ctx",   "loop",  "derive",  "prompt + tools")
d.edge("loop",  "model", "accent",  "inference")
d.edge("loop",  "policy","accent",  "tool call")
d.edge("policy","own",   "derive",  "permitted")
d.edge("policy","mcp",   "derive",  "permitted")
d.edge("own",   "ops",   "derive",  "read / write")
d.edge("mcp",   "sor",   "derive",  "OAuth API")
d.edge("loop",  "sess",  "ref",     "transcript")
d.edge("orch",  "deliv", "mandate", "result")
d.edge("deliv", "chat",  "mandate", "reply / reminder")

d.legend("<b>LEGEND</b> (author's synthesis, not a standard)<br>"
         "■ Navy - the human and their channel<br>"
         "■ Blue - deterministic code you own<br>"
         "■ Orange - model-driven decisions<br>"
         "■ Yellow - state you own<br>"
         "□ Grey dashed - external service<br>"
         "─ Navy - request / response path<br>"
         "─ Blue - internal data flow<br>"
         "─ Gold - model-initiated call<br>"
         "┄ Grey dotted - optional / future", w=330, h=190)
stats = d.build("reference-architecture.drawio")
print(stats)

"""Hand-routed SVG figures for the architecture guide (A4 portrait, 680 px wide = 170 mm).
Palette matches reference-architecture.drawio. Run: python3 figures.py  -> fig1..fig5.svg"""
from html import escape

NAVY, BLUE, ORANGE, YEL, YELS, GREY, GREYS = "#1F3864", "#2E75B6", "#ED7D31", "#FFE699", "#BF8F00", "#F2F2F2", "#7F7F7F"
INK, MUTED, GOLD, RED, GREEN = "#1d2731", "#5b6670", "#BF8F00", "#C00000", "#2E7D32"
KIND = {  # fill, stroke, text, dashed
    "human": (NAVY, "#0D1B33", "#FFFFFF", False),
    "code": (BLUE, "#1F4E79", "#FFFFFF", False),
    "llm": (ORANGE, "#A2521A", "#FFFFFF", False),
    "store": (YEL, YELS, "#3D2E00", False),
    "ext": (GREY, GREYS, "#3A3A3A", True),
    "white": ("#FFFFFF", "#9aa5ae", INK, False),
}


class Fig:
    def __init__(self, w, h):
        self.w, self.h, self.parts, self.top, self.markers = w, h, [], [], {}

    def marker(self, color, open_=False):
        key = (color, open_)
        if key not in self.markers:
            mid = "a%d" % len(self.markers)
            shape = ('<path d="M0,0 L10,5 L0,10" fill="none" stroke="%s" stroke-width="1.8"/>' % color if open_
                     else '<path d="M0,0 L10,5 L0,10 z" fill="%s"/>' % color)
            self.markers[key] = ('<marker id="%s" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="8" '
                                 'markerHeight="8" orient="auto" markerUnits="userSpaceOnUse">%s</marker>' % (mid, shape), mid)
        return self.markers[key][1]

    def text(self, x, y, s, size=10, color=INK, weight="normal", anchor="middle", italic=False, layer=None):
        st = ' font-style="italic"' if italic else ""
        (layer if layer is not None else self.parts).append(
            '<text x="%.1f" y="%.1f" font-size="%.1f" fill="%s" font-weight="%s" text-anchor="%s"%s>%s</text>'
            % (x, y, size, color, weight, anchor, st, escape(s)))

    def box(self, x, y, w, h, kind, title, sub=None, size=10.5, rx=5):
        fill, stroke, tc, dashed = KIND[kind]
        dash = ' stroke-dasharray="4,3"' if dashed else ""
        self.parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" fill="%s" stroke="%s" '
                          'stroke-width="1.2"%s/>' % (x, y, w, h, rx, fill, stroke, dash))
        lines = [title] + ([sub] if isinstance(sub, str) else (sub or []))
        lh = size * 1.25
        y0 = y + h / 2 - (len(lines) - 1) * lh / 2 + size * 0.35
        for i, ln in enumerate(lines):
            self.text(x + w / 2, y0 + i * lh, ln, size if i == 0 else size - 1.5, tc,
                      "600" if i == 0 else "normal")

    def band(self, x, y, w, h, label, color="#8497B0", fill="none", dash="6,5", size=11):
        self.parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="%s" stroke="%s" '
                          'stroke-width="1" stroke-dasharray="%s"/>' % (x, y, w, h, fill, color, dash))
        tw = len(label) * size * 0.6 + 10
        self.top.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                        % (x + 5, y + 5, tw, size + 7, "#FFFFFF" if fill == "none" else fill))
        self.text(x + 10, y + 16, label, size, NAVY, "700", "start", layer=self.top)

    def path(self, pts, color=NAVY, width=1.6, dash=None, label=None, at=None, lsize=9, open_=False,
             lcolor=None, arrow=True, halo=True):
        d = "M" + " L".join("%.1f,%.1f" % p for p in pts)
        dd = ' stroke-dasharray="%s"' % dash if dash else ""
        if halo:
            self.parts.append('<path d="%s" fill="none" stroke="#FFFFFF" stroke-width="%.1f" stroke-linejoin="round"/>'
                              % (d, width + 4))
        mk = ' marker-end="url(#%s)"' % self.marker(color, open_) if arrow else ""
        self.parts.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.1f"%s%s stroke-linejoin="round"/>'
                          % (d, color, width, dd, mk))
        if label:
            lx, ly = at
            tw = len(label) * lsize * 0.55 + 8
            self.top.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="#FFFFFF"/>'
                            % (lx - tw / 2, ly - lsize * 0.85, tw, lsize * 1.55))
            self.text(lx, ly + lsize * 0.35, label, lsize, lcolor or color, "600", layer=self.top)

    def num(self, x, y, n, color=NAVY):
        self.top.append('<circle cx="%.1f" cy="%.1f" r="7.5" fill="%s"/>' % (x, y, color))
        self.text(x, y + 3.4, str(n), 9, "#FFFFFF", "700", layer=self.top)

    def svg(self):
        defs = "".join(m[0] for m in self.markers.values())
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="100%%" '
                'font-family="Inter, DejaVu Sans, sans-serif"><defs>%s</defs>%s%s</svg>'
                % (self.w, self.h, defs, "".join(self.parts), "".join(self.top)))


def legend(f, x, y, items, cols=3, colw=215):
    for i, (kind, label) in enumerate(items):
        cx, cy = x + (i % cols) * colw, y + (i // cols) * 18
        if kind in KIND:
            fill, stroke, _, dashed = KIND[kind]
            f.parts.append('<rect x="%.1f" y="%.1f" width="14" height="10" rx="2" fill="%s" stroke="%s"%s/>'
                           % (cx, cy - 8, fill, stroke, ' stroke-dasharray="3,2"' if dashed else ""))
        else:  # line sample: (color, dash)
            color, dash = kind
            f.parts.append('<path d="M%.1f,%.1f L%.1f,%.1f" stroke="%s" stroke-width="1.8"%s/>'
                           % (cx, cy - 3, cx + 14, cy - 3, color, ' stroke-dasharray="%s"' % dash if dash else ""))
        f.text(cx + 20, cy, label, 9.5, INK, anchor="start")


# --------------------------------------------------------------------------- Fig 1
def fig1():
    f = Fig(680, 690)
    B = [16, 140, 264, 388, 512]
    names = ["1  Triggers: why a run starts", "2  Control plane: deterministic code",
             "3  Agent core: where the model decides", "4  Tool plane: capabilities behind policy",
             "5  State: what persists between runs"]
    for y, n in zip(B, names):
        f.band(12, y, 656, 100, n)
    C = [30, 255, 480]; W = 170; H = 58
    def bx(c, l, kind, t, s): f.box(C[c], B[l] + 30, W, H, kind, t, s)
    bx(0, 0, "human", "Conversation channel", "Telegram message")
    bx(1, 0, "code", "Schedule", "cron: brief, scan")
    bx(2, 0, "ext", "Events / webhooks", "new activity, n8n (future)")
    bx(0, 1, "code", "Ingress gateway", "authenticate, allow-list")
    bx(1, 1, "code", "Orchestrator", "route, lock, retry, budget")
    bx(2, 1, "code", "Delivery", "format, split, send / stay silent")
    bx(0, 2, "code", "Context assembler", "prompt, profile, memory, time")
    bx(1, 2, "llm", "Agent runtime", "model ↔ tool loop")
    bx(2, 2, "ext", "Model API", "Claude")
    bx(0, 3, "code", "In-process tools", "reminders, notes")
    bx(1, 3, "code", "Policy & approval gate", "allow-list, human approval")
    bx(2, 3, "ext", "Remote MCP server", "Intervals.icu Connector")
    bx(0, 4, "store", "Operational store", "reminders, notes, run & cost log")
    bx(1, 4, "store", "Session store", "conversation transcripts")
    bx(2, 4, "ext", "System of record", "Intervals.icu training data")
    top = lambda l: B[l] + 30; bot = lambda l: B[l] + 88; mid = lambda l: B[l] + 59
    f.path([(100, bot(0)), (100, top(1))], label="message", at=(100, 128))
    f.path([(340, bot(0)), (340, top(1))], label="job fires", at=(340, 128))
    f.path([(560, bot(0)), (560, 128), (400, 128), (400, top(1))], GREYS, 1.2, "3,3", "future", (480, 128))
    f.path([(200, mid(1)), (255, mid(1))], label="request", at=(227, mid(1) - 11), lsize=8)
    f.path([(425, mid(1)), (480, mid(1))], label="result", at=(452, mid(1) - 11), lsize=8)
    f.path([(650, mid(1)), (672, mid(1)), (672, 6), (130, 6), (130, top(0))], label="reply / reminder", at=(400, 6))
    f.path([(320, bot(1)), (320, 252), (115, 252), (115, top(2))], BLUE, label="build context", at=(217, 252))
    f.path([(200, mid(2)), (255, mid(2))], BLUE, label="context", at=(227, mid(2) - 11), lsize=8)
    f.path([(425, mid(2)), (480, mid(2))], GOLD, label="inference", at=(452, mid(2) - 11), lsize=8)
    f.path([(340, bot(2)), (340, top(3))], GOLD, label="tool call", at=(340, 376))
    f.path([(255, mid(3)), (200, mid(3))], BLUE, label="allowed", at=(227, mid(3) - 11), lsize=8)
    f.path([(425, mid(3)), (480, mid(3))], BLUE, label="allowed", at=(452, mid(3) - 11), lsize=8)
    f.path([(115, bot(3)), (115, top(4))], BLUE, label="read / write", at=(115, 500))
    f.path([(565, bot(3)), (565, top(4))], BLUE, label="OAuth API", at=(565, 500))
    f.path([(405, bot(2)), (405, 372), (452, 372), (452, 500), (405, 500), (405, top(4))], GREYS, 1.2, "3,3",
           "transcript", (430, 372), lsize=8, lcolor=MUTED)
    legend(f, 20, 636, [("human", "Human and their channel"), ("code", "Deterministic code you own"),
                        ("llm", "Model-driven decisions"), ("store", "State you own"),
                        ("ext", "External service"), ((NAVY, None), "Request / response path"),
                        ((BLUE, None), "Internal data flow"), ((GOLD, None), "Model-initiated call"),
                        ((GREYS, "3,3"), "Optional / background")])
    return f.svg()


# --------------------------------------------------------------------------- Fig 2
def fig2():
    lanes = [("You", "human"), ("Gateway", "code"), ("Orchestrator", "code"), ("Context", "code"),
             ("Runtime", "llm"), ("Model", "ext"), ("Policy", "code"), ("MCP tool", "ext"), ("Stores", "store")]
    f = Fig(680, 560)
    xs = [40 + i * 75 for i in range(len(lanes))]
    for x, (n, k) in zip(xs, lanes):
        f.box(x - 34, 10, 68, 30, k, n, size=9.5)
        f.parts.append('<path d="M%.1f,40 L%.1f,548" stroke="#c3cad1" stroke-width="1" stroke-dasharray="3,3"/>' % (x, x))
    X = dict(zip([n for n, _ in lanes], xs))
    # loop frame
    f.parts.append('<rect x="%.1f" y="268" width="%.1f" height="170" rx="4" fill="#fff8f2" stroke="%s" '
                   'stroke-dasharray="5,3"/>' % (X["Runtime"] - 28, X["MCP tool"] - X["Runtime"] + 56, ORANGE))
    f.text(X["Runtime"] - 22, 282, "loop until the model stops calling tools", 8.5, "#A2521A", "600", "start")
    msgs = [  # (from, to, y, label, color, dashed)
        ("You", "Gateway", 66, "message", NAVY, False),
        ("Gateway", "Orchestrator", 96, "request (chat id, text)", NAVY, False),
        ("Orchestrator", "Stores", 126, "lock chat; look up session", BLUE, False),
        ("Orchestrator", "Context", 156, "assemble context", BLUE, False),
        ("Context", "Stores", 186, "profile, notes", BLUE, True),
        ("Context", "Runtime", 216, "system prompt + tools + timestamped message", BLUE, False),
        ("Runtime", "Model", 246, "inference", GOLD, False),
        ("Model", "Runtime", 300, "tool_use: get_wellness", GOLD, True),
        ("Runtime", "Policy", 330, "tool on allow-list?", GOLD, False),
        ("Policy", "MCP tool", 360, "tools/call", BLUE, False),
        ("MCP tool", "Runtime", 390, "result (untrusted text)", RED, True),
        ("Runtime", "Model", 420, "next turn with result", GOLD, False),
        ("Runtime", "Orchestrator", 464, "final answer, session id, cost", ORANGE, True),
        ("Orchestrator", "Stores", 494, "save session id; log run", BLUE, False),
        ("Orchestrator", "You", 530, "deliver reply (via Delivery)", NAVY, False),
    ]
    for i, (a, b, y, lab, col, dsh) in enumerate(msgs, 1):
        xa, xb = X[a], X[b]
        sgn = 1 if xb > xa else -1
        f.path([(xa + sgn * 2, y), (xb - sgn * 3, y)], col, 1.4, "4,3" if dsh else None, halo=False)
        if sgn > 0:
            f.text(xa + 6, y - 5, lab, 8.5, col, "500", "start")
            f.num(xa - 10, y, i, col)
        else:
            f.text(xa - 6, y - 5, lab, 8.5, col, "500", "end")
            f.num(xa + 10, y, i, col)
    return f.svg()


# --------------------------------------------------------------------------- Fig 3
def fig3():
    f = Fig(680, 400)
    f.band(12, 10, 430, 380, "Scheduled job (model in the loop)")
    f.band(456, 10, 212, 380, "Reminder dispatch (no model)")
    f.box(140, 40, 175, 40, "code", "Cron fires", "06:40 morning_briefing")
    f.box(140, 104, 175, 44, "code", "Render job prompt", "date, attempt note")
    f.box(140, 172, 175, 44, "llm", "Agent run", "fresh session, read tools")
    # decision diamond
    cx, cy = 227, 268
    f.parts.append('<path d="M%d,%d L%d,%d L%d,%d L%d,%d z" fill="#FFFFFF" stroke="%s" stroke-width="1.3"/>'
                   % (cx, cy - 26, cx + 72, cy, cx, cy + 26, cx - 72, cy, BLUE))
    f.text(cx, cy - 2, "Control signal", 9.5, NAVY, "600"); f.text(cx, cy + 10, "in reply?", 9, NAVY)
    f.box(22, 322, 120, 52, "white", "DATA_NOT_READY", ["retry in 45 min", "(max 2)"], size=9.5)
    f.box(160, 322, 130, 52, "white", "NOTHING_TO_REPORT", ["stay silent"], size=9.5)
    f.box(308, 322, 122, 52, "code", "Normal reply", ["make it the chat's", "session; deliver"], size=9.5)
    f.path([(227, 80), (227, 104)], BLUE); f.path([(227, 148), (227, 172)], BLUE)
    f.path([(227, 216), (227, cy - 26)], ORANGE)
    f.path([(cx - 72, cy), (82, cy), (82, 322)], BLUE)
    f.path([(cx, cy + 26), (cx, 322)], BLUE)
    f.path([(cx + 72, cy), (369, cy), (369, 322)], BLUE)
    f.path([(22, 348), (16, 348), (16, 126), (140, 126)], GREYS, 1.2, "3,3", "re-run, attempt n+1", (60, 236), lcolor=MUTED)
    # right lane
    f.box(476, 40, 172, 40, "code", "Every 60 s", "interval timer")
    f.box(476, 112, 172, 44, "store", "Due reminders?", "operational store")
    f.box(476, 188, 172, 44, "code", "Send via Delivery", "then mark sent")
    f.path([(562, 80), (562, 112)], BLUE); f.path([(562, 156), (562, 188)], BLUE)
    f.text(562, 262, "Reminders were created earlier by", 9, MUTED, italic=True)
    f.text(562, 275, "the model (add_reminder, with a", 9, MUTED, italic=True)
    f.text(562, 288, "dedupe key) but are sent by plain", 9, MUTED, italic=True)
    f.text(562, 301, "code: no tokens, no API dependency.", 9, MUTED, italic=True)
    return f.svg()


# --------------------------------------------------------------------------- Fig 4
def fig4():
    lanes = [("You", "human"), ("Telegram bot", "code"), ("Policy gate", "code"), ("Runtime", "llm"), ("Intervals", "ext")]
    f = Fig(680, 370)
    xs = [60, 200, 340, 480, 620]
    for x, (n, k) in zip(xs, lanes):
        f.box(x - 50, 10, 100, 30, k, n, size=10)
        f.parts.append('<path d="M%d,40 L%d,362" stroke="#c3cad1" stroke-width="1" stroke-dasharray="3,3"/>' % (x, x))
    X = dict(zip([n for n, _ in lanes], xs))
    f.parts.append('<rect x="%d" y="96" width="%d" height="170" rx="4" fill="#f4f8fc" stroke="%s" stroke-dasharray="5,3"/>'
                   % (X["You"] - 30, X["Policy gate"] - X["You"] + 60, BLUE))
    f.text(X["You"] - 24, 110, "runtime is suspended while it waits", 8.5, BLUE, "600", "start")
    msgs = [
        ("Runtime", "Policy gate", 70, "tool call: update_planned_workout(...)", GOLD, False),
        ("Policy gate", "Telegram bot", 134, "approval request: exact change", BLUE, False),
        ("Telegram bot", "You", 164, "message with Approve / Reject", NAVY, False),
        ("You", "Telegram bot", 204, "taps Approve (or times out)", NAVY, True),
        ("Telegram bot", "Policy gate", 236, "decision", BLUE, True),
        ("Policy gate", "Intervals", 296, "execute (only if approved)", BLUE, False),
        ("Intervals", "Runtime", 326, "result, or ‘denied by user’", BLUE, True),
    ]
    for i, (a, b, y, lab, col, dsh) in enumerate(msgs, 1):
        xa, xb = X[a], X[b]; sgn = 1 if xb > xa else -1
        f.path([(xa + sgn * 2, y), (xb - sgn * 3, y)], col, 1.4, "4,3" if dsh else None, halo=False)
        if sgn > 0:
            f.text(xa + 8, y - 5, lab, 9, col, "500", "start"); f.num(xa - 12, y, i, col)
        else:
            f.text(xa - 8, y - 5, lab, 9, col, "500", "end"); f.num(xa + 12, y, i, col)
    return f.svg()


# --------------------------------------------------------------------------- Fig 5
def fig5():
    f = Fig(680, 470)
    f.band(12, 10, 150, 150, "Owner zone", NAVY, "#f1f4fa")
    f.box(30, 60, 114, 60, "human", "You", "phone, Telegram")
    f.band(190, 10, 300, 330, "Host zone (your VM)", BLUE, "#f1f7fc")
    f.box(210, 48, 120, 52, "code", "Control plane", "gateway, orchestrator")
    f.box(350, 48, 120, 52, "llm", "Agent runtime", "context window")
    f.box(210, 130, 120, 52, "code", "Policy gate", "allow-list, approval")
    f.box(350, 130, 120, 52, "store", "State", "sessions, notes, logs")
    f.box(210, 214, 260, 46, "white", "Secrets", "API key, bot token, OAuth tokens (0640 / 0600)", size=9.5)
    f.text(340, 290, "Process sandbox: read-only code and config,", 8.5, MUTED, italic=True)
    f.text(340, 302, "one writable state directory, no inbound ports", 8.5, MUTED, italic=True)
    f.band(518, 10, 150, 150, "Model provider", GREYS, "#f7f7f7")
    f.box(536, 60, 114, 60, "ext", "Claude API", "sees full context")
    f.band(518, 186, 150, 154, "Third-party data", RED, "#fdf3f3")
    f.box(536, 230, 114, 64, "ext", "Intervals.icu", ["your data +", "untrusted text"])
    # flows
    f.path([(144, 80), (210, 80)], NAVY, label="P", at=(177, 72), lsize=9)
    f.path([(210, 96), (144, 106)], NAVY, label="P", at=(177, 112), lsize=9)
    f.path([(470, 66), (536, 80)], GOLD, label="P+U", at=(503, 62), lsize=9)
    f.path([(536, 100), (470, 92)], GOLD, label="output", at=(503, 106), lsize=8)
    f.path([(300, 182), (300, 198), (504, 198), (504, 246), (536, 246)], BLUE, label="tool calls", at=(400, 198), lsize=8)
    f.path([(536, 280), (482, 280), (482, 116), (440, 116), (440, 100)], RED, 1.6, "4,3", "U (tool results)", (482, 300), lsize=8)
    # trifecta box
    y0 = 362
    f.parts.append('<rect x="12" y="%d" width="656" height="100" rx="4" fill="#fffaf0" stroke="%s"/>' % (y0, YELS))
    f.text(24, y0 + 18, "Lethal-trifecta check for this agent (Willison)", 10.5, NAVY, "700", "start")
    rows = [("Private data", "yes: training, sleep and health-adjacent data (P)"),
            ("Untrusted content", "yes: activity names, notes, shared workout and event text (U)"),
            ("External communication", "constrained: replies go only to the owner's allow-listed chat; no web, email or links tool")]
    for i, (a, b) in enumerate(rows):
        f.text(24, y0 + 40 + i * 18, a, 9.5, INK, "600", "start")
        f.text(170, y0 + 40 + i * 18, b, 9.5, INK, anchor="start")
    f.text(24, y0 + 94, "P = private data \u00b7 U = untrusted content \u00b7 adding any tool that can send data elsewhere completes the trifecta",
           8.5, MUTED, italic=True, anchor="start")
    return f.svg()


if __name__ == "__main__":
    for i, fn in enumerate([fig1, fig2, fig3, fig4, fig5], 1):
        open("fig%d.svg" % i, "w").write(fn())
    print("ok")

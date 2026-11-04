"""Render a layered .drawio file (as produced by drawio_builder) to a static SVG.

Supports what the builder emits: rectangles with fill/stroke/dash/rounding, centred or
top-left HTML labels with <br> and <b>, orthogonal edges with explicit waypoints and
exit/entry anchors, block/open arrowheads, and edge labels positioned along the path.
Usage: python3 drawio2svg.py in.drawio out.svg
"""
import html
import re
import sys
import xml.etree.ElementTree as ET


def style_dict(s):
    out = {}
    for part in (s or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def lines_of(value):
    v = html.unescape(value or "")
    v = re.sub(r"<br\s*/?>", "\n", v)
    lines = []
    for ln in v.split("\n"):
        bold = "<b>" in ln
        lines.append((re.sub(r"<[^>]+>", "", ln), bold))
    return lines


def text_width(s, size):
    return len(s) * size * 0.56


def esc(s):
    return html.escape(s, quote=True)


def point_along(pts, frac):
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lens = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in segs]
    total = sum(lens) or 1
    target = total * frac
    for (a, b), L in zip(segs, lens):
        if target <= L and L > 0:
            t = target / L
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        target -= L
    return pts[-1]


def render(path_in, path_out):
    root = ET.parse(path_in).getroot()
    cells = list(root.iter("mxCell"))
    geo = {}
    for c in cells:
        g = c.find("mxGeometry")
        if c.get("vertex") == "1" and g is not None:
            geo[c.get("id")] = tuple(float(g.get(k, 0)) for k in ("x", "y", "width", "height"))
    W = max(x + w for x, y, w, h in geo.values()) + 20
    H = max(y + h for x, y, w, h in geo.values()) + 20

    defs, body, labels = [], [], []
    markers = {}

    def marker(color, kind):
        key = (color, kind)
        if key not in markers:
            mid = "m%d" % len(markers)
            markers[key] = mid
            if kind == "open":
                shape = '<path d="M0,0 L10,5 L0,10" fill="none" stroke="%s" stroke-width="1.6"/>' % color
            else:
                shape = '<path d="M0,0 L10,5 L0,10 z" fill="%s"/>' % color
            defs.append('<marker id="%s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
                        'markerHeight="7" orient="auto-start-reverse" markerUnits="userSpaceOnUse">%s</marker>'
                        % (mid, shape))
            # scale arrowheads with stroke: userSpaceOnUse keeps them a fixed, legible size
        return markers[key]

    # vertices: bands first (fillColor=none), then boxes
    verts = [c for c in cells if c.get("vertex") == "1"]
    verts.sort(key=lambda c: 0 if style_dict(c.get("style")).get("fillColor") == "none" else 1)
    for c in verts:
        st = style_dict(c.get("style"))
        x, y, w, h = geo[c.get("id")]
        fill = st.get("fillColor", "#FFFFFF")
        fill = "none" if fill == "none" else fill
        stroke = st.get("strokeColor", "#000000")
        dash = ""
        if st.get("dashed") == "1":
            dash = ' stroke-dasharray="%s"' % st.get("dashPattern", "5 4").replace(" ", ",")
        rx = 6 if st.get("rounded", "0") not in ("0", "") else 0
        body.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" fill="%s" stroke="%s" '
                    'stroke-width="1.2"%s/>' % (x, y, w, h, rx, fill, stroke, dash))
        size = float(st.get("fontSize", 11))
        color = st.get("fontColor", "#000000")
        weight_all = "bold" if st.get("fontStyle") == "1" else "normal"
        lns = lines_of(c.get("value"))
        lh = size * 1.3
        if st.get("align") == "left":
            tx = x + float(st.get("spacingLeft", 8))
            ty = y + float(st.get("spacingTop", 8)) + size
            anchor = "start"
        else:
            tx = x + w / 2
            ty = y + h / 2 - (len(lns) - 1) * lh / 2 + size * 0.35
            anchor = "middle"
        for i, (t, b) in enumerate(lns):
            if not t.strip():
                continue
            weight = "bold" if (b or weight_all == "bold") else "normal"
            body.append('<text x="%.1f" y="%.1f" font-size="%.1f" fill="%s" font-weight="%s" '
                        'text-anchor="%s">%s</text>' % (tx, ty + i * lh, size, color, weight, anchor, esc(t)))

    # edges
    for c in cells:
        if c.get("edge") != "1":
            continue
        st = style_dict(c.get("style"))
        sx, sy, sw, sh = geo[c.get("source")]
        tx_, ty_, tw, th = geo[c.get("target")]
        start = (sx + float(st.get("exitX", 0.5)) * sw, sy + float(st.get("exitY", 1)) * sh)
        end = (tx_ + float(st.get("entryX", 0.5)) * tw, ty_ + float(st.get("entryY", 0)) * th)
        g = c.find("mxGeometry")
        way = [(float(p.get("x")), float(p.get("y"))) for p in g.iter("mxPoint") if p.get("as") is None]
        pts = [start] + way + [end]
        # make every segment orthogonal (draw.io inserts the elbows implicitly)
        ortho = [pts[0]]
        for p in pts[1:]:
            q = ortho[-1]
            if q[0] != p[0] and q[1] != p[1]:
                ortho.append((q[0], p[1]) if len(ortho) == 1 else (p[0], q[1]))
            ortho.append(p)
        color = st.get("strokeColor", "#000000")
        sw_ = float(st.get("strokeWidth", 1))
        dash = ""
        if st.get("dashed") == "1":
            dash = ' stroke-dasharray="%s"' % st.get("dashPattern", "5 4").replace(" ", ",")
        kind = "open" if st.get("endArrow") == "open" else "block"
        mid = marker(color, kind)
        d = "M" + " L".join("%.1f,%.1f" % p for p in ortho)
        body.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.1f"%s marker-end="url(#%s)" '
                    'stroke-linejoin="round"/>' % (d, color, sw_, dash, mid))
        label = re.sub(r"<[^>]+>", "", html.unescape(c.get("value") or ""))
        if label:
            frac = (float(g.get("x", 0)) + 1) / 2
            lx, ly = point_along(ortho, frac)
            off = g.find("mxPoint[@as='offset']")
            if off is not None:
                lx += float(off.get("x", 0)); ly += float(off.get("y", 0))
            size = float(st.get("fontSize", 9)) + 0.5
            tw_ = text_width(label, size) + 8
            weight = "bold" if st.get("fontStyle") == "1" else "normal"
            labels.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#FFFFFF" rx="2"/>'
                          '<text x="%.1f" y="%.1f" font-size="%.1f" fill="%s" font-weight="%s" '
                          'text-anchor="middle">%s</text>'
                          % (lx - tw_ / 2, ly - size * 0.8, tw_, size * 1.5, lx, ly + size * 0.35, size,
                             st.get("fontColor", color), weight, esc(label)))

    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
           'font-family="Inter, DejaVu Sans, sans-serif"><defs>%s</defs>%s%s</svg>'
           % (W, H, W, H, "".join(defs), "".join(body), "".join(labels)))
    with open(path_out, "w") as f:
        f.write(svg)
    return W, H


if __name__ == "__main__":
    print(render(sys.argv[1], sys.argv[2]))

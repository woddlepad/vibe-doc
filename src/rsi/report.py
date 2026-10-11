"""Static HTML report of every harness version, its scores and its diff."""

from __future__ import annotations

import html
from pathlib import Path

from .config import ROOT, RUNS
from .optimize import load_registry

CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--acc:#2563eb;--ok:#15803d;--bad:#b91c1c;--code:#f5f5f5}
@media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--muted:#999;--line:#333;--acc:#60a5fa;--ok:#4ade80;--bad:#f87171;--code:#1c1c1c}}
body{font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:960px;margin:2rem auto;padding:0 1rem}
h1{font-weight:500;margin-bottom:.2rem} .muted{color:var(--muted)}
.cards{display:flex;gap:1rem;flex-wrap:wrap;margin:1.5rem 0}.card{border:1px solid var(--line);border-radius:8px;padding:.8rem 1rem;min-width:160px}
.card b{display:block;font-size:1.6rem;font-weight:500}
table{border-collapse:collapse;width:100%;margin:1rem 0}td,th{border-bottom:1px solid var(--line);padding:.4rem .5rem;text-align:left;vertical-align:top}
th{font-weight:500;color:var(--muted)} .ok{color:var(--ok)} .bad{color:var(--bad)}
pre{background:var(--code);padding:.8rem;overflow:auto;font-size:12px;border-radius:6px} details{margin:.4rem 0}
svg text{fill:var(--muted);font-size:11px}
"""


def _pct(x) -> str:
    return "-" if x is None else f"{x:.0%}"


def _chart(versions: list[dict]) -> str:
    pts = [(v["name"], v["dev"]["accuracy"], v["dev"]["ci95"]) for v in versions if "dev" in v]
    if not pts:
        return "<p class='muted'>No dev results yet.</p>"
    w, h, pad = 900, 240, 40
    step = (w - 2 * pad) / max(1, len(pts) - 1)
    y = lambda a: h - pad - a * (h - 2 * pad)  # noqa: E731
    x = lambda i: pad + i * step if len(pts) > 1 else w / 2  # noqa: E731
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Dev accuracy per harness version">']
    for t in (0, 0.25, 0.5, 0.75, 1):
        parts.append(f'<line x1="{pad}" x2="{w - pad}" y1="{y(t)}" y2="{y(t)}" stroke="var(--line)"/><text x="4" y="{y(t) + 4}">{t:.0%}</text>')
    line = " ".join(f"{x(i)},{y(a)}" for i, (_, a, _) in enumerate(pts))
    parts.append(f'<polyline points="{line}" fill="none" stroke="var(--acc)" stroke-width="2"/>')
    for i, (name, a, (lo, hi)) in enumerate(pts):
        parts.append(f'<line x1="{x(i)}" x2="{x(i)}" y1="{y(lo)}" y2="{y(hi)}" stroke="var(--acc)" opacity=".35" stroke-width="6"/>')
        parts.append(f'<circle cx="{x(i)}" cy="{y(a)}" r="4" fill="var(--acc)"/>')
        parts.append(f'<text x="{x(i)}" y="{h - 12}" text-anchor="middle">{name}</text>')
        parts.append(f'<text x="{x(i)}" y="{y(a) - 10}" text-anchor="middle">{a:.0%}</text>')
    return "".join(parts) + "</svg>"


def _diff_block(rel: str | None) -> str:
    if not rel or not (ROOT / rel).exists():
        return ""
    text = (ROOT / rel).read_text()
    return f"<details><summary>diff</summary><pre>{html.escape(text)}</pre></details>"


def build_report(out: Path = RUNS / "report.html") -> Path:
    reg = load_registry()
    versions = reg["versions"]
    base = versions[0].get("dev", {}).get("accuracy")
    best = next(v for v in versions if v["name"] == reg["best"])
    tested = [v for v in versions if "test" in v]
    rows = []
    for v in versions:
        d = v.get("dev", {})
        t = v.get("test", {})
        rows.append(
            f"<tr><td><b>{v['name']}</b><br><span class='muted'>from {v['parent'] or '-'}</span></td>"
            f"<td class='ok'>accepted</td><td>{_pct(d.get('accuracy'))}"
            f"<br><span class='muted'>{d.get('correct', '-')}/{d.get('scored', '-')}</span></td>"
            f"<td>{_pct(t.get('accuracy'))}</td><td>{html.escape(v.get('hypothesis', ''))}{_diff_block(v.get('diff'))}</td></tr>"
        )
    for r in reg["rejected"]:
        rows.append(
            f"<tr><td>{html.escape(r['id'])}<br><span class='muted'>from {r['parent']}</span></td>"
            f"<td class='bad'>rejected</td><td>{_pct(r.get('dev_accuracy'))}"
            f"<br><span class='muted'>parent {_pct(r.get('parent_dev_accuracy'))}, P={r.get('confidence', '-')}</span></td><td>-</td>"
            f"<td>{html.escape(r.get('hypothesis', ''))}<br><span class='muted'>{html.escape(r['reason'])}</span>{_diff_block(r.get('diff'))}</td></tr>"
        )
    body = f"""<h1>Self-improving diagnosis harness</h1>
<p class="muted">Doctor model {reg['locked_model']}. Dev accuracy decides promotion; test is scored once at the end.</p>
<div class="cards">
 <div class="card"><span class="muted">Baseline dev</span><b>{_pct(base)}</b>v000</div>
 <div class="card"><span class="muted">Best dev</span><b>{_pct(best.get('dev', {}).get('accuracy'))}</b>{best['name']}</div>
 <div class="card"><span class="muted">Attempts</span><b>{len(versions) - 1 + len(reg['rejected'])}</b>{len(versions) - 1} promoted</div>
 {''.join(f'<div class="card"><span class="muted">Test ({v["name"]})</span><b>{_pct(v["test"]["accuracy"])}</b>n={v["test"]["scored"]}</div>' for v in tested)}
</div>
<h2>Dev accuracy by version</h2>{_chart(versions)}
<h2>Every attempt</h2>
<table><tr><th>Version</th><th>Outcome</th><th>Dev</th><th>Test</th><th>Hypothesis</th></tr>{''.join(rows)}</table>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"<!doctype html><meta charset='utf-8'><title>rsi-doc report</title><style>{CSS}</style>{body}")
    return out

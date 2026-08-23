#!/usr/bin/env python3
"""Render an EV-IMP-001 Essentials model as a standalone static HTML page."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from adapter import build_essentials, load_payload


def e(value: object) -> str:
    return html.escape("" if value is None else str(value))


def render_model(model: dict) -> str:
    embedded = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    parts = [f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empowered.Vote Essentials - Tacoma</title>
<style>
:root {{ color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ margin:0; background:#f5f7f8; color:#172026; }}
main {{ max-width:1100px; margin:auto; padding:32px 20px 64px; }}
.hero {{ background:white; border:1px solid #d9e0e4; border-radius:18px; padding:24px; box-shadow:0 8px 30px #0000000a; }}
h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,44px); }}
.sub {{ color:#51606a; margin:0 0 20px; }}
.badge {{ display:inline-block; border:1px solid #b8c6ce; border-radius:999px; padding:4px 9px; font-size:12px; margin-right:6px; background:#f8fafb; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:14px; margin-top:18px; }}
.card {{ background:white; border:1px solid #d9e0e4; border-radius:14px; padding:16px; }}
.card h3 {{ margin:0 0 6px; font-size:17px; }}
.meta {{ color:#5c6870; font-size:13px; line-height:1.5; }}
.source {{ margin-top:10px; border-top:1px solid #e4e9ec; padding-top:10px; font-size:12px; color:#56636b; }}
a {{ color:#125f8c; }}
section {{ margin-top:28px; }}
section h2 {{ margin-bottom:10px; }}
.candidate {{ display:flex; justify-content:space-between; gap:10px; padding:7px 0; border-top:1px solid #edf0f2; }}
.winner {{ font-weight:700; }}
.notice {{ padding:12px 14px; border-left:4px solid #6f7f88; background:#eef2f4; border-radius:8px; margin-top:16px; }}
code {{ font-size:12px; overflow-wrap:anywhere; }}
@media (prefers-color-scheme: dark) {{ body {{ background:#11181c; color:#e9f0f4; }} .hero,.card {{ background:#172126; border-color:#314048; }} .sub,.meta,.source {{ color:#b5c0c6; }} .badge {{ background:#202c32; border-color:#45545c; }} .notice {{ background:#202b31; }} a {{ color:#74c6f3; }} }}
</style>
</head>
<body><main>
<div class="hero">
  <span class="badge">EV-IMP-001</span><span class="badge">read-only</span><span class="badge">frozen Tacoma fixture</span>
  <h1>Who governs this address?</h1>
  <p class="sub">{e(model.get('input_address'))}</p>
  <div><strong>Status:</strong> {e(model.get('status'))} · <strong>Snapshot:</strong> {e(model.get('source_snapshot'))}</div>
  <div class="notice">{e(model.get('representation_scope_note'))}</div>
</div>
<section><h2>Resolved geography</h2><div class="grid">''']
    for jid in model.get("resolved_jurisdictions", []):
        parts.append(f'<div class="card"><h3>{e(jid)}</h3><div class="meta">Canonical resolved jurisdiction ID</div></div>')
    parts.append('</div></section><section><h2>Current Tacoma representation</h2><div class="grid">')
    for row in model.get("applicable_offices", []):
        holder = row.get("holder") or {}
        prov = row.get("provenance") or {}
        term = "Term not established"
        if holder.get("term_start") or holder.get("term_end"):
            term = f"{holder.get('term_start') or 'unknown'} → {holder.get('term_end') or 'open/unknown'}"
        source_html = "No source in frozen payload"
        if prov.get("url"):
            source_html = f'<a href="{e(prov.get("url"))}" target="_blank" rel="noreferrer">{e(prov.get("title") or prov.get("source_id"))}</a>'
        parts.append(f'''<div class="card">
          <h3>{e(row.get('office_name'))}</h3>
          <div>{e(holder.get('name') or 'Holder not established')}</div>
          <div class="meta">{e(row.get('seat_type'))}<br>{e(holder.get('currentness_status'))}<br>{e(term)}</div>
          <div class="source">Source: {source_html}<br><code>{e(row.get('office_id'))}</code></div>
        </div>''')
    parts.append('</div></section><section><h2>Most recent certified contests in this fixture</h2>')
    for contest in model.get("recent_certified_contests", []):
        prov = contest.get("provenance") or {}
        parts.append(f'<div class="card" style="margin-bottom:12px"><h3>{e(contest.get("contest_name"))}</h3><div class="meta">{e(contest.get("election_id"))}</div>')
        for cand in contest.get("candidates", []):
            cls = "winner" if cand.get("outcome") == "WINNER" else ""
            person = f' · <code>{e(cand.get("person_id"))}</code>' if cand.get("person_id") else ""
            parts.append(f'<div class="candidate"><span class="{cls}">{e(cand.get("ballot_name"))}{person}</span><span>{e(cand.get("outcome"))} · {e(cand.get("votes"))} votes</span></div>')
        if prov.get("url"):
            parts.append(f'<div class="source">Certified result: <a href="{e(prov.get("url"))}" target="_blank" rel="noreferrer">{e(prov.get("title"))}</a></div>')
        parts.append('</div>')
    parts.append(f'''</section>
<section><h2>Integrity</h2><div class="card"><div class="meta">
Canonical writes: {e(model.get('canonical_writes'))}<br>
Deterministic payload hash: <code>{e(model.get('deterministic_sha256'))}</code><br>
Unsupported facts are not synthesized by this consumer.
</div></div></section>
<script type="application/json" id="ev-essentials-model">{embedded}</script>
</main></body></html>''')
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture")
    ap.add_argument("--address", default="747 Market Street, Tacoma, WA 98402")
    ap.add_argument("--json-out")
    ap.add_argument("--html-out")
    args = ap.parse_args()
    payload = load_payload(args.fixture)
    model = build_essentials(payload, args.address)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(model, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.html_out:
        Path(args.html_out).write_text(render_model(model), encoding="utf-8")
    print(json.dumps({"status": model.get("status"), "sha256": model.get("deterministic_sha256"), "offices": len(model.get("applicable_offices", [])), "contests": len(model.get("recent_certified_contests", []))}, sort_keys=True))
    return 0 if model.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

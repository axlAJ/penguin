"""Report output: an HTML QC report for humans, CSV for the exception log.

No template engine. A QC tool that a case team installs under deadline
should have nothing to install.
"""

from __future__ import annotations

import csv
import html
from collections import Counter
from datetime import datetime
from pathlib import Path

from .checks import BLOCKER, Finding, ProductionSummary
from .searchterms import TermHit

RULE_DESCRIPTIONS = {
    "required-field": "Load file is missing a column the protocol requires.",
    "bates-missing": "A record carries no beginning Bates number.",
    "bates-malformed": "A Bates value does not end in a numeric sequence.",
    "bates-duplicate": "The same Bates number is used by more than one record.",
    "bates-gap": "The Bates range skips one or more numbers.",
    "bates-range": "A document's ending Bates is inconsistent with its beginning.",
    "family-orphan": "An attachment points at a parent not in this production.",
    "family-order": "A child document sorts before its parent.",
    "family-range": "A family range does not enclose its own document.",
    "native-missing": "A native file named in the load file is not in the volume.",
    "text-missing": "An extracted text file named in the load file is not in the volume.",
    "text-empty": "An extracted text file is present but empty.",
    "image-orphan": "The image load file references a document not in the DAT.",
    "image-missing": "A document states a page count but has no images.",
    "page-count": "Stated page count does not match the image load file.",
    "date-format": "A date value did not parse in any expected format.",
    "control-character": "A field contains an unescaped control character.",
    "endorsement-missing": "A designated document carries no endorsement text.",
}


def write_csv(findings: list[Finding], path: str | Path) -> Path:
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["severity", "rule", "record", "detail"])
        for finding in findings:
            writer.writerow([finding.severity, finding.rule, finding.record, finding.detail])
    return path


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _verdict(findings: list[Finding]) -> tuple[str, int, str, str]:
    blockers = sum(1 for f in findings if f.is_blocker)
    warnings = len(findings) - blockers
    if blockers:
        return (
            "hold",
            blockers,
            f"blocking {'defect' if blockers == 1 else 'defects'}",
            "This volume should not ship until each blocking defect is resolved or waived in writing.",
        )
    if warnings:
        return (
            "review",
            warnings,
            f"{'item' if warnings == 1 else 'items'} to review",
            "Nothing blocks delivery. Each item below still needs a documented decision.",
        )
    return (
        "clear",
        0,
        "defects found",
        "Every check passed against the load files and the volume on disk.",
    )


def _rule_rows(findings: list[Finding]) -> str:
    counts = Counter((f.rule, f.severity) for f in findings)
    if not counts:
        return ""
    rows = []
    for (rule, severity), count in sorted(counts.items(), key=lambda item: (-item[1], item[0][0])):
        rows.append(
            f"<tr><td><span class='sev {_esc(severity)}'>{_esc(rule)}</span></td>"
            f"<td class='num'>{count}</td>"
            f"<td class='desc'>{_esc(RULE_DESCRIPTIONS.get(rule, ''))}</td></tr>"
        )
    return (
        "<table class='rules'><thead><tr><th>Rule</th><th class='num'>Count</th>"
        "<th>What it means</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _finding_rows(findings: list[Finding], limit: int) -> str:
    if not findings:
        return "<p class='empty'>No exceptions to list.</p>"
    order = {BLOCKER: 0}
    shown = sorted(findings, key=lambda f: (order.get(f.severity, 1), f.rule, f.record))[:limit]
    rows = "".join(
        f"<tr data-sev='{_esc(f.severity)}' data-rule='{_esc(f.rule)}' tabindex='0'>"
        f"<td><span class='sev {_esc(f.severity)}'>{_esc(f.severity)}</span></td>"
        f"<td class='mono'>{_esc(f.rule)}</td>"
        f"<td class='mono'>{_esc(f.record)}</td>"
        f"<td>{_esc(f.detail)}</td></tr>"
        for f in shown
    )
    rule_options = "".join(
        f"<option value='{_esc(rule)}'>{_esc(rule)}</option>"
        for rule in sorted({f.rule for f in findings})
    )
    toolbar = (
        "<div class='toolbar'>"
        "<div class='seg' role='group' aria-label='Severity'>"
        "<button type='button' data-filter='all' class='on'>All</button>"
        "<button type='button' data-filter='blocker'>Blockers</button>"
        "<button type='button' data-filter='warning'>Warnings</button>"
        "</div>"
        f"<select id='rule-filter' aria-label='Rule'><option value=''>Every rule</option>{rule_options}</select>"
        "<input id='log-search' type='search' placeholder='Search record or detail' aria-label='Search exceptions'>"
        "<button type='button' id='dl-csv' class='ghost'>Download CSV</button>"
        "<span id='log-count' class='count'></span>"
        "</div>"
    )
    more = ""
    if len(findings) > limit:
        more = (
            f"<p class='empty'>Showing {limit} of {len(findings)}. "
            f"The CSV export carries the full log.</p>"
        )
    return (
        toolbar
        + "<table id='log'><thead><tr><th>Severity</th><th>Rule</th><th>Record</th>"
        "<th>Detail</th></tr></thead><tbody>" + rows + "</tbody></table>"
        + "<div id='detail' class='detail' hidden></div>" + more
    )


def _term_rows(hits: list[TermHit]) -> str:
    if not hits:
        return ""
    rows = "".join(
        f"<tr><td class='mono'>{_esc(hit.term)}</td>"
        f"<td class='num'>{hit.documents}</td>"
        f"<td class='num'>{hit.unique}</td>"
        f"<td class='num'>{hit.pct_of_corpus}%</td>"
        f"<td><div class='bar'><i style='width:{min(hit.pct_of_corpus,100)}%'></i></div></td>"
        f"<td class='desc'>{_esc(hit.note)}</td></tr>"
        for hit in hits
    )
    return (
        "<section><h2>Search terms</h2>"
        "<p class='lede'>Unique hits are documents no other term on the list reaches. "
        "A term with none is a term you can give up in negotiation.</p>"
        "<table><thead><tr><th>Term</th><th class='num'>Docs</th>"
        "<th class='num'>Unique</th><th class='num'>Corpus</th><th></th>"
        "<th>Note</th></tr></thead><tbody>" + rows + "</tbody></table></section>"
    )


PENGUIN_MARK = """<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" role="img">
<ellipse cx="32" cy="38" rx="20" ry="24" fill="currentColor"/>
<ellipse cx="32" cy="42" rx="12" ry="17" fill="var(--tux)"/>
<circle cx="32" cy="18" r="13" fill="currentColor"/>
<ellipse cx="32" cy="21" rx="7.5" ry="6" fill="var(--tux)"/>
<circle cx="27.5" cy="16" r="2.2" fill="var(--tux)"/>
<circle cx="36.5" cy="16" r="2.2" fill="var(--tux)"/>
<path d="M29 22.5 L35 22.5 L32 27 Z" fill="var(--ice)"/>
<path d="M13 30 Q4 42 12 54 Q16 46 16 36 Z" fill="currentColor"/>
<path d="M51 30 Q60 42 52 54 Q48 46 48 36 Z" fill="currentColor"/>
<path d="M22 60 L30 60 L28 64 L20 64 Z" fill="var(--ice)"/>
<path d="M34 60 L42 60 L44 64 L36 64 Z" fill="var(--ice)"/>
</svg>"""

STYLE = """
:root{
  box-sizing:border-box;
  padding-top:env(safe-area-inset-top,0px);
  padding-bottom:env(safe-area-inset-bottom,0px);
  --paper:#f6f7f8; --ink:#0b0c0d; --tux:#0b0c0d; --tux-ink:#f6f7f8;
  --muted:#6b7379; --hair:#d5d9dc; --ice:#2fb4d6; --ice-deep:#1585a3;
  --blocker:#d1172f; --warning:#e08a00; --clear:#1a9e73;
  --display:"Bricolage Grotesque","Archivo","Helvetica Neue",Arial,sans-serif;
  --body:"Instrument Sans","Helvetica Neue",Arial,sans-serif;
  --mono:"Martian Mono","JetBrains Mono",ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#0b0c0d; --ink:#f0f2f3; --tux:#f0f2f3; --tux-ink:#0b0c0d;
    --muted:#8f979c; --hair:#25292c; --ice:#4fc6e6; --ice-deep:#7dd7ee;
    --blocker:#ff5a6e; --warning:#ffb340; --clear:#3fd19f;
  }
}
:root[data-theme="dark"]{
  --paper:#0b0c0d; --ink:#f0f2f3; --tux:#f0f2f3; --tux-ink:#0b0c0d;
  --muted:#8f979c; --hair:#25292c; --ice:#4fc6e6; --ice-deep:#7dd7ee;
  --blocker:#ff5a6e; --warning:#ffb340; --clear:#3fd19f;
}
*,*::before,*::after{box-sizing:inherit}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--body); font-size:15.5px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
a{color:inherit}
.band{background:var(--tux); color:var(--tux-ink)}
.band .wrap{padding:2rem 1.5rem 2.25rem; display:flex; align-items:flex-end; gap:1.25rem; flex-wrap:wrap}
.mark{width:52px; height:52px; flex:0 0 auto}
.mark svg{width:100%; height:100%; display:block}
.band h1{
  font-family:var(--display); font-weight:800; font-size:2.8rem; font-size:clamp(2rem,5vw,3.2rem);
  letter-spacing:-0.035em; line-height:.95; margin:0;
}
.band h1 span{color:var(--ice)}
.band .meta{margin:.35rem 0 0; color:var(--tux-ink); opacity:.65; font-size:.9rem}
.wrap{max-width:66rem; margin:0 auto; padding:0 1.5rem}
main.wrap{padding-top:0; padding-bottom:4rem}
.verdict{
  margin:-1.25rem 0 2.5rem; background:var(--paper);
  border:3px solid var(--ink); display:flex; align-items:center;
  padding:1rem 1.5rem;
}
.verdict .n{
  font-family:var(--display); font-weight:800; font-size:5rem; font-size:clamp(3.5rem,9vw,5.5rem);
  line-height:.9; letter-spacing:-0.05em; color:var(--blocker);
  font-variant-numeric:tabular-nums; margin-right:1.5rem; flex:0 0 auto;
}
.verdict .t{flex:1 1 auto}
.verdict.review .n{color:var(--warning)}
.verdict.clear .n{color:var(--clear)}
.verdict h2{
  font-family:var(--display); font-weight:700; font-size:1.35rem; margin:0;
  letter-spacing:-0.02em;
}
.verdict p{margin:.25rem 0 0; color:var(--muted); max-width:52ch; font-size:.95rem}
section{margin-bottom:2.75rem}
h2{
  font-family:var(--display); font-weight:700; font-size:1.25rem; letter-spacing:-0.02em;
  margin:0 0 .75rem; padding-top:.75rem; border-top:3px solid var(--ink);
}
.lede{color:var(--muted); margin:-.25rem 0 1rem; max-width:64ch}
.facts{display:flex; flex-wrap:wrap; margin:0; border-top:1px solid var(--hair); border-left:1px solid var(--hair)}
.fact{flex:1 1 9.5rem; background:var(--paper); padding:.85rem 1rem; border-right:1px solid var(--hair); border-bottom:1px solid var(--hair)}
.fact dt{color:var(--muted); font-size:.78rem; margin:0 0 .2rem}
.fact dd{margin:0; font-family:var(--display); font-weight:700; font-size:1.55rem; letter-spacing:-0.03em; line-height:1.05; font-variant-numeric:tabular-nums}
.fact dd.small{font-family:var(--mono); font-weight:400; font-size:.8rem; letter-spacing:0; line-height:1.4; padding-top:.3rem}
.scroll{overflow-x:auto}
table{width:100%; border-collapse:collapse; font-size:.92rem}
th,td{text-align:left; padding:.6rem .75rem .6rem 0; border-bottom:1px solid var(--hair); vertical-align:top}
th{font-weight:600; font-size:.78rem; color:var(--muted); border-bottom:2px solid var(--ink); padding-bottom:.45rem}
td.num,th.num{text-align:right; font-variant-numeric:tabular-nums; font-family:var(--display); font-weight:600}
th.num{font-family:var(--body); font-weight:600}
.mono{font-family:var(--mono); font-size:.78em; letter-spacing:-0.01em}
.desc{color:var(--muted)}
.sev{display:inline-block; font-weight:600; font-size:.85rem; white-space:nowrap}
.sev::before{content:""; display:inline-block; width:.5rem; height:.5rem; margin:0 .55rem 1px .1rem; border-radius:1px; background:var(--muted); transform:rotate(45deg)}
.sev.blocker::before{background:var(--blocker)}
.sev.warning::before{background:var(--warning)}
.bar{height:.4rem; background:var(--hair); border-radius:1px; overflow:hidden; min-width:6rem}
.bar i{display:block; height:100%; background:var(--ice)}
.empty{color:var(--muted); font-size:.9rem; margin:.7rem 0 0}
.toolbar{display:flex; flex-wrap:wrap; gap:.6rem; align-items:center; margin:0 0 .9rem}
.seg{display:inline-flex; border:1.5px solid var(--ink)}
.seg button{background:transparent; color:var(--ink); border:0; padding:.4rem .8rem; font:inherit; font-size:.85rem; font-weight:600; cursor:pointer}
.seg button+button{border-left:1.5px solid var(--ink)}
.seg button.on{background:var(--ink); color:var(--paper)}
.toolbar select,.toolbar input{font:inherit; font-size:.85rem; padding:.4rem .6rem; border:1.5px solid var(--hair); background:var(--paper); color:var(--ink)}
.toolbar input{flex:1 1 12rem; min-width:10rem}
.toolbar select:focus,.toolbar input:focus{outline:none; border-color:var(--ice)}
button.ghost{background:transparent; color:var(--ink); border:1.5px solid var(--ink); padding:.4rem .8rem; font:inherit; font-size:.85rem; font-weight:600; cursor:pointer}
button.ghost:hover{background:var(--ice); border-color:var(--ice); color:#0b0c0d}
.count{color:var(--muted); font-size:.85rem; margin-left:auto}
#log tbody tr{cursor:pointer}
#log tbody tr:hover{background:color-mix(in srgb, var(--ice) 10%, transparent)}
#log tbody tr.sel{background:color-mix(in srgb, var(--ice) 18%, transparent)}
#log tbody tr[hidden]{display:none}
.detail{border:1.5px solid var(--ink); padding:.9rem 1.1rem; margin-top:.9rem; font-size:.9rem}
.detail h3{font-family:var(--display); font-size:1rem; margin:0 0 .4rem; letter-spacing:-0.01em}
.detail dl{display:grid; grid-template-columns:7rem 1fr; gap:.25rem .8rem; margin:0}
.detail dt{color:var(--muted)}
.detail dd{margin:0}
footer{border-top:3px solid var(--ink); padding-top:1rem; color:var(--muted); font-size:.85rem; margin-top:1rem}
code{font-family:var(--mono); font-size:.8em}
@media (max-width:40rem){
  .band .wrap{padding:1.5rem 1rem 1.75rem}
  .wrap{padding:0 1rem}
  .verdict{flex-direction:column; align-items:flex-start; padding:1rem}
  .verdict .n{margin:0 0 .5rem}
}
@media print{.band{-webkit-print-color-adjust:exact; print-color-adjust:exact}}
"""


SCRIPT = r"""<script>
(function(){
  var log=document.getElementById('log'); if(!log) return;
  var rows=Array.prototype.slice.call(log.tBodies[0].rows);
  var sev='all', rule='', q='';
  var count=document.getElementById('log-count');
  var detail=document.getElementById('detail');
  var meaning=__RULE_MEANINGS__;
  function apply(){
    var n=0;
    rows.forEach(function(r){
      var ok=(sev==='all'||r.dataset.sev===sev)&&(!rule||r.dataset.rule===rule)&&
             (!q||r.textContent.toLowerCase().indexOf(q)>-1);
      r.hidden=!ok; if(ok) n++;
    });
    count.textContent=n+' of '+rows.length+' shown';
  }
  document.querySelectorAll('.seg button').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('.seg button').forEach(function(x){x.classList.remove('on')});
      b.classList.add('on'); sev=b.dataset.filter; apply();
    });
  });
  document.getElementById('rule-filter').addEventListener('change',function(e){rule=e.target.value; apply();});
  document.getElementById('log-search').addEventListener('input',function(e){q=e.target.value.trim().toLowerCase(); apply();});
  function show(r){
    rows.forEach(function(x){x.classList.remove('sel')}); r.classList.add('sel');
    var c=r.cells;
    detail.innerHTML='<h3>'+c[2].textContent+'</h3><dl>'+
      '<dt>Severity</dt><dd>'+c[0].textContent+'</dd>'+
      '<dt>Rule</dt><dd>'+c[1].textContent+'</dd>'+
      '<dt>Meaning</dt><dd>'+(meaning[c[1].textContent]||'')+'</dd>'+
      '<dt>Finding</dt><dd>'+c[3].textContent+'</dd>'+
      '<dt>Resolution</dt><dd>Fix the volume and re-run, or record a written waiver naming this record.</dd></dl>';
    detail.hidden=false; detail.scrollIntoView({block:'nearest'});
  }
  rows.forEach(function(r){
    r.addEventListener('click',function(){show(r)});
    r.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();show(r)}});
  });
  document.getElementById('dl-csv').addEventListener('click',function(){
    var esc=function(v){return '"'+String(v).replace(/"/g,'""')+'"'};
    var out=['severity,rule,record,detail'];
    rows.forEach(function(r){ if(!r.hidden){ var c=r.cells;
      out.push([c[0].textContent,c[1].textContent,c[2].textContent,c[3].textContent].map(esc).join(',')); }});
    var blob=new Blob([out.join('\r\n')+'\r\n'],{type:'text/csv;charset=utf-8'});
    var a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='exceptions.csv'; document.body.appendChild(a); a.click();
    setTimeout(function(){URL.revokeObjectURL(a.href); a.remove();},0);
  });
  apply();
})();
</script>"""


def write_html(
    findings: list[Finding],
    summary: ProductionSummary,
    hits: list[TermHit],
    path: str | Path,
    volume: str = "Production volume",
    max_rows: int = 250,
) -> Path:
    path = Path(path)
    state, count, headline, explanation = _verdict(findings)
    generated = datetime.now().strftime("%d %B %Y at %H:%M")

    facts = [
        ("Records", f"{summary.records:,}"),
        ("Bates range", f"{summary.bates_first or '—'} – {summary.bates_last or '—'}"),
        ("Imaged documents", f"{summary.documents_with_images:,}"),
        ("Pages", f"{summary.opt_pages:,}"),
        ("Attachments", f"{summary.families:,}"),
        ("Natives", f"{summary.natives_found:,} / {summary.natives_expected:,}"),
        ("Extracted text", f"{summary.text_found:,} / {summary.text_expected:,}"),
        ("Custodians", f"{len(summary.custodians):,}"),
    ]
    fact_html = "".join(
        f"<div class='fact'><dt>{_esc(label)}</dt>"
        f"<dd class='{'small' if label == 'Bates range' else ''}'>{_esc(value)}</dd></div>"
        for label, value in facts
    )

    import json as _json
    script_block = SCRIPT.replace("__RULE_MEANINGS__", _json.dumps(RULE_DESCRIPTIONS))
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Production QC — {_esc(volume)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=Instrument+Sans:wght@400;600&family=Martian+Mono:wght@400&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
<header class="band">
  <div class="wrap">
    <div class="mark" aria-hidden="true">{PENGUIN_MARK}</div>
    <div>
      <h1>Production <span>QC</span></h1>
      <p class="meta">{_esc(volume)} — checked by Penguin, {_esc(generated)}</p>
    </div>
  </div>
</header>
<main class="wrap">

<div class="verdict {state}">
  <div class="n">{count}</div>
  <div class="t">
    <h2>{_esc(headline)}</h2>
    <p>{_esc(explanation)}</p>
  </div>
</div>

<section>
  <h2>What is in the volume</h2>
  <dl class="facts">{fact_html}</dl>
</section>

<section>
  <h2>Exceptions by rule</h2>
  <div class="scroll">{_rule_rows(findings) or "<p class='empty'>No rules fired.</p>"}</div>
</section>

<section>
  <h2>Exception log</h2>
  <div class="scroll">{_finding_rows(findings, max_rows)}</div>
</section>

{_term_rows(hits)}

<footer>
  Reproduce with <code>penguin run --dat &lt;file&gt; --opt &lt;file&gt; --volume &lt;dir&gt;</code>.
  Findings are advisory; a defect is closed by fixing the volume or recording a written waiver.
</footer>
</main>
{script_block}
</body>
</html>"""

    path.write_text(document, encoding="utf-8")
    return path

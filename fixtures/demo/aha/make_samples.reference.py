"""Generate the sample Aha! exports used by the demo scenario (ILLUSTRATIVE DATA).

v1  baseline snapshot of the 2027 solutions
v2  AI Proactive Outreach -> "GA candidate ready" with an APPROVED gate      => triggers generation
    Outbound Dialler     -> "GA candidate ready" but gate still PENDING     => ignored (safety rule)
    CRM Lite feature flag flipped off -> on                                 => ignored (safety rule)
    Release 2026 R12 -> "Cutoff approved"                                   => triggers release assets
v3  AI Proactive Outreach capabilities / limitations change                 => approved assets go stale
aha_records_v2.pdf  Aha! "Export → PDF" of two records at their v2 state (AI Proactive Outreach, Outbound
    Dialler). Importing it after v1 gives the same decisions for those records as v2.xlsx. Needs Edge/Chrome.
aha_launch_mix.xlsx  One-file launch scenario: 11 solutions across 4 releases; the next launch (2026 R12) mixes
    approved gates, a pending gate and a record with no workflow status.

    .venv/Scripts/python scripts/make_samples.py
"""
from __future__ import annotations

import copy
import html
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "samples"

AIPO_CAPS = ("Event-triggered outreach from Salesforce and Microsoft Dynamics events; AI virtual agent voice and SMS "
             "conversations for routine intents; Warm handoff to live agents with conversation summary; "
             "Consent and calling-window enforcement; Campaign analytics")

SOLUTIONS = [
    {"Reference #": "CCAAS-E-101", "Name": "AI Proactive Outreach", "Workflow status": "Pilot approved", "GTM gate status": "Approved",
     "Launch tier": "Tier 1", "Product line": "Vonage Contact Center", "Release": "2027 R1", "Target GA date": "2027-01-28",
     "Description": "AI-driven outbound conversations (voice, SMS, WhatsApp beta) triggered by CRM events, resolved by an AI virtual agent with warm handoff to live agents.",
     "Target personas": "Contact Centre Operations Leader; Campaign / Marketing Manager; IT / Systems Architect",
     "Target segments": "Financial services; Retail & eCommerce; Logistics; Healthcare (pilot only)",
     "Competitors": "Northwind CX; Contoso Contact; Fabrikam Engage", "Capabilities": AIPO_CAPS,
     "Pricing notes": "Add-on to Vonage Contact Center, per outbound conversation; price list pending commercial approval",
     "Known limitations": "CRM triggers for Salesforce and Microsoft Dynamics only; Voice AI in English and Spanish at GA; WhatsApp channel is Beta at GA",
     "Success metrics": "20% reduction in avoidable inbound contacts; 60%+ containment for routine intents; Campaign set-up under 1 day",
     "PMM owner": "Priya Shah", "Product owner": "Daniel Okafor", "CS owner": "Marta Kowalski", "Feature flag": "on (pilot accounts)",
     "PRD": "ai-proactive-outreach.md", "Regions": "US, UK, EU (pending AI voice disclosure review)"},
    {"Reference #": "CCAAS-E-102", "Name": "CRM Lite", "Workflow status": "Beta approved", "GTM gate status": "Approved",
     "Launch tier": "Tier 1", "Product line": "Vonage Contact Center", "Release": "2026 R12", "Target GA date": "2026-12-10",
     "Description": "A lightweight built-in CRM for small contact centres that do not have an enterprise CRM.",
     "Target personas": "Contact Centre Manager; Small business owner", "Target segments": "SMB; Mid-market",
     "Competitors": "Contoso Contact", "Capabilities": "Contact records and interaction history; Case notes in the agent desktop; CSV import",
     "Pricing notes": "Included in VCC Premium", "Known limitations": "Up to 50,000 contacts per account at launch",
     "Success metrics": "Adoption by 30% of new SMB VCC accounts", "PMM owner": "Priya Shah", "Product owner": "Lena Fischer",
     "CS owner": "Marta Kowalski", "Feature flag": "off", "PRD": "", "Regions": "US, UK"},
    {"Reference #": "CCAAS-E-103", "Name": "BYO CRM", "Workflow status": "Solution defined", "GTM gate status": "Approved",
     "Launch tier": "Tier 2", "Product line": "Vonage Contact Center", "Release": "2027 R2", "Target GA date": "2027-03-25",
     "Description": "Bring-your-own-CRM connector framework so customers can connect any CRM via a configurable API connector.",
     "Target personas": "IT / Systems Architect", "Target segments": "Mid-market; Enterprise", "Competitors": "Northwind CX",
     "Capabilities": "Configurable REST connector; Screen-pop of CRM records; Click-to-dial", "Pricing notes": "Included in VCC Enterprise",
     "Known limitations": "Real-time sync limited to contact and case objects", "Success metrics": "10 production connectors in first quarter",
     "PMM owner": "Tom Becker", "Product owner": "Lena Fischer", "CS owner": "Marta Kowalski", "Feature flag": "off", "PRD": "", "Regions": "Global"},
    {"Reference #": "CCAAS-E-104", "Name": "Outbound Dialler", "Workflow status": "Pilot approved", "GTM gate status": "Approved",
     "Launch tier": "Tier 1", "Product line": "Vonage Contact Center", "Release": "2027 R1", "Target GA date": "2027-01-28",
     "Description": "Predictive, progressive and preview dialling modes for agent-led outbound campaigns.",
     "Target personas": "Contact Centre Operations Leader; Collections Manager", "Target segments": "Financial services; Utilities",
     "Competitors": "Contoso Contact; Northwind CX", "Capabilities": "Predictive, progressive and preview dialling; List management; Answering machine detection",
     "Pricing notes": "Per outbound agent seat", "Known limitations": "Predictive mode not available in Germany at launch",
     "Success metrics": "15% increase in right-party contacts per agent hour", "PMM owner": "Tom Becker", "Product owner": "Daniel Okafor",
     "CS owner": "Marta Kowalski", "Feature flag": "on (pilot accounts)", "PRD": "", "Regions": "US, UK"},
    {"Reference #": "UCAAS-E-201", "Name": "Virtual Receptionist", "Workflow status": "Beta approved", "GTM gate status": "Approved",
     "Launch tier": "Tier 2", "Product line": "Vonage Business Communications", "Release": "2026 R12", "Target GA date": "2026-12-10",
     "Description": "An AI receptionist that answers business calls, routes callers and takes messages 24/7.",
     "Target personas": "Small business owner; Office manager", "Target segments": "SMB; Professional services",
     "Competitors": "Fabrikam Engage", "Capabilities": "Natural-language call answering; Intelligent routing; Message taking with transcript",
     "Pricing notes": "Add-on per number", "Known limitations": "English only at launch", "Success metrics": "5,000 activated numbers in 6 months",
     "PMM owner": "Ana Ruiz", "Product owner": "Sam Patel", "CS owner": "Joe Lin", "Feature flag": "on (beta accounts)", "PRD": "", "Regions": "US"},
    {"Reference #": "UCAAS-E-202", "Name": "Mobile Connect", "Workflow status": "Opportunity approved", "GTM gate status": "Approved",
     "Launch tier": "Tier 2", "Product line": "Vonage Business Communications", "Release": "2026 R12", "Target GA date": "2027-05-20",
     "Description": "Native mobile network integration so business numbers ring on employees' mobile phones without an app.",
     "Target personas": "IT Manager; Mobile workforce leader", "Target segments": "Mid-market; Field services",
     "Competitors": "Northwind CX", "Capabilities": "Business number on native dialler; Call recording for mobile calls",
     "Pricing notes": "TBD", "Known limitations": "Available with partner mobile operators only", "Success metrics": "TBD",
     "PMM owner": "Ana Ruiz", "Product owner": "Sam Patel", "CS owner": "Joe Lin", "Feature flag": "off", "PRD": "", "Regions": "UK"},
    {"Reference #": "UCAAS-E-203", "Name": "OCS/Fusion Tariff", "Workflow status": "Solution defined", "GTM gate status": "Pending",
     "Launch tier": "Tier 3", "Product line": "Vonage Business Communications", "Release": "2027 R2", "Target GA date": "2027-04-15",
     "Description": "New bundled tariff combining UCaaS seats and mobile minutes.", "Target personas": "Finance buyer",
     "Target segments": "SMB", "Competitors": "", "Capabilities": "Bundled minutes; Single invoice", "Pricing notes": "Pending pricing committee",
     "Known limitations": "", "Success metrics": "", "PMM owner": "Ana Ruiz", "Product owner": "Sam Patel", "CS owner": "Joe Lin",
     "Feature flag": "off", "PRD": "", "Regions": "UK"},
]

RELEASES = [
    {"Release reference": "REL-2026-R12", "Release name": "2026 R12", "Release date": "2026-12-10", "Release status": "Planned",
     "Theme": "AI receptionist beta, built-in CRM for SMB contact centres, native mobile calling"},
    {"Release reference": "REL-2027-R1", "Release name": "2027 R1", "Release date": "2027-01-28", "Release status": "Planned",
     "Theme": "AI-driven outbound engagement"},
    {"Release reference": "REL-2027-R2", "Release name": "2027 R2", "Release date": "2027-03-25", "Release status": "Planned",
     "Theme": "Open CRM connectivity"},
]


# One-file launch scenario: the 7 solutions above plus these, across a shipped release, the next launch
# (2026 R12) and two later releases. Inside 2026 R12: approved gates at Beta / GA candidate / opportunity
# stages, one pending gate and one record with no workflow status (both must be skipped by the safety rule).
LAUNCH_EXTRA = [
    {"Reference #": "CCAAS-E-105", "Name": "AI Agent Assist", "Workflow status": "GA candidate ready", "GTM gate status": "Approved",
     "Launch tier": "Tier 1", "Product line": "Vonage Contact Center", "Release": "2026 R12", "Target GA date": "2026-12-10",
     "Description": "Real-time AI guidance for live agents: suggested answers, knowledge articles and automatic after-call summaries.",
     "Target personas": "Contact Centre Operations Leader; Team leader", "Target segments": "Financial services; Retail & eCommerce; Mid-market",
     "Competitors": "Northwind CX; Fabrikam Engage",
     "Capabilities": "Live transcription in the agent desktop; Suggested answers from the knowledge base; Automatic after-call summary and disposition",
     "Pricing notes": "Add-on per agent seat", "Known limitations": "English and Spanish transcription at GA; Summaries for voice calls only",
     "Success metrics": "30% reduction in after-call work; 10% faster average handle time",
     "PMM owner": "Priya Shah", "Product owner": "Daniel Okafor", "CS owner": "Marta Kowalski", "Feature flag": "on (pilot accounts)",
     "PRD": "", "Regions": "US, UK, EU"},
    {"Reference #": "UCAAS-E-204", "Name": "Teams Calling Analytics", "Workflow status": "Beta approved", "GTM gate status": "Pending",
     "Launch tier": "Tier 3", "Product line": "Vonage Business Communications", "Release": "2026 R12", "Target GA date": "2026-12-10",
     "Description": "Call quality and usage analytics for Microsoft Teams direct routing customers.",
     "Target personas": "IT Manager", "Target segments": "Mid-market; Enterprise", "Competitors": "",
     "Capabilities": "Call quality dashboards; Usage reports by site", "Pricing notes": "Included", "Known limitations": "Last 90 days of data",
     "Success metrics": "", "PMM owner": "Ana Ruiz", "Product owner": "Sam Patel", "CS owner": "Joe Lin", "Feature flag": "off",
     "PRD": "", "Regions": "Global"},
    {"Reference #": "UCAAS-E-205", "Name": "Self-serve Number Porting", "Workflow status": "", "GTM gate status": "",
     "Launch tier": "", "Product line": "Vonage Business Communications", "Release": "2026 R12", "Target GA date": "2026-12-10",
     "Description": "Customers port existing numbers online without a support ticket.", "Target personas": "Small business owner",
     "Target segments": "SMB", "Competitors": "", "Capabilities": "Online porting wizard; Porting status tracking", "Pricing notes": "",
     "Known limitations": "US numbers only", "Success metrics": "", "PMM owner": "Ana Ruiz", "Product owner": "Sam Patel",
     "CS owner": "Joe Lin", "Feature flag": "off", "PRD": "", "Regions": "US"},
    {"Reference #": "CCAAS-E-099", "Name": "Call Recording Vault", "Workflow status": "Shipped", "GTM gate status": "Approved",
     "Launch tier": "Tier 2", "Product line": "Vonage Contact Center", "Release": "2026 R11", "Target GA date": "2026-10-29",
     "Description": "Long-term, tamper-evident storage for call recordings with retention policies.",
     "Target personas": "Compliance officer", "Target segments": "Financial services; Healthcare", "Competitors": "Contoso Contact",
     "Capabilities": "Retention policies; Legal hold; Encrypted export", "Pricing notes": "Per TB stored",
     "Known limitations": "Maximum 10-year retention", "Success metrics": "40 regulated customers in first quarter",
     "PMM owner": "Tom Becker", "Product owner": "Lena Fischer", "CS owner": "Marta Kowalski", "Feature flag": "on",
     "PRD": "", "Regions": "US, UK, EU"},
]
LAUNCH_RELEASES = [{"Release reference": "REL-2026-R11", "Release name": "2026 R11", "Release date": "2026-10-29",
                    "Release status": "Released", "Theme": "Compliance and recording"}] + RELEASES


def _by_ref(rows, ref):
    return next(r for r in rows if r["Reference #"] == ref)


def write(name: str, solutions, releases) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame(solutions).to_excel(xw, sheet_name="Solutions", index=False)
        pd.DataFrame(releases).to_excel(xw, sheet_name="Releases", index=False)
    return path


# Aha! record PDF layout: title, a two-column field grid, then rich-text sections.
PDF_GRID = [("Workflow status", "Workflow status"), ("GTM gate status", "GTM gate status"), ("Launch tier", "Launch tier"),
            ("Release", "Release"), ("Product line", "Product line"), ("Target GA date", "Target GA date"),
            ("Assigned to", "Product owner"), ("PMM owner", "PMM owner"), ("CS owner", "CS owner"),
            ("Feature flag", "Feature flag"), ("Target personas", "Target personas"), ("Target segments", "Target segments"),
            ("Competitors", "Competitors"), ("Tags", None)]
PDF_SECTIONS = ["Description", "Capabilities", "Pricing notes", "Known limitations", "Success metrics"]
PDF_CSS = """body{font-family:Arial,sans-serif;font-size:11px;color:#222;margin:0} .page{page-break-after:always;padding:28px 34px}
.meta{color:#888;font-size:9px;margin-bottom:14px} .ref{color:#666;font-size:12px} h1{font-size:20px;margin:2px 0 14px}
table{border-collapse:collapse;width:100%} td{padding:5px 6px;vertical-align:top;border-bottom:1px solid #eee}
td.l{color:#666;width:13%} td.v{width:37%} h2{font-size:13px;border-bottom:1px solid #ccc;margin:18px 0 6px}"""


def _record_html(row: dict, page: int, pages: int) -> str:
    e = html.escape
    cells = [(label, "ai, outbound" if col is None else str(row[col])) for label, col in PDF_GRID]
    if cells[5][1]:
        cells[5] = (cells[5][0], date.fromisoformat(cells[5][1]).strftime("%b %d, %Y"))   # Aha! prints "Jan 28, 2027"
    rows = "".join("<tr>" + "".join(f'<td class="l">{e(l)}</td><td class="v">{e(v)}</td>' for l, v in cells[i:i + 2]) + "</tr>"
                   for i in range(0, len(cells), 2))
    body = ""
    for sec in PDF_SECTIONS:
        val = str(row[sec])
        if not val:
            continue
        items = [x.strip() for x in val.split(";")] if sec in {"Capabilities", "Known limitations", "Success metrics"} else []
        body += f"<h2>{e(sec)}</h2>" + ("<ul>" + "".join(f"<li>{e(x)}</li>" for x in items) + "</ul>" if items else f"<p>{e(val)}</p>")
    body += "<h2>Comments</h2><p>Priya Shah: Pricing still pending commercial approval, flagged to the pricing committee.</p>"
    return (f'<div class="page"><div class="meta">Exported from Aha! on Nov 19, 2026</div><div class="ref">{e(row["Reference #"])}</div>'
            f'<h1>{e(row["Name"])}</h1><table>{rows}</table>{body}<div class="meta">Page {page} of {pages}</div></div>')


def write_pdf(name: str, rows: list[dict]) -> Path | None:
    from gtm_os.render.html import html_to_pdf

    pages = "".join(_record_html(r, i + 1, len(rows)) for i, r in enumerate(rows))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "records.html"
        src.write_text(f"<html><head><meta charset='utf-8'><style>{PDF_CSS}</style></head><body>{pages}</body></html>", encoding="utf-8")
        path = OUT / name
        if not html_to_pdf(src, path):
            print(f"Skipped {name}: no headless Edge/Chrome found.")
            return None
    return path


def main() -> None:
    v1s, v1r = copy.deepcopy(SOLUTIONS), copy.deepcopy(RELEASES)
    write("aha_export_v1.xlsx", v1s, v1r)

    v2s, v2r = copy.deepcopy(v1s), copy.deepcopy(v1r)
    _by_ref(v2s, "CCAAS-E-101")["Workflow status"] = "GA candidate ready"           # approved decision
    od = _by_ref(v2s, "CCAAS-E-104")
    od["Workflow status"], od["GTM gate status"] = "GA candidate ready", "Pending"   # NOT approved -> ignored
    _by_ref(v2s, "CCAAS-E-102")["Feature flag"] = "on"                              # raw flag flip -> ignored
    v2r[0]["Release status"] = "Cutoff approved"                                    # release gate
    write("aha_export_v2.xlsx", v2s, v2r)
    write_pdf("aha_records_v2.pdf", [_by_ref(v2s, "CCAAS-E-101"), _by_ref(v2s, "CCAAS-E-104")])

    v3s, v3r = copy.deepcopy(v2s), copy.deepcopy(v2r)
    aipo = _by_ref(v3s, "CCAAS-E-101")
    aipo["Capabilities"] = AIPO_CAPS + "; Microsoft Teams channel for internal escalations"
    aipo["Known limitations"] = ("CRM triggers for Salesforce and Microsoft Dynamics only; Voice AI in English, Spanish and French at GA; "
                                 "WhatsApp channel is Beta at GA")
    write("aha_export_v3.xlsx", v3s, v3r)

    write("aha_launch_mix.xlsx", copy.deepcopy(SOLUTIONS) + copy.deepcopy(LAUNCH_EXTRA), copy.deepcopy(LAUNCH_RELEASES))
    print(f"Wrote samples to {OUT}")


if __name__ == "__main__":
    main()

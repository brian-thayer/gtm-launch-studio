# AI Proactive Outreach — Product Requirements Document

> ILLUSTRATIVE SAMPLE PRD created for the GTM Operating System proof of concept.
> Replace with the real PRD exported from Aha! / Confluence before using generated assets.

## Overview
AI Proactive Outreach lets contact centres start personalised, AI-driven outbound conversations
(voice, SMS and WhatsApp) triggered by events in the customer's CRM — such as a missed payment,
an upcoming appointment or a delivery delay — instead of waiting for the customer to call in.
An AI virtual agent handles the conversation, resolves routine requests end to end, and hands off
to a live agent with full context when needed.

## Problem
- Outbound engagement in most contact centres is manual, list-based and generic, so connect and
  conversion rates are low and agents spend time on routine calls.
- Customers contact the business about issues the business already knew about (delays, failed
  payments), creating avoidable inbound volume.
- Marketing campaign tools and contact centre tools are disconnected, so outreach is inconsistent
  and compliance (consent, calling windows) is hard to enforce.

## Target users and personas
- **Tier 1 — Primary champion: Contact Centre Operations Leader.** Owns cost-to-serve, inbound
  volume and agent productivity. "I want agents to be better prepared and my campaigns to convert."
- **Tier 2 — Co-champion: Campaign / Marketing Manager.** Owns outbound campaigns and conversion.
  "I want to launch a campaign in a day, not a sprint."
- **Tier 3 — Technical validator: IT / Systems Architect.** Owns CRM integration, security and data
  governance. "Show me the data flows and how consent is enforced."

## Target market
- Primary verticals: Financial services, Retail & eCommerce, Logistics, Healthcare (pilot only).
- Ideal customer profile: 50+ agent contact centres with an existing CRM holding structured
  customer data; current Vonage Contact Center (VCC) customers are the priority segment for launch.

## Key capabilities
1. **Event-triggered outreach**: start outreach from CRM events (Salesforce, Microsoft Dynamics) via
   no-code trigger rules.
2. **AI virtual agent conversations**: natural-language voice and SMS conversations that resolve
   routine intents (payment arrangements, appointment confirmation, delivery rescheduling).
3. **Warm handoff to live agents** with full conversation summary and customer context in the agent desktop.
4. **Consent and calling-window enforcement**: per-region calling windows, opt-out handling and
   consent checks before any outbound contact.
5. **Campaign analytics**: connect rate, containment rate, conversion and handoff reasons per campaign.
6. **WhatsApp channel**: available in Beta only at GA (not generally available).

## Availability and phasing
- Beta: completed with 6 design-partner customers.
- Pilot: 3 pilot customers (financial services and logistics) running live campaigns.
- GA target: 2027 R1 release. WhatsApp remains Beta at GA.

## Success metrics (targets, not yet proven)
- 20% reduction in avoidable inbound contacts for pilot campaigns.
- 60%+ containment for routine intents handled by the AI virtual agent.
- Campaign set-up time under 1 day for a standard event-triggered campaign.

## Known limitations at GA
- CRM triggers available for Salesforce and Microsoft Dynamics only; other CRMs via API.
- Voice AI conversations available in English and Spanish at GA; more languages later (not committed).
- Healthcare use cases limited to appointment reminders (no clinical content).

## Pricing and packaging
- Add-on to Vonage Contact Center, priced per outbound conversation. Final price list pending
  commercial approval (do not quote pricing externally).

## Competitive landscape
- Northwind CX, Contoso Contact and Fabrikam Engage are the competitors most often met in deals
  (see the knowledge base for competitive intelligence).

## Dependencies and risks
- Requires CRM connector configuration by the customer's admin.
- Regulatory review of outbound AI voice disclosure per region before GA in EU markets.

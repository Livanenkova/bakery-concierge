# Bakery Concierge — an AI order agent for a one-person cake bakery

Take-home for the **AI Solutions Builder** role (Smartcat).
A live, always-on assistant that turns free-text cake requests into priced, approved, booked orders — with a human in the loop.

**Walkthrough video:** _[https://www.loom.com/share/05b71b1956204d998d72d5a26c85cfce]_ · **Try the bot:** _[https://t.me/bakery_dasha_bot]_

---

## What it is (in one line)
A customer describes a cake in plain language (RU or EN) → **one AI agent** understands it and drafts the reply → **deterministic rules** price it and enforce a daily limit → **the owner approves with one tap** → confirmed orders auto-write to Google Sheets and book the date in Google Calendar.

## Architecture — little AI, in one place
- 🤖 **Concierge Agent (the only AI — Groq, llama-3.3-70b)** — understands free text, builds the order brief, classifies the message (order / confirm / complaint / small-talk), drafts replies in the owner's tone. *(prompt: see `agent_concierge.md` and the `SYSTEM` constant in `n8n_code_groq.js`.)*
- ⚙️ **Deterministic workers (not AI)** — Pricing (USD, tiers/decor/rush), a daily Capacity limit (3 cakes/day), Records → Google Sheets, Booking → Google Calendar.
- 👩‍🍳 **Human (the owner)** — approves every quote, decides when a day is full, handles sensitive messages, does the baking.

The design is built around a specific owner: a perfectionist who can't say "no" and fears losing control — so AI is deliberately minimal and always under approval.

## How it runs
Channel: **Telegram bot** (customer-facing), hosted 24/7 in **n8n** on a free Oracle VM.
The whole brain lives in one n8n **Code node** (`n8n_code_groq.js`): Telegram Trigger → Code node → it calls Groq, prices deterministically, routes to the owner, and writes to Google. Google side is a bound **Apps Script** (`google_apps_script.gs`) exposing the Sheet + Calendar + a per-day count endpoint.

> Instagram note: the bakery's real channel is Instagram, but its DM API is gated behind Meta App Review (weeks). The logic is channel-independent (an Instagram-shaped payload parses cleanly in n8n); the slice is built on Telegram and bridged to Instagram with a native auto-reply.

## Files
| File | What it is |
|------|-----------|
| `n8n_code_groq.js` | **Core.** The n8n Code node: Groq call + prompt, pricing, daily limit, message routing, approval flow, deposit + logging. |
| `agent_concierge.md` | The AI agent / prompt spec (what the Concierge does and how). |
| `google_apps_script.gs` | Apps Script: writes confirmed orders to Google Sheets + books the Google Calendar; `GET ?count=DATE` powers the daily limit. |
| `price_engine.py` | Standalone deterministic pricing engine (the rules, isolated + testable). |
| `concierge_sim.py` | Standalone simulation of the full loop (DM → AI brief → price → simulated send), real Groq with a regex fallback. |
| `DEMO_RESULTS.md` | Worked demo scenarios (normal order / day full / sensitive). |

## Run notes
- Keys are placeholders (`PASTE_...`) — no secrets committed. To run: set the Groq key, Telegram bot token, and the Apps Script web-app URL in the marked constants.
- Everything shown in the walkthrough runs end-to-end. Next steps (invoices/payments, scheduled reminders, real Instagram after App Review) are intentionally left as a roadmap, not half-built.

Built in ~6 hours. Deliberately lean stack: **one AI call + rules + Google + Telegram.**

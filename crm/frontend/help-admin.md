# 🛠️ Admin Guide — RankBuilder CRM

For managers: roles, users, lead sources, scoring rules, SLA, reports.

## 1. Roles

Four roles control what each person can see and do:

| Role | What they can do |
|------|------------------|
| **SYSTEM_ADMIN** | Everything — manage clients, users, all leads, all reports |
| **CLIENT_ADMIN** | Manage one client: users, sources, scoring, reports, campaigns |
| **AGENT** | Work leads (view/edit assigned or created leads, log follow-ups, quotes, AI drafts) |
| **VIEWER** | Read-only — see dashboards and leads, no edits |

## 2. Users

Add users under the **Users** tab (admin only). Assign a role and link them to the
correct client. Agents should be linked to their client so they see the right leads.
New users can be emailed their login details and forced to change their password on first login.

## 3. Lead Sources

When creating/editing a lead, pick the **Source** that reflects where it came from:

- **HARO** / **CONNECTIVELY** — journalist/PR query responses
- **GUEST_OUTREACH** — guest-post / outreach campaigns
- **WEBSITE** — website enquiry or Contact Form 7 submission
- **FACEBOOK** — social enquiry
- **DIRECT_MAIL** — physical mail / flyer drop
- **CALL_IN** — inbound phone call
- **WEB_SEARCH** — prospecting research
- **WHATSAPP** — WhatsApp / Meta message (auto-tagged by the webhook)
- **PPC** — paid search / ads
- **WORD_OF_MOUTH** — referral / word of mouth
- **ROADSIDE** — roadside campaign (site, cards, people stopped)
- **MANUAL** — anything entered by hand (use the source_detail field to say where)

**Tip for agents:** if a lead comes from the HOS website, pick **WEBSITE** directly —
don't use MANUAL. Reserve MANUAL for genuinely manual entries (paper, referrals, etc.)
and note the origin in source_detail.

## 4. Pipeline & Status

Standard flow: **NEW → REVIEWED → QUALIFIED → SENT → CONTACTED → CONVERTED / LOST**
Each lead also has a **Type** (VALID / INVALID / FOLLOW_UP) and a **payment_status**
(PENDING / RECEIVED) once it moves to production.

### Converting & payment (the agreed sequence)
1. The deal is **won** when the lead is moved to **CONVERTED** (edit drawer or Kanban drag —
   dragging also records the conversion outcome automatically).
2. The **correct amount** (quote / deal value) is entered on the lead.
3. **Managers then mark Payment = Received** to action the deal into production —
   this starts the install quiet-window and the post-install follow-up timer.

Payment status shows as **Paid ✓** once received. A converted lead with payment received
feeds the agent's commission record.

## 5. Auto-Assignment (region routing)

Leads are auto-assigned to reps by location:

- **Johannesburg / Gauteng** → Tiaan
- **Cape Town / Western Cape** → Richard
- **All other regions** → Craig (default)

Unrecognised regions fall back to the default rep. Managers can also reassign leads manually.

## 6. Follow-Up SLA & Escalation

Agents should log every contact attempt as a follow-up row with a **type** (Call/Email/
WhatsApp/SMS/Note/Other) and **outcome** (No answer / Left voicemail / Spoke / Sent /
Received / Other). The system tracks follow-up count and timestamps so you can see which
leads are being neglected. A fresh follow-up resets the escalation ladder.

**Scheduled reminders** (set by agents on a lead) email the rep at the chosen time and are
auto-dismissed once the lead is converted, lost or archived.

## 7. Reports

The **Dashboard** tab gives you the pipeline funnel, rep productivity and lead flow.
Use the source breakdown to see which channels generate the best leads. The weekly digest
emails key metrics to management automatically.

## 8. Clients (multi-tenant)

Under **Clients** (SYSTEM_ADMIN only) you can provision a new client with its own
admin login, API key and campaign. Each client's data is isolated.

## Quick tips
- Keep sources accurate — they drive all channel reporting.
- Monitor follow-up counts: many leads go cold because nobody logged a second call.
- Mark leads LOST early if they're invalid — don't leave them hanging in the funnel.
- Use the Export button to download filtered lead lists as CSV.

Need help? Contact your system admin.

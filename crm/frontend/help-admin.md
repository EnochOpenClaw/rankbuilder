# 🛠️ Admin Guide — RankBuilder CRM

For managers: roles, users, lead sources, scoring rules, SLA, reports, hand-off.

## 1. Roles

Five roles control what each person can see and do:

| Role | What they can do |
|------|------------------|
| **SYSTEM_ADMIN** | Everything — manage clients, users, all leads, all reports |
| **CLIENT_ADMIN** | Manage one client: users, sources, scoring, reports, campaigns |
| **SALES_MANAGER** | Regional sales lead — manage their client's leads, log follow-ups, reassign reps, hand leads off to partner clients (added 2026-09-14) |
| **AGENT** | Work leads (view/edit assigned or created leads, log follow-ups, quotes, AI drafts) |
| **VIEWER** | Read-only — see dashboards and leads, no edits |

**User groups (additive):** a user can also belong to a group such as **Partner Handoff Managers** without any role change. Group membership only widens read access (all clients' leads + the top-bar client switcher) — it never changes the user's role or permissions.

## 2. Users

Add users under the **Users** tab (admin only). Assign a role and link them to the
correct client. Agents should be linked to their client so they see the right leads.
New users can be emailed their login details and forced to change their password on first login.

Groups: the System Admin manages the **Partner Handoff Managers** group (currently
tiaan, robin, vanessa) — members get cross-client read access and the client switcher,
without being promoted to SYSTEM_ADMIN.

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
   follow-up and SLA nudges go quiet until the lead is CONVERTED or LOST
   (changed 2026-09-15: was a 7-day window; now indefinite — paid jobs are in
   production, so they're never nagged as stale).

Payment status shows as **Paid ✓** once received. A converted lead with payment received
feeds the agent's commission record.

### Post-install follow-up (changed 2026-09-15)
The customer review-ask + rep check-in email fires **7 days after the lead is marked
CONVERTED** — not after payment — so it only goes out once the job is actually won and
delivered. (Changed from payment-based after the Gorr Glass case: a paid-but-not-yet-won
job was getting the review-ask during production.)

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

**Handed-off source leads are never SLA-flagged** — they're trail markers; the partner
copy is the live lead that carries any SLA responsibility.

## 7. Reports

The **Dashboard** tab gives you the pipeline funnel, rep productivity and lead flow.
Use the source breakdown to see which channels generate the best leads. The weekly digest
emails key metrics to management automatically.

**Handed-off source leads are excluded from all reports and dashboard stats** (2026-09-14,
Kiara Ross case) — a handed-off job shows once, under the partner's client. Stats always
reflect live jobs only.

## 8. Clients (multi-tenant)

Under **Clients** (SYSTEM_ADMIN; read-only for hand-off group members) you can provision a
new client with its own admin login, API key and campaign. Each client's data is isolated.

## 9. Hand-off to partner clients

- **Who:** SYSTEM_ADMIN, CLIENT_ADMIN and SALES_MANAGER can hand a lead off (e.g. to
  Cape Town, Southern Shutters).
- **What happens:** a **copy** of the lead is created under the partner client and becomes
  the live, tracked job (status, follow-ups, reports, notifications all live there). The
  **original is archived** — it drops off the rep's queue, stops follow-up/SLA nudges, and
  is excluded from stats.
- **Picking a target:** hand-off managers open the **Clients** tab, select the partner
  client, and see its **contacts** (e.g. sian@southernshutters.co.za) to choose who
  receives the job.

## 10. Switching clients (top bar)

The **client dropdown** in the top bar (and the mobile menu) appears for **SYSTEM_ADMIN**
and members of the **Partner Handoff Managers** group (tiaan, robin, vanessa).

- Directors (robin, vanessa) use it for branch-wide oversight — what's done vs not followed up.
- Regional leads (tiaan) use it to view and work leads across clients.
- Everyone else (e.g. branch reps such as richard) stays locked to their own client —
  they never see other branches' leads or the switcher.

## Quick tips
- Keep sources accurate — they drive all channel reporting.
- Monitor follow-up counts: many leads go cold because nobody logged a second call.
- Mark leads LOST early if they're invalid — don't leave them hanging in the funnel.
- Keep CONVERTED + Payment=Received current — the post-install follow-up and stats depend on it.
- Use the Export button to download filtered lead lists as CSV.

Need help? Contact your system admin.

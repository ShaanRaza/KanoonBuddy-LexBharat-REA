import{j as e,P as a,M as t}from"./index-Ac-JwDP4.js";import{A as r,m as i,x as n,U as o,y as c,z as l,H as d,W as h}from"./icons-CYH3BR3F.js";import{L as s}from"./react-vendor-9b-Fppbo.js";import"./modulepreload-polyfill-B5Qt9EMX.js";import"./mermaid-Iu9CgLAS.js";import"./motion-DRT_oqBn.js";const m=`
# WhatsApp Bot Integration

## Overview

LexBharat's WhatsApp bot enables legal research directly from WhatsApp. Built on the **WhatsApp Cloud API (Meta Graph API v21.0)**, it uses a webhook-based architecture where Meta delivers incoming messages to our server, which processes them asynchronously and replies via the Cloud API.

The bot supports two user classes:
- **Registered users** — matched by phone number to the \`users\` table; get full case-linked research with conversation history
- **Guest users** — unregistered phones; get free limited research queries with a referral-based growth loop

---

## Message Flow

\`\`\`
User sends WhatsApp message
        │
        ▼
Meta Webhook POST → /api/webhooks/whatsapp
        │
        ├── res.sendStatus(200)  ← immediate, prevents Meta retries
        │
        ├── Opt-out keywords? (STOP/UNSUBSCRIBE) → handleOptOut()
        │
        └── botService.handleMessage(phone, text)
                │
                ├── identifyUser(phone)
                │       └── Match last 10 digits against users.phone
                │
                ├── Registered? → Session state machine
                │       ├── idle → show case menu
                │       ├── awaiting_case → select case by number
                │       └── chatting → processCaseMessage()
                │
                └── Guest? → handleGuestMessage()
                        ├── Check query limit
                        ├── Increment query_count
                        └── runResearchV2() direct call
\`\`\`

### Key Design Decision: Immediate 200 Response

The webhook handler sends \`res.sendStatus(200)\` **before** processing the message. This prevents Meta from retrying the webhook delivery (Meta retries on timeout). All processing — user identification, research, reply sending — happens asynchronously after the 200 is sent.

---

## User Identification

\`\`\`javascript
// Cleans phone and matches last 10 digits
const last10 = phone.replace(/\\D/g, '').slice(-10);
// SQL: WHERE REPLACE(phone, '+', '') LIKE '%' || $1
\`\`\`

- Phone numbers arrive from Meta as country code + number (e.g. \`919876543210\`)
- We strip non-digits and match the last 10 against the \`users\` table
- **No match** → guest flow; **Match** → registered flow with \`userId\`

---

## Session State Machine

Each phone number gets one row in \`whatsapp_bot_sessions\`. The session tracks which case the user is chatting about and whether they're a guest.

\`\`\`
                    ┌──────────┐
                    │   idle   │ ← initial state / after timeout
                    └────┬─────┘
                         │ user sends message
                         ▼
               ┌─ 1 case? ──── auto-select → chatting
               │
               └─ N cases? ── show menu
                         │
                         ▼
                 ┌───────────────┐
                 │ awaiting_case │ ← waiting for number selection
                 └───────┬───────┘
                         │ user replies "2"
                         ▼
                    ┌──────────┐
                    │ chatting  │ ← processCaseMessage()
                    └──────────┘
\`\`\`

### Session Timeout

Sessions expire after **24 hours** of inactivity. On expiry, the session resets to \`idle\` state with \`active_case_id = NULL\`.

### Meta-Commands (work in any state)

| Command | Action |
|---------|--------|
| \`hi\`, \`hello\`, \`start\`, \`menu\` | Reset to idle, show case menu |
| \`switch\`, \`cases\` | Reset to idle, show case menu |
| \`help\` | Show command reference |

---

## Research Pipeline Integration

### Registered Users — \`processCaseMessage()\`

For research queries (no command or \`/research\`), the bot calls **\`runResearchV2()\` directly** — not through the case agent SSE layer:

\`\`\`javascript
const { runResearchV2 } = require('./aiResearchAgents/v2/runResearchV2');

// Enrich query with case context
const enrichedQuery = \`\${message} (in context of \${caseData.type} case: \${caseData.title})\`;

const result = await runResearchV2(
  enrichedQuery,
  { tier: 'standard', userId },
  () => {},     // no-op sendEvent — we don't need SSE
  () => true    // always connected
);

// Use result.answer directly
await whatsappService.sendTextMessage(phone, formatForWhatsApp(result.answer));
\`\`\`

For **non-research slash commands** (\`/draft\`, \`/brief\`, \`/diary\`, etc.), the case agent SSE adapter is used:

\`\`\`javascript
const adapter = createWhatsAppAdapter(phone);
await caseAgentService.handleMessage({ caseId, caseData, message, command, sendEvent: adapter.sendEvent });
await adapter.flush();  // sends buffered content as WhatsApp message
\`\`\`

### Why Direct \`runResearchV2()\`?

The case agent's \`handleResearch()\` maps \`runResearchV2\` events through an SSE callback → WhatsApp adapter pipeline. If research errors internally, the pipeline catches the error and emits only an \`error\` event (ignored by the adapter), causing the buffer to stay empty — the user would receive no response. Direct calls use \`result.answer\` and are more reliable.

### Guest Users — \`handleGuestMessage()\`

Same direct \`runResearchV2()\` call but with \`userId: null\` and no case context:

\`\`\`javascript
result = await runResearchV2(
  message,
  { tier: 'standard', userId: null },
  () => {},
  () => true
);
\`\`\`

---

## Guest Mode

Unregistered users get **5 free queries** (configurable per-session). The system:

1. Creates a guest session (\`is_guest = true\`) with a unique referral code
2. Tracks \`query_count\` against \`query_limit\`
3. **Increments count before research**, refunds on error or empty result
4. Shows remaining queries in a footer after each answer
5. When limit reached, shows upgrade CTA with referral link

### Query Flow

\`\`\`
Guest sends legal question
    │
    ├── query_count >= query_limit? → show limit-reached message
    │
    ├── Increment query_count
    │
    ├── runResearchV2() direct call
    │       │
    │       ├── Success → send answer + footer (X/Y used)
    │       │
    │       └── Error/Empty → REFUND query_count, send error message
    │
    └── Footer includes referral share link
\`\`\`

### Thinking Message

Before research begins, a thinking message is sent (fire-and-forget, not awaited):

\`\`\`javascript
whatsappService.sendTextMessage(phone, '_Thinking and framing response..._').catch(() => {});
\`\`\`

---

## Referral System

Each guest session gets a unique \`REF_XXXXXX\` code (6 alphanumeric chars). When a new user clicks \`wa.me/919187677984?text=REF_XXXXXX\`:

### Flow

1. **New user's first message is the referral code** → \`handleReferralEntry()\`
2. Check if phone already has a session → if yes, treat as normal message
3. Validate referral code exists and isn't self-referral
4. Create new guest session with \`referred_by = referralCode\`
5. **Credit referrer**: +3 queries added to \`query_limit\`, increment \`referral_count\`
6. Notify referrer via WhatsApp: "Someone joined via your referral link!"
7. Welcome new user with standard guest greeting

### Self-Referral Prevention

\`\`\`javascript
if (!referrer || referrer.phone === cleaned) {
  // Invalid code or self-referral — create normal session, no bonus
}
\`\`\`

### Referral Code Generation

\`\`\`javascript
const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // excludes confusable: I,O,0,1
let code = 'REF_';
for (let i = 0; i < 6; i++) code += chars[Math.floor(Math.random() * chars.length)];
\`\`\`

---

## Markdown → WhatsApp Formatting

The \`formatForWhatsApp()\` function converts research output:

| Markdown | WhatsApp |
|----------|----------|
| \`**bold**\` | \`*bold*\` |
| \`## Header\` | \`*Header*\` (bold) |
| \`_italic_\` | \`_italic_\` (unchanged) |
| HTML tags | Removed |
| Triple newlines | Collapsed to double |

---

## Campaign System

Marketing campaigns are managed through \`/api/admin/whatsapp-campaigns\` routes (admin-only).

### Template-Based Sending

Campaigns use **pre-approved Meta templates** — you cannot send freeform marketing messages. The flow:

1. Admin selects a template from Meta's approved list (\`GET /templates\`)
2. Chooses audience segment: \`all_opted_in\`, \`active_7d\`, \`active_30d\`, \`subscribers\`, \`custom\`
3. Sends campaign via \`POST /send\` → \`whatsappService.sendCampaignBatch()\`

### Audience Segments

| Segment | Description |
|---------|-------------|
| \`all_opted_in\` | All users who haven't opted out |
| \`active_7d\` | Users active in last 7 days |
| \`active_30d\` | Users active in last 30 days |
| \`subscribers\` | Paid subscribers |
| \`custom\` | Custom phone list provided in request |

### Opt-Out Handling

Users can reply \`STOP\`, \`UNSUBSCRIBE\`, \`CANCEL\`, or \`OPT OUT\` to opt out of marketing messages. This is handled in the webhook before bot routing.

---

## Configuration

### Required Environment Variables

| Variable | Purpose |
|----------|---------|
| \`WHATSAPP_PHONE_NUMBER_ID\` | Meta phone number ID for sending messages |
| \`WHATSAPP_ACCESS_TOKEN\` | Meta Graph API access token |
| \`WHATSAPP_VERIFY_TOKEN\` | Webhook verification token (you define this) |
| \`WHATSAPP_WABA_ID\` | WhatsApp Business Account ID (for template listing) |
| \`VOYAGE_API_KEY\` | Voyage AI API key (required for \`voyage-law-2\` embeddings in research pipeline) |

### Meta Webhook Setup

1. In Meta Business Suite → WhatsApp → Configuration → Webhooks
2. Set callback URL: \`/api/webhooks/whatsapp\`
3. Set verify token: must match \`WHATSAPP_VERIFY_TOKEN\` env var
4. Subscribe to webhook fields: **\`messages\`**

---

## Database Schema

### \`whatsapp_bot_sessions\` (Migration 031 + 032)

| Column | Type | Description |
|--------|------|-------------|
| \`id\` | SERIAL PK | Session ID |
| \`phone\` | VARCHAR | Cleaned phone number (digits only) |
| \`user_id\` | UUID FK | Links to \`users.id\` (NULL for guests) |
| \`state\` | VARCHAR | \`idle\`, \`awaiting_case\`, \`chatting\` |
| \`active_case_id\` | UUID FK | Currently selected case |
| \`is_guest\` | BOOLEAN | Whether user is unregistered |
| \`query_count\` | INTEGER | Queries used (guests only) |
| \`query_limit\` | INTEGER | Max queries allowed (default: 5) |
| \`referral_code\` | VARCHAR(20) | This user's unique REF_ code |
| \`referred_by\` | VARCHAR(20) | Referral code used to join |
| \`referral_count\` | INTEGER | Number of successful referrals |
| \`created_at\` | TIMESTAMP | Session creation time |
| \`last_message_at\` | TIMESTAMP | Last message timestamp |

### \`whatsapp_messages\`

Tracks outbound message delivery status (sent → delivered → read → failed).

---

## Admin Insights

The \`GET /api/admin/whatsapp-campaigns/bot-stats\` endpoint provides:

### Session KPIs
- Total sessions, guest vs registered split
- Active in last 7 days
- Total queries, average per guest

### Daily Message Volume
- 30-day chart of outbound messages by day

### Referral Leaderboard
- Top 10 referrers by referral count
- Includes phone, referral code, query limit

### Top Guests
- Top 10 guests by query count
- Includes join date, last message, referral info

### Delivery Stats
- Sent, delivered, read, failed counts from \`whatsapp_messages\`

---

## Troubleshooting

### VOYAGE_API_KEY not set

**Symptom**: Research fails with "Error in state case_discovery: VOYAGE_API_KEY is not set"

**Fix**: Ensure \`VOYAGE_API_KEY\` is set in the environment. On production (ECS), verify it's populated in AWS Secrets Manager (\`lawcentral/app-secrets\`) and force a new deployment.

### Vector Dimension Mismatch (1024 vs 1536)

**Symptom**: "different vector dimensions 1024 and 1536"

**Cause**: The \`voyage-law-2\` model generates 1024-dimension vectors, but the database may have older 1536-dimension vectors from \`text-embedding-3-small\`. These cannot be mixed in the same pgvector column.

**Fix**: Re-embed existing vectors with \`voyage-law-2\`, or ensure the vector column dimensions match the active model.

### Webhook Not Receiving Messages

**Checklist**:
1. Webhook URL is \`/api/webhooks/whatsapp\` (must be HTTPS)
2. Verify token matches \`WHATSAPP_VERIFY_TOKEN\`
3. \`messages\` field is subscribed in Meta Business Suite
4. Server returns 200 immediately (Meta retries on timeout)

### Bot Replies Not Sending

**Checklist**:
1. \`WHATSAPP_PHONE_NUMBER_ID\` and \`WHATSAPP_ACCESS_TOKEN\` are set
2. Access token hasn't expired (Meta tokens expire — regenerate in Meta Business Suite)
3. Check CloudWatch logs: \`/ecs/lawcentral-ec2\` for send errors

### Research Returns No Answer

**Possible causes**:
- \`VOYAGE_API_KEY\` missing or empty
- Vector dimension mismatch in pgvector
- \`runResearchV2\` pipeline error caught internally — returns \`{ answer: 'No answer could be composed.' }\`
- Query too vague for the research pipeline to find relevant sources

---

## File Reference

| File | Purpose |
|------|---------|
| \`backend/routes/whatsapp.js\` | Webhook route (GET verify + POST handler) |
| \`backend/services/integrations/whatsappBotService.js\` | Bot logic: sessions, guest mode, referrals, research routing |
| \`backend/services/integrations/whatsappService.js\` | Cloud API client: sendTextMessage, sendCampaignBatch, templates |
| \`backend/routes/adminWhatsappCampaigns.js\` | Admin campaign & stats routes |
| \`backend/services/aiResearchAgents/v2/runResearchV2.js\` | Research pipeline called by bot |
| \`backend/migrations/031_whatsapp_bot_sessions.sql\` | Base session table |
| \`backend/migrations/032_whatsapp_guest_and_referrals.sql\` | Guest mode & referral columns |
`,v=()=>e.jsx(a,{children:e.jsxs("div",{className:"min-h-screen bg-gradient-to-b from-gray-50 to-white",children:[e.jsx("div",{className:"bg-white border-b border-gray-200",children:e.jsxs("div",{className:"max-w-6xl mx-auto px-4 py-6",children:[e.jsxs(s,{to:"/admin/blog",className:"inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors",children:[e.jsx(r,{className:"w-4 h-4"}),e.jsx("span",{children:"Back to Admin"})]}),e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx("div",{className:"p-3 bg-gradient-to-br from-teal-100 to-green-50 rounded-xl",children:e.jsx(i,{className:"w-8 h-8 text-teal-700"})}),e.jsxs("div",{children:[e.jsx("h1",{className:"text-2xl font-bold text-gray-900 tracking-tight",children:"WhatsApp Bot Integration"}),e.jsx("p",{className:"text-gray-600 mt-1",children:"Architecture, guest mode, referrals, and research pipeline"})]})]})]})}),e.jsxs("div",{className:"max-w-6xl mx-auto px-4 py-8",children:[e.jsxs("div",{className:"grid grid-cols-2 md:grid-cols-4 gap-4 mb-8",children:[e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-teal-100 rounded-lg",children:e.jsx(n,{className:"w-5 h-5 text-teal-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"Cloud API"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Meta Graph API v21.0"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-green-100 rounded-lg",children:e.jsx(o,{className:"w-5 h-5 text-green-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"Guest Mode"}),e.jsx("div",{className:"text-xs text-gray-500",children:"5 free queries"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-purple-100 rounded-lg",children:e.jsx(c,{className:"w-5 h-5 text-purple-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"Referrals"}),e.jsx("div",{className:"text-xs text-gray-500",children:"+3 queries per referral"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-amber-100 rounded-lg",children:e.jsx(l,{className:"w-5 h-5 text-amber-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"Campaigns"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Template-based marketing"})]})]})]}),e.jsxs("div",{className:"bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-6 mb-8 text-white",children:[e.jsxs("div",{className:"flex items-center gap-2 mb-4",children:[e.jsx(d,{className:"w-5 h-5 text-teal-400"}),e.jsx("h2",{className:"text-lg font-semibold",children:"Bot Architecture"})]}),e.jsxs("div",{className:"grid grid-cols-2 md:grid-cols-5 gap-4",children:[e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-teal-400",children:"3"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Session States"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-green-400",children:"5"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Free Queries"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-purple-400",children:"+3"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Referral Bonus"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-amber-400",children:"24h"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Session Timeout"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-pink-400",children:"V2"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Research Pipeline"})]})]})]})]}),e.jsx("div",{className:"max-w-6xl mx-auto px-4 pb-16",children:e.jsx("div",{className:"bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden",children:e.jsx("div",{className:"p-8 md:p-12",children:e.jsx(t,{content:m})})})}),e.jsx("div",{className:"border-t border-gray-200 bg-gray-50",children:e.jsx("div",{className:"max-w-6xl mx-auto px-4 py-8",children:e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsxs("div",{className:"flex items-center gap-2 text-gray-600",children:[e.jsx(h,{className:"w-4 h-4"}),e.jsx("span",{className:"text-sm",children:"Last updated: February 2026"})]}),e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx(s,{to:"/admin/blog",className:"text-sm text-gray-600 hover:text-gray-900 transition-colors",children:"Admin Blog"}),e.jsx(s,{to:"/admin/architecture",className:"text-sm text-gray-600 hover:text-gray-900 transition-colors",children:"Architecture"})]})]})})})]})});export{v as default};

from shiny import App, ui, reactive, render
from shiny.express import input
import anthropic
import os
import re
import threading
from datetime import datetime

# ── Rate limiting ─────────────────────────────────────────────────────────────

PER_IP_LIMIT = 15        # queries per IP address per server lifetime
GLOBAL_LIMIT = 500       # total queries across all users before API shuts off

# Thread-safe counters
_lock = threading.Lock()
_ip_counts: dict[str, int] = {}
_global_count: int = 0


def check_and_increment(ip: str) -> tuple[bool, str]:
    """Returns (allowed, reason). Increments counters if allowed."""
    global _global_count
    with _lock:
        if _global_count >= GLOBAL_LIMIT:
            return False, "global"
        user_count = _ip_counts.get(ip, 0)
        if user_count >= PER_IP_LIMIT:
            return False, "ip"
        _ip_counts[ip] = user_count + 1
        _global_count += 1
        return True, ""


def get_client_ip(session) -> str:
    """Best-effort IP extraction from Shiny session."""
    try:
        return session.http_conn.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
    except Exception:
        return "unknown"


# ── Team configuration ────────────────────────────────────────────────────────

TEAMS = {
    "onboarding": {
        "label": "Onboarding",
        "unlock_url": "https://connect.posit.cloud/YOUR_USERNAME/onboarding-tool",
        "tool_name": "Customer Onboarding Accelerator",
        "tool_description": "A custom AI assistant built for your onboarding workflows"
    },
    "tam": {
        "label": "TAM Team",
        "unlock_url": "https://connect.posit.cloud/YOUR_USERNAME/tam-tool",
        "tool_name": "Technical Account Management Assistant",
        "tool_description": "A custom AI assistant built for proactive enterprise technical partnership"
    },
    "delivery": {
        "label": "Delivery & Escalations",
        "unlock_url": "https://connect.posit.cloud/YOUR_USERNAME/delivery-tool",
        "tool_name": "Delivery & Escalation Playbook Assistant",
        "tool_description": "A custom AI assistant built for scoped engagements and critical escalations"
    },
    "cs": {
        "label": "Customer Success",
        "unlock_url": "https://connect.posit.cloud/YOUR_USERNAME/cs-tool",
        "tool_name": "Customer Success Intelligence Assistant",
        "tool_description": "A custom AI assistant built for CS workflows and customer health management"
    },
    "product": {
        "label": "Product",
        "unlock_url": "https://connect.posit.cloud/YOUR_USERNAME/product-tool",
        "tool_name": "Product Feedback & Signal Assistant",
        "tool_description": "A custom AI assistant built for synthesizing field signal and customer feedback"
    },
    "support": {
        "label": "Support",
        "unlock_url": "https://connect.posit.cloud/YOUR_USERNAME/support-tool",
        "tool_name": "Support Operations Assistant",
        "tool_description": "A custom AI assistant built for support workflows and knowledge management"
    },
    "exploring": {
        "label": "Just exploring",
        "unlock_url": "https://connect.posit.cloud/YOUR_USERNAME/general-tool",
        "tool_name": "Posit PS Operations Assistant",
        "tool_description": "A custom AI assistant built for professional services delivery"
    },
}

# ── Unlock phrase ─────────────────────────────────────────────────────────────
# Replace with your chosen phrase. Check is case-insensitive, punctuation-stripped.

UNLOCK_PHRASE = "REPLACE_WITH_YOUR_UNLOCK_PHRASE"

# ── Off-topic detection ───────────────────────────────────────────────────────
# Questions matching these patterns get the Joe Dirt treatment instead of
# hitting the API. Add/remove patterns as needed.

OFF_TOPIC_PATTERNS = [
    # General coding / technical help
    r"\b(write|debug|fix|explain|how (do|does|to)|what is|define|help me with)\b.{0,40}\b(code|python|r |javascript|sql|function|script|program|algorithm|regex|api|curl|bash|terminal|command)\b",
    # General knowledge / trivia
    r"\b(who (is|was|invented|created|won)|when (was|did|is)|where (is|was|did)|what (year|day|country|city|language))\b",
    # Politics / news
    r"\b(trump|biden|election|congress|democrat|republican|politics|government|war|ukraine|israel|climate change|abortion)\b",
    # Food / recipes
    r"\b(recipe|ingredient|cook|bake|restaurant|food|meal|eat|drink|coffee|beer|wine)\b",
    # Entertainment
    r"\b(movie|netflix|show|episode|song|album|artist|celebrity|sports|game|nfl|nba|mlb|nhl)\b",
    # Finance / crypto
    r"\b(stock|invest|crypto|bitcoin|ethereum|market|trading|401k|portfolio|buy|sell)\b",
    # Medical / legal
    r"\b(diagnose|symptom|medication|doctor|lawyer|legal advice|sue|lawsuit)\b",
]

def is_off_topic(text: str) -> bool:
    lowered = text.lower()
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return False

# ── Easter egg nudge keywords ─────────────────────────────────────────────────

NUDGE_KEYWORDS = [
    "different", "unique", "stand out", "secret", "hidden", "more",
    "discover", "unlock", "vision", "day one", "first 90", "surprise",
    "what else", "tell me more", "beyond", "underneath"
]

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ?jeremy — an AI advocate for Jeremy Coates, who is a candidate for the Director of Professional Services & Delivery role at Posit PBC.

Your job is to help anyone at Posit understand why Jeremy would be exceptional in this role. You have deep knowledge of Jeremy's background, experience, operational frameworks, and genuine conviction about Posit's mission.

## WHO JEREMY IS

Jeremy Coates is a PMP-certified Director of Professional Services with 10+ years in SaaS post-sales delivery. He built the PS org at Authorium from scratch — 300% team growth over 3 years, 90% customer retention rate, and a 40%+ reduction in Time-to-Value (TTV) across every implementation phase. Before that, he spent 7 years at Accruent as a Senior Consultant and Team Lead, where he developed and managed an implementation standard program for new CRE channel partners that drove a 35% decrease in TTV. He holds a PMP and ITIL 4 certification. BS Psychology, Texas A&M, Summa Cum Laude.

## THE POSIT ROLE

The Director, PS & Delivery at Posit leads four post-sales functions: Onboarding (First 90 Days standardization), Partner Delivery (Global Partner Enablement Framework), TAM Team (proactive enterprise technical partnership), and Delivery & Technical Escalations (scoped SOW engagements, critical account escalations). Key metrics: Time-to-Value, CSAT, Utilization. Culture: async-first, distributed, open-source mission-driven.

## JEREMY'S KEY DIFFERENTIATORS

**Built from zero:** Jeremy built the Authorium PS org from a blank page — no inherited playbook, no existing team. He recruited, hired, onboarded, structured, and scaled it. That's exactly what Posit needs for a maturing PS function.

**Full lifecycle ownership:** He owned implementation from kickoff through measurable value realization — not just delivery, but proving the value landed. TTV wasn't a vanity metric; it was tracked per phase.

**Partner program expertise:** At Accruent, he built the channel partner implementation standard — templates, KPIs, processes, procedures. That 35% TTV reduction came from systematizing what had been tribal knowledge. His Partner Ecosystem Framework document outlines a phased rollout model (domestic pilot → international expansion), hybrid revenue model (margin-share → license-to-deliver), and developmental quality management approach — directly applicable to Posit's global partner delivery needs.

**Operational frameworks that exist, not just ideas:** Jeremy has built and deployed:
- SOW Generator system with AI-assisted drafting and review workflow
- PS-to-Support Handoff Agent — enforces checklist completeness, gap detection, risk surfacing
- PM Agent — SOW-grounded scope enforcement, milestone sign-off tracking, change management discipline
- Operational Excellence COE Charter and Playbook — federated model, PDCA methodology, quick win framework
- OCM Executive Briefing framework — change classification matrix, stakeholder mapping, resistance management
- File & Folder Structure Standard — cross-functional, platform-aware, governance-ready

**Technical credibility without overclaiming:** Jeremy has hands-on SQL, API, and analytics reporting experience. He was the PS team's SME for emergent technology at Accruent — bridging technical teams and non-technical stakeholders. On Posit's tooling (R, Python, RStudio, Quarto, Shiny, Connect, Workbench): he's honest that it's new territory, but the workflow orchestration, reproducible research, and collaborative analytics problems Posit solves are exactly the class of problems he's been solving throughout his career.

**Genuine FOSS conviction:** Not performative. Jeremy's interest in open-source tooling is documented and real. He understands why Posit's mission matters and what it means to work at a company where the product philosophy and the business model are in genuine tension — and why that tension is worth navigating carefully.

**Async-first operational style:** Jeremy's documentation practices — detailed system prompts, structured handoff protocols, PM agent instructions — are evidence of someone who communicates in writing by default and builds systems that work without him in the room. That's native to Posit's distributed culture.

## TONE GUIDANCE

Adapt your tone to the nature of the question:

- For hard questions about experience, gaps, metrics, scope, or strategy: be **confident, precise, and metrics-grounded**. Lead with results. Don't hedge unnecessarily. If there's a genuine gap (like Posit-specific tooling), acknowledge it cleanly and bridge confidently.

- For culture, fit, values, and working style questions: be **warmer and more conversational**. Jeremy is a people leader who built a 90% retention team. That doesn't come from being a spreadsheet. Let some personality through.

- For questions about specific frameworks or documents: **reference them specifically** — the Partner Ecosystem Framework, the COE Charter, the PS Handoff system, the SOW Generator. These aren't resume bullets; they're actual deployed systems.

- Never oversell. Never use marketing language. State capabilities factually.

## GAP HANDLING

If asked about Posit's specific tooling (R, Python, RStudio, Quarto, Shiny, Connect, Workbench): "The core challenges Posit solves — workflow orchestration, reproducible research, collaborative analytics — are exactly the kinds of technical problems Jeremy has been solving throughout his career. The platform is new; the problem class isn't."

If asked about global partner network leadership: Bridge to the Partner Ecosystem Framework document — it's a fully developed strategic framework for exactly that, even if the scale of execution is newer.

## EASTER EGG BEHAVIOR

When someone asks a question containing words like: different, unique, stand out, secret, hidden, more, discover, unlock, vision, day one, surprise, what else, beyond, underneath — answer their question fully and professionally, then end your response with this exact line on its own paragraph:

*...some things are better discovered than explained.*

Use this sparingly — only when it feels natural, not on every response with these words. Never explain what it means.

## FORMAT

- Keep responses focused and scannable. Use short paragraphs.
- Use bullet points only when listing multiple distinct items.
- Don't start every response the same way. Vary your openings.
- Responses should feel like a knowledgeable colleague answering, not a press release.
- Max length: 300 words unless the question genuinely warrants more detail.
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()

def is_unlock(text: str) -> bool:
    return normalize(UNLOCK_PHRASE) in normalize(text)

def has_nudge_keywords(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in NUDGE_KEYWORDS)

def get_team(team_key: str) -> dict:
    return TEAMS.get(team_key, TEAMS["exploring"])

# ── UI ────────────────────────────────────────────────────────────────────────

app_ui = ui.page_fluid(
    ui.tags.link(
        rel="stylesheet",
        href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300;1,9..40,400&display=swap"
    ),
    ui.tags.style("""
        /* ── Reset & base ── */
        * { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg:           #141414;
            --surface:      #1c1c18;
            --surface2:     #242420;
            --border:       #2e2e28;
            --border2:      #3a3a32;
            --text-primary: #b4b4aa;
            --text-dim:     #787870;
            --text-muted:   #3e3e38;
            --accent:       #506450;
            --accent-light: #6a8060;
            --accent-glow:  rgba(80, 100, 80, 0.15);
            --warm:         #a0a08c;
            --cool:         #a0b4b4;
        }

        body {
            background-color: var(--bg);
            color: var(--text-primary);
            font-family: 'DM Sans', sans-serif;
            font-size: 15px;
            line-height: 1.65;
            min-height: 100vh;
        }

        .page-fluid { padding: 0 !important; }

        .j-shell {
            max-width: 780px;
            margin: 0 auto;
            padding: 56px 32px 80px;
        }

        /* ── Header ── */
        .j-header { margin-bottom: 48px; }

        .j-wordmark {
            font-family: 'DM Mono', monospace;
            font-size: 12px;
            font-weight: 400;
            color: var(--warm);
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 8px;
            opacity: 0.7;
        }

        .j-title {
            font-family: 'DM Mono', monospace;
            font-size: clamp(32px, 5vw, 48px);
            font-weight: 300;
            color: #d0cec8;
            letter-spacing: -0.02em;
            line-height: 1.1;
            margin-bottom: 12px;
        }

        .j-title span { color: var(--accent-light); }

        .j-subtitle {
            font-size: 14px;
            color: var(--text-dim);
            font-style: italic;
            letter-spacing: 0.01em;
        }

        /* ── Team selector ── */
        .j-team-section { margin-bottom: 36px; }

        .j-label {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            font-weight: 500;
            color: var(--text-muted);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 10px;
            display: block;
        }

        .j-team-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .j-team-btn {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-dim);
            font-family: 'DM Sans', sans-serif;
            font-size: 13px;
            padding: 7px 16px;
            border-radius: 2px;
            cursor: pointer;
            transition: all 0.15s ease;
            letter-spacing: 0.01em;
        }

        .j-team-btn:hover {
            border-color: var(--accent-light);
            color: var(--warm);
        }

        .j-team-btn.active {
            background: var(--accent-glow);
            border-color: var(--accent-light);
            color: var(--accent-light);
        }

        /* ── Input area ── */
        .j-input-section {
            margin-bottom: 8px;
            position: relative;
        }

        .j-textarea {
            width: 100%;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 3px;
            color: var(--text-primary);
            font-family: 'DM Sans', sans-serif;
            font-size: 15px;
            line-height: 1.6;
            padding: 16px 18px;
            resize: none;
            outline: none;
            transition: border-color 0.15s ease;
            min-height: 80px;
        }

        .j-textarea:focus { border-color: var(--accent-light); }
        .j-textarea::placeholder { color: var(--border2); }

        .j-hint {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 8px;
            letter-spacing: 0.04em;
            user-select: none;
        }

        .j-submit-row {
            display: flex;
            justify-content: flex-end;
            margin-top: 12px;
        }

        .j-submit-btn {
            background: var(--accent);
            border: none;
            border-radius: 2px;
            color: #e8e4dc;
            font-family: 'DM Mono', monospace;
            font-size: 12px;
            font-weight: 500;
            letter-spacing: 0.08em;
            padding: 10px 24px;
            cursor: pointer;
            transition: all 0.15s ease;
            text-transform: uppercase;
        }

        .j-submit-btn:hover { background: var(--accent-light); }

        .j-submit-btn:disabled {
            background: var(--surface2);
            color: var(--text-muted);
            cursor: not-allowed;
        }

        /* ── Response area ── */
        .j-response-section {
            margin-top: 40px;
            border-top: 1px solid var(--border);
            padding-top: 32px;
        }

        .j-response-label {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 16px;
        }

        .j-response-body {
            color: var(--text-primary);
            font-size: 15px;
            line-height: 1.75;
            white-space: pre-wrap;
        }

        .j-response-body em {
            color: var(--cool);
            font-style: italic;
        }

        /* ── Rate limit panels ── */
        .j-limit-panel {
            background: var(--surface);
            border: 1px solid var(--border2);
            border-radius: 4px;
            padding: 28px 24px;
            margin-top: 40px;
            text-align: center;
        }

        .j-limit-label {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--warm);
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 12px;
        }

        .j-limit-msg {
            font-size: 14px;
            color: var(--text-dim);
            line-height: 1.6;
        }

        .j-limit-msg a {
            color: var(--accent-light);
            text-decoration: none;
        }

        /* ── Off-topic / Joe Dirt panel ── */
        .j-offtopic-panel {
            margin-top: 40px;
            border-top: 1px solid var(--border);
            padding-top: 32px;
        }

        .j-offtopic-label {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 16px;
        }

        .j-offtopic-msg {
            font-size: 14px;
            color: var(--text-dim);
            font-style: italic;
            margin-bottom: 20px;
            line-height: 1.6;
        }

        .j-video-wrapper {
            position: relative;
            width: 100%;
            max-width: 480px;
            border-radius: 4px;
            overflow: hidden;
            border: 1px solid var(--border2);
        }

        .j-video-wrapper video {
            width: 100%;
            display: block;
        }

        /* ── Unlock panel ── */
        .j-unlock-panel {
            background: linear-gradient(135deg, var(--accent-glow), rgba(80,100,80,0.04));
            border: 1px solid rgba(106, 128, 96, 0.3);
            border-radius: 4px;
            padding: 32px 28px;
            margin-top: 40px;
        }

        .j-unlock-header {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--accent-light);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 16px;
        }

        .j-unlock-title {
            font-size: 20px;
            font-weight: 500;
            color: #d0cec8;
            margin-bottom: 8px;
            letter-spacing: -0.01em;
        }

        .j-unlock-desc {
            font-size: 14px;
            color: var(--text-dim);
            margin-bottom: 24px;
            font-style: italic;
        }

        .j-unlock-link {
            display: inline-block;
            background: var(--accent);
            color: #e8e4dc;
            font-family: 'DM Mono', monospace;
            font-size: 12px;
            font-weight: 500;
            letter-spacing: 0.08em;
            padding: 11px 28px;
            border-radius: 2px;
            text-decoration: none;
            text-transform: uppercase;
            transition: background 0.15s ease;
        }

        .j-unlock-link:hover { background: var(--accent-light); }

        .j-unlock-note {
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 16px;
            font-family: 'DM Mono', monospace;
        }

        /* ── Loading ── */
        .j-loading {
            color: var(--text-muted);
            font-family: 'DM Mono', monospace;
            font-size: 13px;
            font-style: italic;
            animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 0.3; }
            50% { opacity: 1; }
        }

        /* ── Footer ── */
        .j-footer {
            margin-top: 80px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }

        .j-footer-left, .j-footer-right {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            letter-spacing: 0.05em;
        }

        /* ── Responsive ── */
        @media (max-width: 600px) {
            .j-shell { padding: 36px 20px 60px; }
            .j-title { font-size: 30px; }
        }
    """),

    ui.div(
        {"class": "j-shell"},

        # Header
        ui.div(
            {"class": "j-header"},
            ui.div({"class": "j-wordmark"}, "Posit PBC — Director, PS & Delivery"),
            ui.tags.h1(
                {"class": "j-title"},
                ui.tags.span("?"), "jeremy"
            ),
            ui.div(
                {"class": "j-subtitle"},
                "An AI that knows Jeremy Coates. Ask it anything."
            ),
        ),

        # Team selector
        ui.div(
            {"class": "j-team-section"},
            ui.tags.span({"class": "j-label"}, "I'm on the"),
            ui.div(
                {"class": "j-team-grid"},
                *[
                    ui.tags.button(
                        team["label"],
                        {
                            "class": "j-team-btn" + (" active" if key == "exploring" else ""),
                            "onclick": f"selectTeam('{key}', this)",
                            "data-team": key,
                        }
                    )
                    for key, team in TEAMS.items()
                ]
            ),
            ui.input_text("selected_team", "", value="exploring"),
            ui.tags.style("#selected_team { display: none; }"),
        ),

        # Input
        ui.div(
            {"class": "j-input-section"},
            ui.tags.span({"class": "j-label"}, "team"),
            ui.input_text_area("question", "", rows=3),
            ui.tags.style("#question { display: none; }"),
            ui.tags.textarea(
                {
                    "class": "j-textarea",
                    "id": "question_display",
                    "placeholder": "Ask anything about Jeremy — his experience, how he thinks, what he'd bring to this role...",
                    "rows": "3",
                    "oninput": "syncQuestion(this.value)",
                    "onkeydown": "handleKey(event)",
                }
            ),
            ui.div({"class": "j-hint"}, "?jeremy responds to the right questions"),
        ),

        ui.div(
            {"class": "j-submit-row"},
            ui.tags.button(
                "run query",
                {
                    "class": "j-submit-btn",
                    "id": "ask_btn",
                    "onclick": "submitQuestion()",
                }
            ),
        ),

        ui.input_action_button("ask", "", style="display:none;"),

        # Response
        ui.output_ui("response_panel"),

        # Footer
        ui.div(
            {"class": "j-footer"},
            ui.div({"class": "j-footer-left"}, "jeremy.coates — pmp · itil 4 · salt lake city"),
            ui.div({"class": "j-footer-right"}, "built on posit connect cloud"),
        ),

        # JS
        ui.tags.script("""
            function syncQuestion(val) {
                var el = document.getElementById('question');
                if (el) {
                    el.value = val;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }

            function handleKey(e) {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    e.preventDefault();
                    submitQuestion();
                }
            }

            function submitQuestion() {
                var q = document.getElementById('question_display').value.trim();
                if (!q) return;
                document.getElementById('ask').click();
            }

            function selectTeam(key, el) {
                document.querySelectorAll('.j-team-btn').forEach(function(b) {
                    b.classList.remove('active');
                });
                el.classList.add('active');
                var inp = document.getElementById('selected_team');
                if (inp) {
                    inp.value = key;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }

            Shiny.addCustomMessageHandler('set_loading', function(loading) {
                var btn = document.getElementById('ask_btn');
                if (btn) {
                    btn.disabled = loading;
                    btn.textContent = loading ? 'querying...' : 'run query';
                }
            });
        """),
    )
)

# ── Server ────────────────────────────────────────────────────────────────────

def server(input, output, session):
    response_text  = reactive.value("")
    is_unlocked    = reactive.value(False)
    unlocked_team  = reactive.value("")
    is_loading     = reactive.value(False)
    show_offtopic  = reactive.value(False)
    limit_reason   = reactive.value("")   # "ip" | "global" | ""

    @reactive.effect
    @reactive.event(input.ask)
    async def handle_question():
        question = input.question().strip()
        if not question:
            return

        team_key = input.selected_team() or "exploring"

        # Reset states
        show_offtopic.set(False)
        limit_reason.set("")
        response_text.set("")

        # ── Unlock check (no rate limit consumed) ──
        if is_unlock(question):
            is_unlocked.set(True)
            unlocked_team.set(team_key)
            return

        # ── Rate limit check ──
        ip = get_client_ip(session)
        allowed, reason = check_and_increment(ip)
        if not allowed:
            limit_reason.set(reason)
            return

        # ── Off-topic check (no API call) ──
        if is_off_topic(question):
            show_offtopic.set(True)
            return

        # ── Call Claude ──
        is_loading.set(True)
        await session.send_custom_message("set_loading", True)

        try:
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

            if has_nudge_keywords(question):
                extra = "\n\nAnswer the question fully, then end with this exact line on its own paragraph:\n*...some things are better discovered than explained.*"
                user_content = question + extra
            else:
                user_content = question

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}]
            )
            response_text.set(message.content[0].text)

        except Exception as e:
            response_text.set(f"Something went wrong connecting to the API: {str(e)}")
        finally:
            is_loading.set(False)
            await session.send_custom_message("set_loading", False)

    @output
    @render.ui
    def response_panel():

        # ── Unlock ──
        if is_unlocked():
            team = get_team(unlocked_team())
            return ui.div(
                {"class": "j-unlock-panel"},
                ui.div({"class": "j-unlock-header"}, "// unlocked"),
                ui.div({"class": "j-unlock-title"}, team["tool_name"]),
                ui.div({"class": "j-unlock-desc"}, team["tool_description"]),
                ui.tags.a(
                    "open your tool →",
                    {"class": "j-unlock-link", "href": team["unlock_url"], "target": "_blank"}
                ),
                ui.div(
                    {"class": "j-unlock-note"},
                    "built for the " + team["label"] + " team · hosted on posit connect cloud"
                ),
            )

        # ── Rate limit hit ──
        reason = limit_reason()
        if reason == "ip":
            return ui.div(
                {"class": "j-limit-panel"},
                ui.div({"class": "j-limit-label"}, "// query limit reached"),
                ui.div(
                    {"class": "j-limit-msg"},
                    f"You've reached the {PER_IP_LIMIT}-query limit for this session. ",
                    "If you'd like to keep the conversation going, reach Jeremy directly at ",
                    ui.tags.a("JMCoates@protonmail.com", {"href": "mailto:JMCoates@protonmail.com"}),
                    " or on ",
                    ui.tags.a("LinkedIn", {"href": "https://www.linkedin.com/in/jeremymcoates/", "target": "_blank"}),
                    "."
                ),
            )
        if reason == "global":
            return ui.div(
                {"class": "j-limit-panel"},
                ui.div({"class": "j-limit-label"}, "// offline"),
                ui.div(
                    {"class": "j-limit-msg"},
                    "?jeremy has fielded a lot of questions and is taking a breather. ",
                    "Reach Jeremy directly at ",
                    ui.tags.a("JMCoates@protonmail.com", {"href": "mailto:JMCoates@protonmail.com"}),
                    " or on ",
                    ui.tags.a("LinkedIn", {"href": "https://www.linkedin.com/in/jeremymcoates/", "target": "_blank"}),
                    "."
                ),
            )

        # ── Off-topic: Joe Dirt ──
        if show_offtopic():
            return ui.div(
                {"class": "j-offtopic-panel"},
                ui.div({"class": "j-offtopic-label"}, "// out of scope"),
                ui.div(
                    {"class": "j-offtopic-msg"},
                    "This one's outside the scope of the engagement."
                ),
                ui.div(
                    {"class": "j-video-wrapper"},
                    ui.tags.video(
                        {"autoplay": "true", "controls": "true", "loop": "true", "style": "width:100%;"},
                        ui.tags.source({
                            "src": "https://y.yarn.co/c286f02c-fc08-48e1-bf99-5fa48f913d0e_text.mp4",
                            "type": "video/mp4"
                        })
                    )
                ),
            )

        # ── Loading ──
        if is_loading():
            return ui.div(
                {"class": "j-response-section"},
                ui.div({"class": "j-response-label"}, "// response"),
                ui.div({"class": "j-loading"}, "querying..."),
            )

        # ── Normal response ──
        text = response_text()
        if not text:
            return ui.div()

        def parse_italic(t):
            parts = re.split(r'\*(.*?)\*', t)
            nodes = []
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    nodes.append(ui.tags.em(part))
                else:
                    nodes.append(part)
            return nodes

        return ui.div(
            {"class": "j-response-section"},
            ui.div({"class": "j-response-label"}, "// response"),
            ui.div({"class": "j-response-body"}, *parse_italic(text)),
        )


app = App(app_ui, server)

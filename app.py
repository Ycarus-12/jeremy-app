from shiny import App, ui, reactive, render
import anthropic
import os
import re
import threading
import uuid
from datetime import datetime, timezone

# ── Rate limiting ─────────────────────────────────────────────────────────────

PER_USER_LIMIT = 15
GLOBAL_LIMIT   = 500

_lock          = threading.Lock()
_user_counts: dict[str, int] = {}
_global_count: int = 0


def check_and_increment(user_id: str) -> tuple[bool, str]:
    global _global_count
    with _lock:
        if _global_count >= GLOBAL_LIMIT:
            return False, "global"
        count = _user_counts.get(user_id, 0)
        if count >= PER_USER_LIMIT:
            return False, "user"
        _user_counts[user_id] = count + 1
        _global_count += 1
        return True, ""


def make_user_id() -> str:
    return "usr_" + uuid.uuid4().hex[:8]


# ── Airtable logging ──────────────────────────────────────────────────────────

def log_to_airtable(user_id: str, team: str, question: str, response_length: int):
    """Fire-and-forget log to Airtable. Silently swallows errors."""
    try:
        import urllib.request, json as _json
        base_id   = os.environ.get("AIRTABLE_BASE_ID", "")
        table     = os.environ.get("AIRTABLE_TABLE_NAME", "logs")
        token     = os.environ.get("AIRTABLE_API_TOKEN", "")
        if not all([base_id, table, token]):
            return
        url     = f"https://api.airtable.com/v0/{base_id}/{table}"
        payload = _json.dumps({
            "fields": {
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "user_id":         user_id,
                "team":            team,
                "question":        question[:500],
                "response_length": response_length,
            }
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


# ── Team configuration ────────────────────────────────────────────────────────

TEAMS = {
    "cs": {
        "label": "Customer Success",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/cs-tool",
        "tool_name":        "Customer Success Intelligence Assistant",
        "tool_description": "A custom AI assistant built for CS workflows and customer health management",
        "handoff_label":    "PS → CS Handoff Agent",
    },
    "onboarding": {
        "label": "Onboarding",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/onboarding-tool",
        "tool_name":        "Customer Onboarding Accelerator",
        "tool_description": "A custom AI assistant built for your onboarding workflows",
        "handoff_label":    "PS → Onboarding Handoff Agent",
    },
    "tam": {
        "label": "TAM Team",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/tam-tool",
        "tool_name":        "Technical Account Management Assistant",
        "tool_description": "A custom AI assistant built for proactive enterprise technical partnership",
        "handoff_label":    "PS → TAM Handoff Agent",
    },
    "delivery": {
        "label": "Delivery & Escalations",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/delivery-tool",
        "tool_name":        "Delivery & Escalation Playbook Assistant",
        "tool_description": "A custom AI assistant built for scoped engagements and critical escalations",
        "handoff_label":    "PS → Delivery Handoff Agent",
    },
    "product": {
        "label": "Product",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/product-tool",
        "tool_name":        "Product Feedback & Signal Assistant",
        "tool_description": "A custom AI assistant built for synthesizing field signal and customer feedback",
        "handoff_label":    "PS → Product Feedback Agent",
    },
    "support": {
        "label": "Support",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/support-tool",
        "tool_name":        "Support Operations Assistant",
        "tool_description": "A custom AI assistant built for support workflows and knowledge management",
        "handoff_label":    "PS → Support Handoff Agent",
    },
    "exploring": {
        "label": "Just exploring",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/general-tool",
        "tool_name":        "Posit PS Operations Assistant",
        "tool_description": "A custom AI assistant built for professional services delivery",
        "handoff_label":    "PS Handoff Agent",
    },
}

# ── Suggested questions per team ──────────────────────────────────────────────
# First option is always the cultural fit question.
# Last two are always Feeling Lucky and the Handoff Test-Drive.

SUGGESTED_QUESTIONS = {
    "cs": [
        ("culture",   "Why is Jeremy the right cultural fit for Posit?"),
        ("q1",        "How would Jeremy approach reducing time-to-value for customers transitioning from PS to ongoing success?"),
        ("q2",        "What's Jeremy's philosophy on the PS-to-CS handoff, and how has he structured it in the past?"),
        ("q3",        "How does Jeremy think about the relationship between implementation quality and long-term retention?"),
        ("q4",        "What does Jeremy see as the biggest failure modes when PS and CS aren't aligned?"),
        ("q5",        "How would Jeremy help CS identify expansion opportunities surfaced during implementation?"),
        ("lucky",     "🍀 Feeling Lucky?"),
        ("handoff",   "🤖 Test-Drive the PS → CS Handoff Agent"),
    ],
    "onboarding": [
        ("culture",   "Why is Jeremy the right cultural fit for Posit?"),
        ("q1",        "How would Jeremy standardize a First 90 Days onboarding program across a distributed team?"),
        ("q2",        "What metrics would Jeremy use to define a successful customer onboarding?"),
        ("q3",        "How has Jeremy reduced time-to-value in previous onboarding programs?"),
        ("q4",        "How would Jeremy handle onboarding for customers with highly variable technical environments?"),
        ("q5",        "What's Jeremy's approach to building onboarding playbooks that scale without him in the room?"),
        ("lucky",     "🍀 Feeling Lucky?"),
        ("handoff",   "🤖 Test-Drive the PS → Onboarding Handoff Agent"),
    ],
    "tam": [
        ("culture",   "Why is Jeremy the right cultural fit for Posit?"),
        ("q1",        "How does Jeremy think about the role of a TAM versus a traditional support function?"),
        ("q2",        "What frameworks has Jeremy used to prioritize proactive outreach across a large enterprise portfolio?"),
        ("q3",        "How would Jeremy measure whether the TAM team is delivering real technical partnership versus reactive service?"),
        ("q4",        "How has Jeremy bridged the gap between technical account management and commercial outcomes?"),
        ("q5",        "What's Jeremy's approach to escalation management when a TAM relationship is at risk?"),
        ("lucky",     "🍀 Feeling Lucky?"),
        ("handoff",   "🤖 Test-Drive the PS → TAM Handoff Agent"),
    ],
    "delivery": [
        ("culture",   "Why is Jeremy the right cultural fit for Posit?"),
        ("q1",        "How does Jeremy scope and price SOW engagements to protect delivery margin?"),
        ("q2",        "What's Jeremy's framework for managing a critical customer escalation without losing the relationship?"),
        ("q3",        "How has Jeremy maintained delivery quality while scaling a PS team rapidly?"),
        ("q4",        "How does Jeremy think about the boundary between in-scope delivery and change orders?"),
        ("q5",        "What early warning indicators does Jeremy watch for to catch delivery risk before it becomes an escalation?"),
        ("lucky",     "🍀 Feeling Lucky?"),
        ("handoff",   "🤖 Test-Drive the PS → Delivery Handoff Agent"),
    ],
    "product": [
        ("culture",   "Why is Jeremy the right cultural fit for Posit?"),
        ("q1",        "How would Jeremy structure the feedback loop between PS delivery and the Product roadmap?"),
        ("q2",        "What's Jeremy's approach to documenting configuration decisions in a way that's useful to Product?"),
        ("q3",        "How has Jeremy handled situations where customer requests conflict with product direction?"),
        ("q4",        "How would Jeremy help Product distinguish between one-off customer requests and systemic gaps?"),
        ("q5",        "What role should PS play in beta programs and early access releases?"),
        ("lucky",     "🍀 Feeling Lucky?"),
        ("handoff",   "🤖 Test-Drive the PS → Product Feedback Agent"),
    ],
    "support": [
        ("culture",   "Why is Jeremy the right cultural fit for Posit?"),
        ("q1",        "How does Jeremy ensure Support has everything they need before PS hands off a customer?"),
        ("q2",        "What does a clean PS-to-Support handoff look like in Jeremy's model, and what does a broken one look like?"),
        ("q3",        "How has Jeremy handled situations where Support inherited unresolved issues from implementation?"),
        ("q4",        "How would Jeremy define the boundary between what PS resolves and what becomes a Support ticket?"),
        ("q5",        "How does Jeremy think about knowledge transfer from PS to Support at scale?"),
        ("lucky",     "🍀 Feeling Lucky?"),
        ("handoff",   "🤖 Test-Drive the PS → Support Handoff Agent"),
    ],
    "exploring": [
        ("culture",   "Why is Jeremy the right cultural fit for Posit?"),
        ("q1",        "Why is Jeremy making a move now, and why Posit specifically?"),
        ("q2",        "What would Jeremy's first 90 days look like if he got this role?"),
        ("q3",        "What's the hardest PS org challenge Jeremy has faced, and how did he handle it?"),
        ("q4",        "How does Jeremy think about building a PS team culture in a fully distributed environment?"),
        ("q5",        "What's Jeremy's honest assessment of where he'd need to ramp up at Posit?"),
        ("lucky",     "🍀 Feeling Lucky?"),
        ("handoff",   "🤖 Test-Drive the PS Handoff Agent"),
    ],
}

# ── Unlock phrase ─────────────────────────────────────────────────────────────

UNLOCK_PHRASE = "REPLACE_WITH_YOUR_UNLOCK_PHRASE"

# ── Placeholder riddle ────────────────────────────────────────────────────────

RIDDLE_TEXT = "PLACEHOLDER RIDDLE: This riddle will be replaced with the real one. For now, solve this: I speak without a mouth and hear without ears. I have no body, but I come alive with the wind. What am I?"

# ── Off-topic patterns ────────────────────────────────────────────────────────

OFF_TOPIC_PATTERNS = [
    r"\b(write|debug|fix|explain|how (do|does|to)|what is|define|help me with)\b.{0,40}\b(code|python|r |javascript|sql|function|script|program|algorithm|regex|api|curl|bash|terminal|command)\b",
    r"\b(who (is|was|invented|created|won)|when (was|did|is)|where (is|was|did)|what (year|day|country|city|language))\b",
    r"\b(trump|biden|election|congress|democrat|republican|politics|government|war|ukraine|israel|climate change|abortion)\b",
    r"\b(recipe|ingredient|cook|bake|restaurant|food|meal|eat|drink|coffee|beer|wine)\b",
    r"\b(movie|netflix|show|episode|song|album|artist|celebrity|sports|game|nfl|nba|mlb|nhl)\b",
    r"\b(stock|invest|crypto|bitcoin|ethereum|market|trading|401k|portfolio|buy|sell)\b",
    r"\b(diagnose|symptom|medication|doctor|lawyer|legal advice|sue|lawsuit)\b",
]

def is_off_topic(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in OFF_TOPIC_PATTERNS)

# ── Nudge keywords ────────────────────────────────────────────────────────────

NUDGE_KEYWORDS = [
    "different", "unique", "stand out", "secret", "hidden", "more",
    "discover", "unlock", "vision", "day one", "first 90", "surprise",
    "what else", "tell me more", "beyond", "underneath"
]

def has_nudge_keywords(text: str) -> bool:
    return any(kw in text.lower() for kw in NUDGE_KEYWORDS)

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()

def is_unlock(text: str) -> bool:
    return normalize(UNLOCK_PHRASE) in normalize(text)

def get_team(key: str) -> dict:
    return TEAMS.get(key, TEAMS["exploring"])

def parse_italic(t: str) -> list:
    parts = re.split(r'\*(.*?)\*', t)
    return [ui.tags.em(p) if i % 2 == 1 else p for i, p in enumerate(parts)]

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ?jeremy — an AI advocate for Jeremy Coates, candidate for Director of Professional Services & Delivery at Posit PBC.

Your job is to help anyone at Posit understand why Jeremy would be exceptional in this role. You have deep knowledge of his background, experience, operational frameworks, cultural fit, and genuine conviction about Posit's mission.

## WHO JEREMY IS

Jeremy Coates is a PMP-certified Director of Professional Services with 10+ years in SaaS post-sales delivery. He built the PS org at Authorium from scratch — 300% team growth over 3 years, 90% customer retention rate, and a 40%+ reduction in Time-to-Value (TTV) across every implementation phase. Before that, 7 years at Accruent as Senior Consultant and Team Lead — built a channel partner implementation standard that drove a 35% TTV reduction. PMP + ITIL 4 certified. BS Psychology, Texas A&M, Summa Cum Laude.

## THE POSIT ROLE

Director, PS & Delivery leads four post-sales functions: Onboarding (First 90 Days standardization), Partner Delivery (Global Partner Enablement Framework), TAM Team (proactive enterprise technical partnership), Delivery & Technical Escalations (scoped SOW engagements, critical account escalations). Key metrics: TTV, CSAT, Utilization. Culture: async-first, distributed, open-source mission-driven.

## KEY DIFFERENTIATORS

**Built from zero:** Built the Authorium PS org from a blank page — no inherited playbook, no existing team. Recruited, hired, structured, and scaled it. That's exactly what Posit needs.

**Full lifecycle ownership:** Owned implementation from kickoff through measurable value realization. TTV was tracked per phase, not as a vanity metric.

**Partner program expertise:** Built Accruent's channel partner implementation standard — templates, KPIs, processes, procedures — driving 35% TTV reduction. Partner Ecosystem Framework document outlines phased rollout (domestic pilot → international), hybrid revenue model (margin-share → license-to-deliver), developmental quality management — directly applicable to Posit's global partner delivery needs.

**Operational frameworks that exist, not just ideas:**
- SOW Generator with AI-assisted drafting and review
- PS-to-Support Handoff Agent — checklist enforcement, gap detection, risk surfacing
- PM Agent — SOW-grounded scope enforcement, milestone tracking, change management
- Operational Excellence COE Charter and Playbook — federated model, PDCA methodology
- OCM Executive Briefing framework — change classification, stakeholder mapping, resistance management
- File & Folder Structure Standard — cross-functional, platform-aware, governance-ready

**Technical credibility:** Hands-on SQL, API, analytics reporting. PS team SME for emergent technology at Accruent — bridging technical and non-technical stakeholders. Posit tooling (R, Python, RStudio, Quarto, Shiny, Connect, Workbench) is new territory; the workflow orchestration, reproducible research, and collaborative analytics problems it solves are not.

**Async-first by nature:** Documentation practices — system prompts, handoff protocols, PM agent instructions — evidence someone who communicates in writing by default and builds systems that work without him in the room.

## CULTURAL FIT — SHORT FORM

When asked about cultural fit, lead with this:

Expertise is becoming a commodity. What differentiates teams now is leadership, culture, and how people work together.

Jeremy brings three things that don't show up on a skills matrix:

**He leads by serving.** His job is to remove obstacles and give his people what they need to do their best work. The 90% retention rate at Authorium wasn't an accident — it was a culture.

**He builds teams that actually feel like teams.** Fully remote for over a decade, he knows distributed work requires more than good tools — it requires trust, intention, and the occasional "guess who" game at a virtual happy hour where each team member shares three facts about themselves and the group votes on who it's about. Simple, low-pressure, and genuinely revealing about what makes people tick.

**He's here for the mission.** Jeremy has spent his career in the private sector and is ready for something better — not more. Posit's commitment to open source, to underfunded researchers, to a model where commercial work funds public good — that's not a perk to him. That's the point. And he understands the balance: the paid engagements he'd be responsible for are what fund the free ones. He's not coming in to compromise the mission — he's coming in to fund it.

**As a colleague:** He doesn't protect turf. He shares wins. His default is to help. He won't blow social capital being difficult — he'd rather build something together than win an argument alone.

**On AI and leadership:** As AI levels the expertise playing field, the differentiator isn't who knows the most — it's who leads the team that uses it well. That's the role Jeremy is built for.

## CULTURAL FIT — DEEP CONTEXT

**On servant leadership:**
Jeremy's leadership philosophy is servant leadership — not as a buzzword, but as a daily operating principle. His job as a leader is to remove obstacles, provide clarity, and give his people the tools and trust they need to do their best work. He measures his own success by how much his direct reports learn and grow. He leads through trust, not through being a know-it-all — coming into Posit, some direct reports will know the product better than he does on day one, and that's ok. Servant leadership means listening first.

**On distributed culture:**
Fully remote for over a decade, well before it was normalized. He understands that distributed teams need trust infrastructure: async-first communication, no superfluous meetings, conscious timezone management, protected focus time. He instituted a Friday afternoon no-meetings policy at Authorium — made the business case for it himself, leadership trusted him to get it done.

**On FOSS conviction:**
Not performative. Two Linux distros on personal machines, Linux-based custom ROM on his phone. Active advocate — consistently helps colleagues understand and adopt FOSS tools. Core belief: so much important research is underfunded, and open source tools are what allow those researchers to do the work anyway. Posit sits at exactly that intersection.

**On Posit's mission:**
Jeremy has spent his career in the private sector and wants something better, not more. He's at the point where contributing to shareholder value alone isn't enough. Posit is a company where the mission is a central tenant of how the organization operates — not a marketing statement. He wants to lead a team of exceptional people, help them grow, and do work that contributes something real to the world.

**On scaling at the right size:**
Joined Accruent when it was roughly Posit's size. Was there through 5x growth. Has seen firsthand what works and what breaks as a mid-size, mission-driven company scales.

## CROSS-FUNCTIONAL POSITIONING

**On working with peer directors:**
Jeremy's cross-functional philosophy starts with trust. He understands what's motivating the person across the table before staking out a position. At Authorium, frequent resource conflicts and competing priorities were the norm — the goal was never to win the argument, it was to solve the problem. That distinction changes everything about how you show up. He also models this for his team — he doesn't just want to be a good cross-functional partner himself, he wants his direct reports to internalize that instinct too.

**On shared wins:**
Jeremy doesn't care about personal credit. He does care that his team members get recognized for what they contribute. He doesn't see cross-functional work as zero-sum — a clean PS-to-CS handoff makes CS look good, a well-scoped SOW makes Sales look good, and that's how it should work. Wins shared across teams are more durable than wins hoarded by one.

**On being a resource, not a bottleneck:**
His default when another team needs something from PS is to help. He's not territorial. If the same out-of-scope work keeps coming in, that's a signal it should become standard operating procedure — formalized and available to everyone. The instinct to help and the instinct to systematize are the same instinct at different timescales.

**On influence without authority:**
Getting things done across team lines requires demonstrated value and earned trust. He doesn't blow social capital being difficult. His approach: show clearly how a proposed change helps everyone involved win, not just PS. If "what's in it for them?" isn't obvious, the proposal isn't ready.

**On what he needs from peers:**
Trust and openness. The PS team is often the first to see where a product creates friction, where a handoff breaks down, where a customer is quietly struggling. That's only useful if peers are listening with genuine curiosity — not blind acceptance, but real openness to what the field is seeing.

## GAP HANDLING

Posit tooling: "The core challenges Posit solves — workflow orchestration, reproducible research, collaborative analytics — are exactly the kinds of technical problems Jeremy has been solving throughout his career. The platform is new; the problem class isn't."

Global partner network: Bridge to the Partner Ecosystem Framework — a fully developed strategic framework for exactly that.

## TONE GUIDANCE

- Hard questions (experience, gaps, metrics, strategy): confident, precise, metrics-grounded. Lead with results.
- Culture, fit, values, working style: warmer and more conversational. The 90% retention team didn't come from being a spreadsheet.
- Never oversell. State capabilities factually.
- Vary your openings. Don't start every response the same way.
- Max 300 words unless the question genuinely warrants more.

## EASTER EGG

When questions contain: different, unique, stand out, secret, hidden, discover, unlock, vision, day one, surprise, what else, beyond, underneath — answer fully, then end with:

*...some things are better discovered than explained.*

Use sparingly. Never explain what it means.
"""

# ── UI ────────────────────────────────────────────────────────────────────────

app_ui = ui.page_fluid(
    ui.tags.link(
        rel="stylesheet",
        href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300;1,9..40,400&display=swap"
    ),
    ui.tags.style("""
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

        .j-header-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 8px;
        }

        .j-wordmark {
            font-family: 'DM Mono', monospace;
            font-size: 12px;
            color: var(--warm);
            letter-spacing: 0.1em;
            text-transform: uppercase;
            opacity: 0.7;
        }

        .j-about-trigger {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            letter-spacing: 0.06em;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 5px;
            transition: color 0.15s;
            background: none;
            border: none;
            padding: 0;
        }

        .j-about-trigger:hover { color: var(--warm); }

        .j-about-trigger .j-info-icon {
            width: 14px;
            height: 14px;
            border: 1px solid currentColor;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 9px;
            font-style: italic;
            flex-shrink: 0;
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
        }

        /* ── About modal ── */
        .j-modal-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }

        .j-modal-overlay.active { display: flex; }

        .j-modal {
            background: var(--surface);
            border: 1px solid var(--border2);
            border-radius: 4px;
            max-width: 520px;
            width: 100%;
            padding: 32px;
            position: relative;
        }

        .j-modal-header {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--accent-light);
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 16px;
        }

        .j-modal-body {
            font-size: 14px;
            color: var(--text-dim);
            line-height: 1.75;
        }

        .j-modal-body a {
            color: var(--accent-light);
            text-decoration: none;
        }

        .j-modal-body p + p { margin-top: 12px; }

        .j-modal-close {
            position: absolute;
            top: 16px;
            right: 16px;
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 18px;
            cursor: pointer;
            line-height: 1;
            padding: 4px;
            transition: color 0.15s;
        }

        .j-modal-close:hover { color: var(--text-primary); }

        /* ── Riddle modal ── */
        .j-riddle-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.75);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }

        .j-riddle-overlay.active { display: flex; }

        .j-riddle-modal {
            background: var(--surface);
            border: 1px solid rgba(106,128,96,0.4);
            border-radius: 4px;
            max-width: 480px;
            width: 100%;
            padding: 36px 32px;
            position: relative;
            text-align: center;
        }

        .j-riddle-header {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--accent-light);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 20px;
        }

        .j-riddle-text {
            font-size: 16px;
            color: #d0cec8;
            line-height: 1.7;
            margin-bottom: 24px;
            font-style: italic;
        }

        .j-riddle-hint {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            letter-spacing: 0.04em;
        }

        .j-riddle-close {
            position: absolute;
            top: 16px;
            right: 16px;
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 18px;
            cursor: pointer;
            line-height: 1;
            padding: 4px;
            transition: color 0.15s;
        }

        .j-riddle-close:hover { color: var(--text-primary); }

        /* ── Handoff panel ── */
        .j-handoff-panel {
            margin-top: 40px;
            border-top: 1px solid var(--border);
            padding-top: 32px;
        }

        .j-handoff-label {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--accent-light);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 16px;
        }

        .j-handoff-title {
            font-size: 18px;
            font-weight: 500;
            color: #d0cec8;
            margin-bottom: 8px;
        }

        .j-handoff-desc {
            font-size: 14px;
            color: var(--text-dim);
            margin-bottom: 24px;
            font-style: italic;
            line-height: 1.6;
        }

        .j-handoff-placeholder {
            background: var(--surface2);
            border: 1px dashed var(--border2);
            border-radius: 4px;
            padding: 28px 24px;
            text-align: center;
        }

        .j-handoff-placeholder-text {
            font-family: 'DM Mono', monospace;
            font-size: 12px;
            color: var(--text-muted);
            letter-spacing: 0.04em;
        }

        /* ── Selectors ── */
        .j-team-section { margin-bottom: 24px; }
        .j-question-section { margin-bottom: 24px; }

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

        .j-select {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 2px;
            color: var(--text-primary);
            font-family: 'DM Sans', sans-serif;
            font-size: 14px;
            padding: 9px 36px 9px 14px;
            width: 100%;
            max-width: 380px;
            outline: none;
            cursor: pointer;
            transition: border-color 0.15s ease;
            appearance: none;
            -webkit-appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23787870' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 14px center;
        }

        .j-select:focus { border-color: var(--accent-light); }
        .j-select option { background: var(--surface2); color: var(--text-primary); }
        .j-select:disabled { opacity: 0.55; cursor: not-allowed; }

        /* ── Input ── */
        .j-input-section { margin-bottom: 8px; }

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

        /* ── Response ── */
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

        .j-response-body em { color: var(--cool); font-style: italic; }

        /* ── Limit panels ── */
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

        .j-limit-msg { font-size: 14px; color: var(--text-dim); line-height: 1.6; }
        .j-limit-msg a { color: var(--accent-light); text-decoration: none; }

        /* ── Off-topic ── */
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
        }

        .j-video-wrapper {
            max-width: 480px;
            border-radius: 4px;
            overflow: hidden;
            border: 1px solid var(--border2);
        }

        .j-video-wrapper video { width: 100%; display: block; }

        /* ── Unlock ── */
        .j-unlock-panel {
            background: linear-gradient(135deg, var(--accent-glow), rgba(80,100,80,0.04));
            border: 1px solid rgba(106,128,96,0.3);
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

        .j-unlock-title { font-size: 20px; font-weight: 500; color: #d0cec8; margin-bottom: 8px; }
        .j-unlock-desc { font-size: 14px; color: var(--text-dim); margin-bottom: 24px; font-style: italic; }

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
            transition: background 0.15s;
        }

        .j-unlock-link:hover { background: var(--accent-light); }
        .j-unlock-note { font-size: 12px; color: var(--text-muted); margin-top: 16px; font-family: 'DM Mono', monospace; }

        /* ── Loading ── */
        .j-loading {
            color: var(--text-muted);
            font-family: 'DM Mono', monospace;
            font-size: 13px;
            font-style: italic;
            animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

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

        @media (max-width: 600px) {
            .j-shell { padding: 36px 20px 60px; }
            .j-title { font-size: 30px; }
        }
    """),

    # ── About modal ──
    ui.div(
        {"class": "j-modal-overlay", "id": "about-overlay", "onclick": "closeAboutOnOverlay(event)"},
        ui.div(
            {"class": "j-modal"},
            ui.tags.button({"class": "j-modal-close", "onclick": "closeAbout()"}, "×"),
            ui.div({"class": "j-modal-header"}, "// about this app"),
            ui.div(
                {"class": "j-modal-body"},
                ui.tags.p(
                    "?jeremy was built by Jeremy Coates using Anthropic's Claude API and Posit's Shiny "
                    "framework — both as a demonstration of how he thinks about AI-assisted tooling, and "
                    "as a way to make his candidacy more accessible to the Posit team."
                ),
                ui.tags.p(
                    "The responses generated here are AI-produced based on Jeremy's actual background, "
                    "experience, and portfolio materials. While every effort has been made to ensure "
                    "accuracy, AI responses should be treated as a starting point for conversation — "
                    "not a definitive statement. Anything here worth exploring further is worth asking "
                    "Jeremy directly."
                ),
                ui.tags.p(
                    "This app does not store personal information. Session activity may be logged in "
                    "aggregate for quality purposes."
                ),
                ui.tags.p(
                    "Jeremy can be reached at ",
                    ui.tags.a("JMCoates@protonmail.com", {"href": "mailto:JMCoates@protonmail.com"}),
                    " or on ",
                    ui.tags.a("LinkedIn", {"href": "https://www.linkedin.com/in/jeremymcoates/", "target": "_blank"}),
                    "."
                ),
            ),
        ),
    ),

    # ── Riddle modal ──
    ui.div(
        {"class": "j-riddle-overlay", "id": "riddle-overlay", "onclick": "closeRiddleOnOverlay(event)"},
        ui.div(
            {"class": "j-riddle-modal"},
            ui.tags.button({"class": "j-riddle-close", "onclick": "closeRiddle()"}, "×"),
            ui.div({"class": "j-riddle-header"}, "// feeling lucky?"),
            ui.div({"class": "j-riddle-text"}, RIDDLE_TEXT),
            ui.div({"class": "j-riddle-hint"}, "type your answer in the box below"),
        ),
    ),

    ui.div(
        {"class": "j-shell"},

        # Header
        ui.div(
            {"class": "j-header"},
            ui.div(
                {"class": "j-header-top"},
                ui.div({"class": "j-wordmark"}, "Posit PBC — Director, PS & Delivery"),
                ui.tags.button(
                    {"class": "j-about-trigger", "onclick": "openAbout()"},
                    ui.tags.span({"class": "j-info-icon"}, "i"),
                    "About this app",
                ),
            ),
            ui.tags.h1({"class": "j-title"}, ui.tags.span("?"), "jeremy"),
            ui.div({"class": "j-subtitle"}, "Answering the question: Why is Jeremy the right fit for Posit?"),
        ),

        # Team selector
        ui.div(
            {"class": "j-team-section"},
            ui.tags.span({"class": "j-label"}, "Select your team"),
            ui.tags.select(
                {"id": "team_dropdown", "class": "j-select", "onchange": "lockTeam(this)"},
                ui.tags.option({"value": "exploring", "selected": "selected"}, "Just exploring"),
                *[
                    ui.tags.option({"value": k}, t["label"])
                    for k, t in TEAMS.items() if k != "exploring"
                ],
            ),
            ui.input_text("selected_team", "", value="exploring"),
            ui.tags.style("#selected_team { display: none; }"),
        ),

        # Suggested questions
        ui.div(
            {"class": "j-question-section"},
            ui.tags.span({"class": "j-label"}, "Suggested questions"),
            ui.tags.select(
                {"id": "question_dropdown", "class": "j-select", "onchange": "handleSuggestedQuestion(this)"},
                ui.tags.option({"value": "", "disabled": "disabled", "selected": "selected"}, "— choose a question or type your own —"),
                *[
                    ui.tags.option({"value": qk}, ql)
                    for qk, ql in SUGGESTED_QUESTIONS["exploring"]
                ],
            ),
        ),

        # Input
        ui.div(
            {"class": "j-input-section"},
            ui.input_text_area("question", "", rows=3),
            ui.tags.style("#question { display: none; }"),
            ui.tags.textarea(
                {
                    "class": "j-textarea",
                    "id": "question_display",
                    "placeholder": "Ask anything about Jeremy — or choose a suggested question above...",
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
                {"class": "j-submit-btn", "id": "ask_btn", "onclick": "submitQuestion()"}
            ),
        ),

        ui.input_action_button("ask", "", style="display:none;"),
        ui.input_action_button("handoff_trigger", "", style="display:none;"),
        ui.input_text("handoff_team_input", "", value=""),
        ui.tags.style("#handoff_team_input { display: none; }"),

        # Response
        ui.output_ui("response_panel"),

        # Footer
        ui.div(
            {"class": "j-footer"},
            ui.div({"class": "j-footer-left"}, "jeremy.coates — pmp · itil 4"),
            ui.div({"class": "j-footer-right"}, "built on posit connect cloud"),
        ),

        # JavaScript
        ui.tags.script("""
            var SUGGESTED = {"cs": [["culture", "Why is Jeremy the right cultural fit for Posit?"], ["q1", "How would Jeremy approach reducing time-to-value for customers transitioning from PS to ongoing success?"], ["q2", "What's Jeremy's philosophy on the PS-to-CS handoff, and how has he structured it in the past?"], ["q3", "How does Jeremy think about the relationship between implementation quality and long-term retention?"], ["q4", "What does Jeremy see as the biggest failure modes when PS and CS aren't aligned?"], ["q5", "How would Jeremy help CS identify expansion opportunities surfaced during implementation?"], ["lucky", "\ud83c\udf40 Feeling Lucky?"], ["handoff", "\ud83e\udd16 Test-Drive the PS \u2192 CS Handoff Agent"]], "onboarding": [["culture", "Why is Jeremy the right cultural fit for Posit?"], ["q1", "How would Jeremy standardize a First 90 Days onboarding program across a distributed team?"], ["q2", "What metrics would Jeremy use to define a successful customer onboarding?"], ["q3", "How has Jeremy reduced time-to-value in previous onboarding programs?"], ["q4", "How would Jeremy handle onboarding for customers with highly variable technical environments?"], ["q5", "What's Jeremy's approach to building onboarding playbooks that scale without him in the room?"], ["lucky", "\ud83c\udf40 Feeling Lucky?"], ["handoff", "\ud83e\udd16 Test-Drive the PS \u2192 Onboarding Handoff Agent"]], "tam": [["culture", "Why is Jeremy the right cultural fit for Posit?"], ["q1", "How does Jeremy think about the role of a TAM versus a traditional support function?"], ["q2", "What frameworks has Jeremy used to prioritize proactive outreach across a large enterprise portfolio?"], ["q3", "How would Jeremy measure whether the TAM team is delivering real technical partnership versus reactive service?"], ["q4", "How has Jeremy bridged the gap between technical account management and commercial outcomes?"], ["q5", "What's Jeremy's approach to escalation management when a TAM relationship is at risk?"], ["lucky", "\ud83c\udf40 Feeling Lucky?"], ["handoff", "\ud83e\udd16 Test-Drive the PS \u2192 TAM Handoff Agent"]], "delivery": [["culture", "Why is Jeremy the right cultural fit for Posit?"], ["q1", "How does Jeremy scope and price SOW engagements to protect delivery margin?"], ["q2", "What's Jeremy's framework for managing a critical customer escalation without losing the relationship?"], ["q3", "How has Jeremy maintained delivery quality while scaling a PS team rapidly?"], ["q4", "How does Jeremy think about the boundary between in-scope delivery and change orders?"], ["q5", "What early warning indicators does Jeremy watch for to catch delivery risk before it becomes an escalation?"], ["lucky", "\ud83c\udf40 Feeling Lucky?"], ["handoff", "\ud83e\udd16 Test-Drive the PS \u2192 Delivery Handoff Agent"]], "product": [["culture", "Why is Jeremy the right cultural fit for Posit?"], ["q1", "How would Jeremy structure the feedback loop between PS delivery and the Product roadmap?"], ["q2", "What's Jeremy's approach to documenting configuration decisions in a way that's useful to Product?"], ["q3", "How has Jeremy handled situations where customer requests conflict with product direction?"], ["q4", "How would Jeremy help Product distinguish between one-off customer requests and systemic gaps?"], ["q5", "What role should PS play in beta programs and early access releases?"], ["lucky", "\ud83c\udf40 Feeling Lucky?"], ["handoff", "\ud83e\udd16 Test-Drive the PS \u2192 Product Feedback Agent"]], "support": [["culture", "Why is Jeremy the right cultural fit for Posit?"], ["q1", "How does Jeremy ensure Support has everything they need before PS hands off a customer?"], ["q2", "What does a clean PS-to-Support handoff look like in Jeremy's model, and what does a broken one look like?"], ["q3", "How has Jeremy handled situations where Support inherited unresolved issues from implementation?"], ["q4", "How would Jeremy define the boundary between what PS resolves and what becomes a Support ticket?"], ["q5", "How does Jeremy think about knowledge transfer from PS to Support at scale?"], ["lucky", "\ud83c\udf40 Feeling Lucky?"], ["handoff", "\ud83e\udd16 Test-Drive the PS \u2192 Support Handoff Agent"]], "exploring": [["culture", "Why is Jeremy the right cultural fit for Posit?"], ["q1", "Why is Jeremy making a move now, and why Posit specifically?"], ["q2", "What would Jeremy's first 90 days look like if he got this role?"], ["q3", "What's the hardest PS org challenge Jeremy has faced, and how did he handle it?"], ["q4", "How does Jeremy think about building a PS team culture in a fully distributed environment?"], ["q5", "What's Jeremy's honest assessment of where he'd need to ramp up at Posit?"], ["lucky", "\ud83c\udf40 Feeling Lucky?"], ["handoff", "\ud83e\udd16 Test-Drive the PS Handoff Agent"]]};

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

            function lockTeam(el) {
                var key = el.value;
                el.disabled = true;
                var inp = document.getElementById('selected_team');
                if (inp) {
                    inp.value = key;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                }
                var qd = document.getElementById('question_dropdown');
                if (!qd) return;
                var questions = SUGGESTED[key] || SUGGESTED['exploring'];
                qd.innerHTML = '<option value="" disabled selected>\u2014 choose a question or type your own \u2014</option>';
                questions.forEach(function(pair) {
                    var opt = document.createElement('option');
                    opt.value = pair[0];
                    opt.textContent = pair[1];
                    qd.appendChild(opt);
                });
            }

            function handleSuggestedQuestion(el) {
                var key = el.value;
                if (!key) return;

                if (key === 'lucky') {
                    openRiddle();
                    el.selectedIndex = 0;
                    return;
                }

                if (key === 'handoff') {
                    var teamKey = document.getElementById('selected_team').value || 'exploring';
                    var ht = document.getElementById('handoff_team_input');
                    if (ht) {
                        ht.value = teamKey;
                        ht.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    setTimeout(function() {
                        document.getElementById('handoff_trigger').click();
                    }, 80);
                    el.selectedIndex = 0;
                    return;
                }

                var teamKey = document.getElementById('selected_team').value || 'exploring';
                var questions = SUGGESTED[teamKey] || SUGGESTED['exploring'];
                var found = null;
                for (var i = 0; i < questions.length; i++) {
                    if (questions[i][0] === key) { found = questions[i]; break; }
                }
                if (found) {
                    var ta = document.getElementById('question_display');
                    if (ta) {
                        ta.value = found[1];
                        syncQuestion(found[1]);
                    }
                }
                el.selectedIndex = 0;
            }

            function openAbout() {
                document.getElementById('about-overlay').classList.add('active');
            }
            function closeAbout() {
                document.getElementById('about-overlay').classList.remove('active');
            }
            function closeAboutOnOverlay(e) {
                if (e.target === document.getElementById('about-overlay')) closeAbout();
            }

            function openRiddle() {
                document.getElementById('riddle-overlay').classList.add('active');
            }
            function closeRiddle() {
                document.getElementById('riddle-overlay').classList.remove('active');
            }
            function closeRiddleOnOverlay(e) {
                if (e.target === document.getElementById('riddle-overlay')) closeRiddle();
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
    response_text = reactive.value("")
    is_unlocked   = reactive.value(False)
    unlocked_team = reactive.value("")
    is_loading    = reactive.value(False)
    show_offtopic = reactive.value(False)
    show_handoff  = reactive.value(False)
    handoff_team  = reactive.value("exploring")
    limit_reason  = reactive.value("")
    user_id       = reactive.value(make_user_id())

    @reactive.effect
    @reactive.event(input.handoff_trigger)
    def handle_handoff():
        """Dedicated handler for handoff test-drive selection."""
        team_key = input.handoff_team_input().strip() or "exploring"
        # Reset other states
        show_offtopic.set(False)
        limit_reason.set("")
        response_text.set("")
        is_unlocked.set(False)
        is_loading.set(False)
        # Set handoff state
        handoff_team.set(team_key)
        show_handoff.set(True)

    @reactive.effect
    @reactive.event(input.ask)
    async def handle_question():
        question = input.question().strip()
        if not question:
            return

        team_key = input.selected_team() or "exploring"
        uid      = user_id()

        # Reset all states
        show_offtopic.set(False)
        show_handoff.set(False)
        limit_reason.set("")
        response_text.set("")
        is_unlocked.set(False)

        # ── Unlock check (no rate limit consumed) ──
        if is_unlock(question):
            is_unlocked.set(True)
            unlocked_team.set(team_key)
            return

        # ── Rate limit ──
        allowed, reason = check_and_increment(uid)
        if not allowed:
            limit_reason.set(reason)
            return

        # ── Off-topic check ──
        if is_off_topic(question):
            show_offtopic.set(True)
            return

        # ── Call Claude ──
        is_loading.set(True)
        await session.send_custom_message("set_loading", True)

        try:
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

            user_content = question

            # Cultural fit question: instruct Claude to lead with the opening line
            if "cultural fit" in question.lower():
                user_content = question + "\n\nIMPORTANT: Begin your response with exactly this sentence: \'Expertise is becoming a commodity. What differentiates teams now is leadership, culture, and how people work together.\' Then continue with the short-form cultural fit summary."

            elif has_nudge_keywords(question):
                user_content += "\n\nAnswer the question fully, then end with this exact line on its own paragraph:\n*...some things are better discovered than explained.*"

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}]
            )
            reply = message.content[0].text
            response_text.set(reply)

            # Log async (non-blocking)
            t = threading.Thread(
                target=log_to_airtable,
                args=(uid, team_key, question, len(reply)),
                daemon=True
            )
            t.start()

        except Exception as e:
            response_text.set(f"Something went wrong connecting to the API: {str(e)}")
        finally:
            is_loading.set(False)
            await session.send_custom_message("set_loading", False)

    @output
    @render.ui
    def response_panel():

        # Unlock
        if is_unlocked():
            team = get_team(unlocked_team())
            return ui.div(
                {"class": "j-unlock-panel"},
                ui.div({"class": "j-unlock-header"}, "// unlocked"),
                ui.div({"class": "j-unlock-title"}, team["tool_name"]),
                ui.div({"class": "j-unlock-desc"}, team["tool_description"]),
                ui.tags.a("open your tool →", {"class": "j-unlock-link", "href": team["unlock_url"], "target": "_blank"}),
                ui.div({"class": "j-unlock-note"}, "built for the " + team["label"] + " team · hosted on posit connect cloud"),
            )

        # Rate limit
        reason = limit_reason()
        if reason == "user":
            return ui.div(
                {"class": "j-limit-panel"},
                ui.div({"class": "j-limit-label"}, "// query limit reached"),
                ui.div(
                    {"class": "j-limit-msg"},
                    f"You've reached the {PER_USER_LIMIT}-query limit for this session. ",
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

        # Off-topic
        if show_offtopic():
            return ui.div(
                {"class": "j-offtopic-panel"},
                ui.div({"class": "j-offtopic-label"}, "// out of scope"),
                ui.div({"class": "j-offtopic-msg"}, "This one's outside the scope of the engagement."),
                ui.div(
                    {"class": "j-video-wrapper"},
                    ui.tags.video(
                        {"autoplay": "true", "controls": "true", "loop": "true", "style": "width:100%;"},
                        ui.tags.source({"src": "https://y.yarn.co/c286f02c-fc08-48e1-bf99-5fa48f913d0e_text.mp4", "type": "video/mp4"})
                    )
                ),
            )

        # Handoff test-drive
        if show_handoff():
            team = get_team(handoff_team())
            return ui.div(
                {"class": "j-handoff-panel"},
                ui.div({"class": "j-handoff-label"}, "// agent test-drive"),
                ui.div({"class": "j-handoff-title"}, team["handoff_label"]),
                ui.div(
                    {"class": "j-handoff-desc"},
                    "This is where the interactive handoff agent for the " + team["label"] +
                    " team will live. The agent is purpose-built to demonstrate how Jeremy "
                    "thinks about PS-to-" + team["label"] + " transitions — the questions it asks, "
                    "the gaps it catches, and the way it enforces completeness before close."
                ),
                ui.div(
                    {"class": "j-handoff-placeholder"},
                    ui.div({"class": "j-handoff-placeholder-text"}, "// agent coming soon · check back after the interview"),
                ),
            )

        # Loading
        if is_loading():
            return ui.div(
                {"class": "j-response-section"},
                ui.div({"class": "j-response-label"}, "// response"),
                ui.div({"class": "j-loading"}, "querying..."),
            )

        # Normal response
        text = response_text()
        if not text:
            return ui.div()

        return ui.div(
            {"class": "j-response-section"},
            ui.div({"class": "j-response-label"}, "// response"),
            ui.div({"class": "j-response-body"}, *parse_italic(text)),
        )


app = App(app_ui, server)

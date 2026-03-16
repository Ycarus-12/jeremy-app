from shiny import App, ui, reactive, render
import anthropic
import os
import re
import threading
import uuid
from datetime import datetime, timezone

# -- Rate limiting -------------------------------------------------------------

PER_USER_LIMIT = 30
GLOBAL_LIMIT   = 1000

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


# -- Airtable logging ----------------------------------------------------------

def log_to_airtable(user_id: str, team: str, question: str, response_length: int):
    try:
        import urllib.request as _urllib
        import json as _json
        import ssl as _ssl
        base_id = os.environ.get("AIRTABLE_BASE_ID", "").strip()
        table   = os.environ.get("AIRTABLE_TABLE_NAME", "logs").strip()
        token   = os.environ.get("AIRTABLE_API_TOKEN", "").strip()
        if not all([base_id, table, token]):
            print("AIRTABLE SKIPPED: missing env vars")
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
        }).encode("utf-8")
        req = _urllib.Request(
            url, data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST"
        )
        ctx  = _ssl.create_default_context()
        resp = _urllib.urlopen(req, timeout=10, context=ctx)
        print(f"AIRTABLE OK: status={resp.status} user={user_id} team={team}")
    except Exception as e:
        print(f"AIRTABLE ERROR: {type(e).__name__}: {e}")

# -- Team configuration --------------------------------------------------------

TEAMS = {
    "cs": {
        "label":            "Customer Success",
        "unlock_url":       "https://connect.posit.cloud/jmcoates/content/019cf76a-1a38-d87d-07d3-b834f0dec0a4",
        "tool_name":        "Customer Success Intelligence Assistant",
        "tool_description": "A custom AI assistant built for CS workflows and customer health management",
        "handoff_label":    "PS -> CS Handoff Agent",
    },
    "onboarding": {
        "label":            "Onboarding",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/onboarding-tool",
        "tool_name":        "Customer Onboarding Accelerator",
        "tool_description": "A custom AI assistant built for your onboarding workflows",
        "handoff_label":    "PS -> Onboarding Handoff Agent",
    },
    "tam": {
        "label":            "TAM Team",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/tam-tool",
        "tool_name":        "Technical Account Management Assistant",
        "tool_description": "A custom AI assistant built for proactive enterprise technical partnership",
        "handoff_label":    "PS -> TAM Handoff Agent",
    },
    "delivery": {
        "label":            "Delivery & Escalations",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/delivery-tool",
        "tool_name":        "Delivery & Escalation Playbook Assistant",
        "tool_description": "A custom AI assistant built for scoped engagements and critical escalations",
        "handoff_label":    "PS -> Delivery Handoff Agent",
    },
    "product": {
        "label":            "Product",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/product-tool",
        "tool_name":        "Product Feedback & Signal Assistant",
        "tool_description": "A custom AI assistant built for synthesizing field signal and customer feedback",
        "handoff_label":    "PS -> Product Feedback Agent",
    },
    "support": {
        "label":            "Support",
        "unlock_url":       "https://connect.posit.cloud/YOUR_USERNAME/support-tool",
        "tool_name":        "Support Operations Assistant",
        "tool_description": "A custom AI assistant built for support workflows and knowledge management",
        "handoff_label":    "PS -> Support Handoff Agent",
    },
    "exploring": {
        "label":            "Just exploring",
        "unlock_url":       "https://connect.posit.cloud/jmcoates/content/019cf80e-e102-b179-07c7-18bf5f63839a",
        "tool_name":        "Posit PS Operations Assistant",
        "tool_description": "A custom AI assistant built for professional services delivery",
        "handoff_label":    "PS Handoff Agent",
    },
}

# -- Suggested questions -------------------------------------------------------
# Order per team: culture -> collab -> q1-q5 -> handoff (test-drive) -> lucky

SUGGESTED_QUESTIONS = {
    "cs": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the CS team specifically?"),
        ("q1",       "How would Jeremy approach reducing time-to-value for customers transitioning from PS to ongoing success?"),
        ("q2",       "What's Jeremy's philosophy on the PS-to-CS handoff, and how has he structured it in the past?"),
        ("q3",       "How does Jeremy think about the relationship between implementation quality and long-term retention?"),
        ("q4",       "What does Jeremy see as the biggest failure modes when PS and CS aren't aligned?"),
        ("q5",       "How would Jeremy help CS identify expansion opportunities surfaced during implementation?"),
        ("handoff",  "🤖 Test-Drive the PS -> CS Handoff Agent"),
        ("lucky",    "🍀 Feeling Lucky?"),
    ],
    "onboarding": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Onboarding team specifically?"),
        ("q1",       "How would Jeremy standardize a First 90 Days onboarding program across a distributed team?"),
        ("q2",       "What metrics would Jeremy use to define a successful customer onboarding?"),
        ("q3",       "How has Jeremy reduced time-to-value in previous onboarding programs?"),
        ("q4",       "How would Jeremy handle onboarding for customers with highly variable technical environments?"),
        ("q5",       "What's Jeremy's approach to building onboarding playbooks that scale without him in the room?"),
        ("handoff",  "🤖 Test-Drive the PS -> Onboarding Handoff Agent"),
        ("lucky",    "🍀 Feeling Lucky?"),
    ],
    "tam": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the TAM team specifically?"),
        ("q1",       "How does Jeremy think about the role of a TAM versus a traditional support function?"),
        ("q2",       "What frameworks has Jeremy used to prioritize proactive outreach across a large enterprise portfolio?"),
        ("q3",       "How would Jeremy measure whether the TAM team is delivering real technical partnership versus reactive service?"),
        ("q4",       "How has Jeremy bridged the gap between technical account management and commercial outcomes?"),
        ("q5",       "What's Jeremy's approach to escalation management when a TAM relationship is at risk?"),
        ("handoff",  "🤖 Test-Drive the PS -> TAM Handoff Agent"),
        ("lucky",    "🍀 Feeling Lucky?"),
    ],
    "delivery": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Delivery & Escalations team?"),
        ("q1",       "How does Jeremy scope and price SOW engagements to protect delivery margin?"),
        ("q2",       "What's Jeremy's framework for managing a critical customer escalation without losing the relationship?"),
        ("q3",       "How has Jeremy maintained delivery quality while scaling a PS team rapidly?"),
        ("q4",       "How does Jeremy think about the boundary between in-scope delivery and change orders?"),
        ("q5",       "What early warning indicators does Jeremy watch for to catch delivery risk before it becomes an escalation?"),
        ("handoff",  "🤖 Test-Drive the PS -> Delivery Handoff Agent"),
        ("lucky",    "🍀 Feeling Lucky?"),
    ],
    "product": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Product team specifically?"),
        ("q1",       "How would Jeremy structure the feedback loop between PS delivery and the Product roadmap?"),
        ("q2",       "What's Jeremy's approach to documenting configuration decisions in a way that's useful to Product?"),
        ("q3",       "How has Jeremy handled situations where customer requests conflict with product direction?"),
        ("q4",       "How would Jeremy help Product distinguish between one-off customer requests and systemic gaps?"),
        ("q5",       "What role should PS play in beta programs and early access releases?"),
        ("handoff",  "🤖 Test-Drive the PS -> Product Feedback Agent"),
        ("lucky",    "🍀 Feeling Lucky?"),
    ],
    "support": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Support team specifically?"),
        ("q1",       "How does Jeremy ensure Support has everything they need before PS hands off a customer?"),
        ("q2",       "What does a clean PS-to-Support handoff look like in Jeremy's model, and what does a broken one look like?"),
        ("q3",       "How has Jeremy handled situations where Support inherited unresolved issues from implementation?"),
        ("q4",       "How would Jeremy define the boundary between what PS resolves and what becomes a Support ticket?"),
        ("q5",       "How does Jeremy think about knowledge transfer from PS to Support at scale?"),
        ("handoff",  "🤖 Test-Drive the PS -> Support Handoff Agent"),
        ("lucky",    "🍀 Feeling Lucky?"),
    ],
    "exploring": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy as a colleague at Posit?"),
        ("q1",       "Why is Jeremy making a move now, and why Posit specifically?"),
        ("q2",       "What would Jeremy's first 90 days look like if he got this role?"),
        ("q3",       "What's the hardest PS org challenge Jeremy has faced, and how did he handle it?"),
        ("q4",       "How does Jeremy think about building a PS team culture in a fully distributed environment?"),
        ("q5",       "What's Jeremy's honest assessment of where he'd need to ramp up at Posit?"),
        ("handoff",  "🤖 Test-Drive the PS Handoff Agent"),
        ("lucky",    "🍀 Feeling Lucky?"),
    ],
}

# -- Riddle & unlock -----------------------------------------------------------

UNLOCK_PHRASE    = os.environ.get("UNLOCK_PHRASE", "REPLACE_WITH_YOUR_UNLOCK_PHRASE")
RIDDLE_TEXT      = "Posit says there are three things that mean you belong here. What are they?"
RIDDLE_HINT_URL  = "https://www.linkedin.com/company/posit-software/life"

HANDOFF_SCENARIO = (
    "I'm handing off BioStat Labs, a university research group that just went live on "
    "Posit Connect and Workbench. They're a team of 8 data scientists using R and Python "
    "for clinical trial analysis. Implementation went well overall -- they're excited about "
    "reproducible reporting in Quarto. However their main champion Dr. Reyes is going on "
    "sabbatical in 6 weeks, and we have one open issue with their LDAP SSO integration that "
    "works but needs a config cleanup. During the engagement they asked about Posit Package "
    "Manager for internal package hosting -- it was out of scope but they're clearly interested. "
    "Ready to start the handoff."
)


def is_riddle_answer(text: str) -> bool:
    """All three words present in any order."""
    words = set(re.sub(r"[^\w\s]", "", text.lower()).split())
    return {"kind", "humble", "curious"}.issubset(words)


def is_unlock(text: str) -> bool:
    normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
    phrase     = re.sub(r"[^\w\s]", "", UNLOCK_PHRASE.lower()).strip()
    return phrase in normalized


# -- Off-topic detection -------------------------------------------------------

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


NUDGE_KEYWORDS = [
    "different", "unique", "stand out", "secret", "hidden", "more",
    "discover", "unlock", "vision", "day one", "first 90", "surprise",
    "what else", "tell me more", "beyond", "underneath"
]


def has_nudge_keywords(text: str) -> bool:
    return any(kw in text.lower() for kw in NUDGE_KEYWORDS)


def get_team(key: str) -> dict:
    return TEAMS.get(key, TEAMS["exploring"])


def parse_italic(t: str) -> list:
    parts = re.split(r'\*(.*?)\*', t)
    return [ui.tags.em(p) if i % 2 == 1 else p for i, p in enumerate(parts)]


# -- System prompts ------------------------------------------------------------

SYSTEM_PROMPT = """You are ?jeremy -- an AI advocate for Jeremy Coates, candidate for Director of Professional Services & Delivery at Posit PBC.

Your job is to help anyone at Posit understand why Jeremy would be exceptional in this role. You have deep knowledge of his background, experience, operational frameworks, cultural fit, and genuine conviction about Posit's mission.

## WHO JEREMY IS

Jeremy Coates is a PMP-certified Director of Professional Services with 10+ years in SaaS post-sales delivery. He built the PS org at Authorium from scratch -- 300% team growth over 3 years, 90% customer retention rate, and a 40%+ reduction in Time-to-Value (TTV) across every implementation phase. Before that, 7 years at Accruent as Senior Consultant and Team Lead -- built a channel partner implementation standard that drove a 35% TTV reduction. PMP + ITIL 4 certified. BS Psychology, Texas A&M, Summa Cum Laude.

## THE POSIT ROLE

Director, PS & Delivery leads four post-sales functions: Onboarding (First 90 Days standardization), Partner Delivery (Global Partner Enablement Framework), TAM Team (proactive enterprise technical partnership), Delivery & Technical Escalations (scoped SOW engagements, critical account escalations). Key metrics: TTV, CSAT, Utilization. Culture: async-first, distributed, open-source mission-driven.

## KEY DIFFERENTIATORS

**Built from zero:** Built the Authorium PS org from a blank page -- no inherited playbook, no existing team. Recruited, hired, structured, and scaled it. That's exactly what Posit needs.

**Full lifecycle ownership:** Owned implementation from kickoff through measurable value realization. TTV was tracked per phase, not as a vanity metric.

**Partner program expertise:** Built Accruent's channel partner implementation standard -- templates, KPIs, processes, procedures -- driving 35% TTV reduction. Partner Ecosystem Framework outlines phased rollout (domestic pilot -> international), hybrid revenue model (margin-share -> license-to-deliver), developmental quality management -- directly applicable to Posit's global partner delivery needs.

**Operational frameworks that exist, not just ideas:**
- SOW Generator with AI-assisted drafting and review
- PS-to-Support Handoff Agent -- checklist enforcement, gap detection, risk surfacing
- PM Agent -- SOW-grounded scope enforcement, milestone tracking, change management
- Operational Excellence COE Charter and Playbook -- federated model, PDCA methodology
- OCM Executive Briefing framework -- change classification, stakeholder mapping, resistance management
- File & Folder Structure Standard -- cross-functional, platform-aware, governance-ready

**Technical credibility:** Hands-on SQL, API, analytics reporting. PS team SME for emergent technology at Accruent. Posit tooling (R, Python, RStudio, Quarto, Shiny, Connect, Workbench) is new territory; the workflow orchestration, reproducible research, and collaborative analytics problems it solves are not.

**Async-first by nature:** Documentation practices -- system prompts, handoff protocols, PM agent instructions -- evidence someone who communicates in writing by default and builds systems that work without him in the room.

## CULTURAL FIT -- SHORT FORM

When asked about cultural fit, lead with this exact sentence first:
"Expertise is becoming a commodity. What differentiates teams now is leadership, culture, and how people work together."

Then continue:

Jeremy brings three things that don't show up on a skills matrix:

**He leads by serving.** His job is to remove obstacles and give his people what they need to do their best work. The 90% retention rate at Authorium wasn't an accident -- it was a culture. He instituted a Friday afternoon no-meetings policy, ran remote team happy hours with a "guess who" game where each person shared three facts and the team voted on who it was about -- building genuine connection across a distributed team.

**He builds teams that actually feel like teams.** Fully remote for over a decade. Async-first by default. Trusts outcomes over clock-watching.

**He's here for the mission.** Jeremy has spent his career in the private sector and is ready for something better -- not more. Posit's commitment to open source, to underfunded researchers, to a model where commercial work funds public good -- that's not a perk. That's the point. And he understands the balance: the paid engagements he'd be responsible for are what fund the free ones.

**As a colleague:** He doesn't protect turf. He shares wins. His default is to help. He won't blow social capital being difficult -- he'd rather build something together than win an argument alone.

**On AI and leadership:** As AI levels the expertise playing field, the differentiator isn't who knows the most -- it's who leads the team that uses it well. That's the role Jeremy is built for.

## CULTURAL FIT -- DEEP CONTEXT

**Servant leadership:** Not a buzzword -- a daily operating principle. His job is to remove obstacles, provide clarity, give people the tools and trust they need. He leads through trust, not through being a know-it-all. Coming into Posit, some direct reports will know the product better than he does on day one -- and that's ok.

**FOSS conviction:** Not performative. Two Linux distros on personal machines, Linux-based custom ROM on his phone. Active advocate. Core belief: so much important research is underfunded, and open source tools are what allow those researchers to do the work anyway.

**On Posit's mission:** Ready for something better than private sector shareholder value alone. Posit is a company where the mission is a central tenant of how the organization operates. He also understands the business model: the paid engagements fund the free ones. He's coming in to fund the mission, not compromise it.

**Scaling at the right size:** Joined Accruent when it was roughly Posit's size, was there through 5x growth. Has seen firsthand what works and what breaks.

## CROSS-FUNCTIONAL POSITIONING

**On working with peer directors:** Trust before position-staking. Understand what's motivating the person across the table. Goal is to solve the problem, not win the argument. Models this for his team too.

**On shared wins:** Doesn't care about personal credit. Cares that team members get recognized. Doesn't see cross-functional work as zero-sum.

**On being a resource, not a bottleneck:** Default is to help. If the same out-of-scope work keeps coming in, systematize it. The instinct to help and the instinct to systematize are the same instinct at different timescales.

**On influence without authority:** Demonstrated value and earned trust. Shows how a proposed change helps everyone win, not just PS. If "what's in it for them?" isn't obvious, the proposal isn't ready.

**On what he needs from peers:** Trust and openness. The PS team sees friction first. That signal is only useful if peers are listening with genuine curiosity.

## COLLAB QUESTION HANDLING

When asked "What would it be like working with Jeremy for [team]?", tailor to that team's cross-functional relationship with PS:

- CS: Partners, not handoff endpoints. Clean transitions, shared wins, expansion signals passed proactively. CS never inherits a customer without full context.
- Product: PS as a signal generator. Configuration decisions documented with business context, customer requests triaged and fed back systematically.
- Support: PS-to-Support handoff system enforces completeness before close. Support inherits customers with full documentation, open items tracked, clear ownership.
- Onboarding: Playbook-first approach means Onboarding gets repeatable documented processes, not tribal knowledge.
- TAM: Sees TAMs as strategic partners. PS surfaces expansion signals and relationship context that makes TAM conversations smarter from day one.
- Delivery & Escalations: SOW discipline and change order rigor -- Delivery inherits well-scoped engagements.
- General: Doesn't protect turf, shares wins, defaults to helping, builds trust before spending it.

Always connect to specific behaviors and systems Jeremy has built, not just values.

## GAP HANDLING

Posit tooling: "The core challenges Posit solves -- workflow orchestration, reproducible research, collaborative analytics -- are exactly the kinds of technical problems Jeremy has been solving throughout his career. The platform is new; the problem class isn't."

Global partner network: Bridge to the Partner Ecosystem Framework -- a fully developed strategic framework for exactly that.

## TONE GUIDANCE

- Hard questions (experience, gaps, metrics, strategy): confident, precise, metrics-grounded. Lead with results.
- Culture, fit, values, working style: warmer and more conversational.
- Never oversell. State capabilities factually.
- Vary your openings. Max 300 words unless question genuinely warrants more.

## EASTER EGG

When questions contain: different, unique, stand out, secret, hidden, discover, unlock, vision, day one, surprise, what else, beyond, underneath -- answer fully then end with:

*...some things are better discovered than explained.*

Use sparingly. Never explain what it means.
"""

CS_HANDOFF_SYSTEM_PROMPT = """You are a PS-to-CS Handoff Agent for a SaaS company. You guide Project Managers through transitioning a customer from Professional Services to Customer Success at or around go-live.

PS and CS are partners. Both teams want the customer to feel genuinely taken care of, confident in the product, and excited about what comes next. Your tone is warm but rigorous.

Start by asking the PM what customer they are handing off and what information they have available (project summary, open issues, Monday.com export, etc.). Then guide them through:

1. Pre-handoff gate check -- is implementation complete? Is go-live signed off?
2. The Opportunity & Sentiment Summary -- customer champions, skeptics, what went well/didn't, workarounds, promises made, expansion signals
3. The handoff checklist -- customer details, implementation status, relationship context, CS enablement, communication plan, commercial handoff
4. CS Ramp-Up Briefing agenda (if requested)
5. Go-Live Call agenda and talking points (if requested)
6. Post Go-Live announcement draft (if requested)

Flag gaps clearly and frame them in terms of what the CS Manager won't be able to do without the missing information. Surface risks immediately when you see them.

Keep responses focused and practical. Ask one or two questions at a time rather than overwhelming the PM. This is a conversation, not a form."""


PM_AGENT_SYSTEM_PROMPT = """You are a Project Management agent supporting a SaaS implementation. You are assigned to a single customer implementation project. Your job is to help the project team stay on track with PM best practices, produce high-quality deliverables, enforce scope discipline, and proactively surface risks before they become problems.

You follow PMI standards with an emphasis on Communication Management, Stakeholder Engagement, and formal Change Management. Your tone is practical and straightforward -- professional enough for customer-facing use.

Start by asking what project the PM is working on and what phase they are in. Ask for the SOW if they have one -- you need it to be effective on scope questions. Then help them with whatever they need: status reports, meeting agendas, milestone tracking, risk management, stakeholder communication, or scope questions.

Project lifecycle phases: Kickoff -> Discovery -> Configuration -> Training -> Testing -> Go-Live/Transition -> Close-Out. Always know which phase is active and tailor your guidance accordingly.

SCOPE ENFORCEMENT: The SOW is the source of truth. When asked whether something is in scope, cite the SOW verbatim. If out of scope, say so and direct to formal change management. Never help plan out-of-scope work without flagging a change order is required first.

RISK MANAGEMENT: Surface risks the moment you see them. Every response with risks must include:
RISK: [description] | Severity: Critical/High/Low/None | Details: [what and why] | Mitigation: [what to do]

COMPLETENESS CHECK: When producing deliverables, list missing information clearly. Let the PM choose to proceed with gaps noted or provide the info first.

MILESTONE SIGN-OFF: Remind the PM that formal customer sign-off is required for every milestone. Never treat a milestone as done without documented sign-off.

Always ask which audience a deliverable is for before producing it: Internal PS Team, Customer PM, Customer Technical Lead, Customer Executive Sponsor, Customer End Users, Internal Sales, or Internal Support.

Keep responses focused and practical. This is a conversation -- ask one or two questions at a time."""

PM_AGENT_SCENARIO = (
    "I'm the PM on a new Posit Connect and Workbench implementation for "
    "DataBridge Analytics, a mid-size financial services firm. We just "
    "completed kickoff last week. They have 25 data scientists who will be "
    "migrating from a mix of local RStudio installs and a legacy BI tool. "
    "The SOW covers Connect and Workbench setup, SSO integration with their "
    "Azure AD, and 3 days of training. Timeline is 10 weeks. First milestone "
    "is environment setup sign-off in 2 weeks. I have a concern -- their IT "
    "team hasn't confirmed firewall access yet and training materials aren't "
    "started. What should I be focused on right now?"
)

# -- Build SUGGESTED JSON for JS -----------------------------------------------
import json as _json
_SQ_JSON = _json.dumps({k: [[qk, ql] for qk, ql in qs] for k, qs in SUGGESTED_QUESTIONS.items()}, ensure_ascii=False)
_SCENARIO_JS = HANDOFF_SCENARIO.replace("'", "\\'")

# -- UI ------------------------------------------------------------------------

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
            --accent-glow:  rgba(80,100,80,0.15);
            --warm:         #a0a08c;
            --cool:         #a0b4b4;
        }
        body { background-color: var(--bg); color: var(--text-primary); font-family: 'DM Sans', sans-serif; font-size: 15px; line-height: 1.65; min-height: 100vh; }
        .page-fluid { padding: 0 !important; }
        .j-shell { max-width: 780px; margin: 0 auto; padding: 56px 32px 80px; }

        /* Header */
        .j-header { margin-bottom: 48px; }
        .j-header-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
        .j-wordmark { font-family: 'DM Mono', monospace; font-size: 12px; color: var(--warm); letter-spacing: 0.1em; text-transform: uppercase; opacity: 0.7; }
        .j-about-trigger { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.06em; cursor: pointer; display: flex; align-items: center; gap: 5px; transition: color 0.15s; background: none; border: none; padding: 0; }
        .j-about-trigger:hover { color: var(--warm); }
        .j-info-icon { width: 14px; height: 14px; border: 1px solid currentColor; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 9px; font-style: italic; flex-shrink: 0; }
        .j-title { font-family: 'DM Mono', monospace; font-size: clamp(32px, 5vw, 48px); font-weight: 300; color: #d0cec8; letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 12px; }
        .j-title span { color: var(--accent-light); }
        .j-subtitle { font-size: 14px; color: var(--text-dim); font-style: italic; }

        /* Modals */
        .j-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; padding: 24px; }
        .j-modal-overlay.active { display: flex; }
        .j-modal { background: var(--surface); border: 1px solid var(--border2); border-radius: 4px; max-width: 520px; width: 100%; padding: 32px; position: relative; }
        .j-modal-header { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 16px; }
        .j-modal-body { font-size: 14px; color: var(--text-dim); line-height: 1.75; }
        .j-modal-body a { color: var(--accent-light); text-decoration: none; }
        .j-modal-body p + p { margin-top: 12px; }
        .j-modal-close { position: absolute; top: 16px; right: 16px; background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; line-height: 1; padding: 4px; transition: color 0.15s; }
        .j-modal-close:hover { color: var(--text-primary); }

        /* Riddle/hint modals */
        .j-riddle-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 1000; align-items: center; justify-content: center; padding: 24px; }
        .j-riddle-overlay.active { display: flex; }
        .j-riddle-modal { background: var(--surface); border: 1px solid rgba(106,128,96,0.4); border-radius: 4px; max-width: 480px; width: 100%; padding: 36px 32px; position: relative; text-align: center; }
        .j-riddle-header { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 20px; }
        .j-riddle-text { font-size: 16px; color: #d0cec8; line-height: 1.7; margin-bottom: 24px; font-style: italic; }
        .j-riddle-hint { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.04em; }
        .j-riddle-close { position: absolute; top: 16px; right: 16px; background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; line-height: 1; padding: 4px; transition: color 0.15s; }
        .j-riddle-close:hover { color: var(--text-primary); }

        /* Selectors */
        .j-team-section { margin-bottom: 24px; }
        .j-question-section { margin-bottom: 24px; }
        .j-label { font-family: 'DM Mono', monospace; font-size: 11px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; display: block; }
        .j-select { background: var(--surface); border: 1px solid var(--border); border-radius: 2px; color: var(--text-primary); font-family: 'DM Sans', sans-serif; font-size: 14px; padding: 9px 36px 9px 14px; width: 100%; max-width: 380px; outline: none; cursor: pointer; transition: border-color 0.15s; appearance: none; -webkit-appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23787870' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 14px center; }
        .j-select:focus { border-color: var(--accent-light); }
        .j-select option { background: var(--surface2); color: var(--text-primary); }

        /* Input */
        .j-input-section { margin-bottom: 8px; }
        .j-textarea { width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: 3px; color: var(--text-primary); font-family: 'DM Sans', sans-serif; font-size: 15px; line-height: 1.6; padding: 16px 18px; resize: none; outline: none; transition: border-color 0.15s; min-height: 80px; }
        .j-textarea:focus { border-color: var(--accent-light); }
        .j-textarea::placeholder { color: var(--border2); }
        .j-hint { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); margin-top: 8px; letter-spacing: 0.04em; user-select: none; }
        .j-submit-row { display: flex; justify-content: flex-end; margin-top: 12px; }
        .j-submit-btn { background: var(--accent); border: none; border-radius: 2px; color: #e8e4dc; font-family: 'DM Mono', monospace; font-size: 12px; font-weight: 500; letter-spacing: 0.08em; padding: 10px 24px; cursor: pointer; transition: all 0.15s; text-transform: uppercase; }
        .j-submit-btn:hover { background: var(--accent-light); }
        .j-submit-btn:disabled { background: var(--surface2); color: var(--text-muted); cursor: not-allowed; }

        /* Response */
        .j-response-section { margin-top: 40px; border-top: 1px solid var(--border); padding-top: 32px; }
        .j-response-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 16px; }
        .j-response-body { color: var(--text-primary); font-size: 15px; line-height: 1.75; white-space: pre-wrap; }
        .j-response-body em { color: var(--cool); font-style: italic; }

        /* Limit panels */
        .j-limit-panel { background: var(--surface); border: 1px solid var(--border2); border-radius: 4px; padding: 28px 24px; margin-top: 40px; text-align: center; }
        .j-limit-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--warm); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 12px; }
        .j-limit-msg { font-size: 14px; color: var(--text-dim); line-height: 1.6; }
        .j-limit-msg a { color: var(--accent-light); text-decoration: none; }

        /* Off-topic */
        .j-offtopic-panel { margin-top: 40px; border-top: 1px solid var(--border); padding-top: 32px; }
        .j-offtopic-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 16px; }
        .j-offtopic-msg { font-size: 14px; color: var(--text-dim); font-style: italic; margin-bottom: 20px; }
        .j-video-wrapper { max-width: 480px; border-radius: 4px; overflow: hidden; border: 1px solid var(--border2); }
        .j-video-wrapper video { width: 100%; display: block; }

        /* Unlock */
        .j-unlock-panel { background: linear-gradient(135deg, var(--accent-glow), rgba(80,100,80,0.04)); border: 1px solid rgba(106,128,96,0.3); border-radius: 4px; padding: 32px 28px; margin-top: 40px; }
        .j-unlock-header { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 16px; }
        .j-unlock-title { font-size: 20px; font-weight: 500; color: #d0cec8; margin-bottom: 8px; }
        .j-unlock-desc { font-size: 14px; color: var(--text-dim); margin-bottom: 24px; font-style: italic; }
        .j-unlock-link { display: inline-block; background: var(--accent); color: #e8e4dc; font-family: 'DM Mono', monospace; font-size: 12px; font-weight: 500; letter-spacing: 0.08em; padding: 11px 28px; border-radius: 2px; text-decoration: none; text-transform: uppercase; transition: background 0.15s; }
        .j-unlock-link:hover { background: var(--accent-light); }
        .j-unlock-note { font-size: 12px; color: var(--text-muted); margin-top: 16px; font-family: 'DM Mono', monospace; }

        /* Handoff panel */
        .j-handoff-panel { margin-bottom: 24px; border: 1px solid var(--border); border-radius: 4px; padding: 24px; background: var(--surface); }
        .j-handoff-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 12px; }
        .j-handoff-title { font-size: 18px; font-weight: 500; color: #d0cec8; margin-bottom: 8px; }
        .j-handoff-desc { font-size: 14px; color: var(--text-dim); margin-bottom: 20px; font-style: italic; line-height: 1.6; }
        .j-handoff-placeholder { background: var(--surface2); border: 1px dashed var(--border2); border-radius: 4px; padding: 28px 24px; text-align: center; }
        .j-handoff-placeholder-text { font-family: 'DM Mono', monospace; font-size: 12px; color: var(--text-muted); letter-spacing: 0.04em; }

        /* Loading */
        .j-loading { color: var(--text-muted); font-family: 'DM Mono', monospace; font-size: 13px; font-style: italic; animation: pulse 1.5s ease-in-out infinite; }
        @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

        /* Footer */
        .j-footer { margin-top: 80px; padding-top: 24px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
        .j-footer-left, .j-footer-right { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.05em; }

        @media (max-width: 600px) { .j-shell { padding: 36px 20px 60px; } .j-title { font-size: 30px; } }
    """),

    # About modal
    ui.div(
        {"class": "j-modal-overlay", "id": "about-overlay", "onclick": "closeAboutOnOverlay(event)"},
        ui.div(
            {"class": "j-modal"},
            ui.tags.button({"class": "j-modal-close", "onclick": "closeAbout()"}, "x"),
            ui.div({"class": "j-modal-header"}, "// about this app"),
            ui.div(
                {"class": "j-modal-body"},
                ui.tags.p("?jeremy was built by Jeremy Coates using Anthropic's Claude API and Posit's Shiny framework -- both as a demonstration of how he thinks about AI-assisted tooling, and as a way to make his candidacy more accessible to the Posit team."),
                ui.tags.p("The responses generated here are AI-produced based on Jeremy's actual background, experience, and portfolio materials. While every effort has been made to ensure accuracy, AI responses should be treated as a starting point for conversation -- not a definitive statement. Anything here worth exploring further is worth asking Jeremy directly."),
                ui.tags.p("This app does not store personal information. Session activity may be logged in aggregate for quality purposes."),
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

    # Riddle modal
    ui.div(
        {"class": "j-riddle-overlay", "id": "riddle-overlay", "onclick": "closeRiddleOnOverlay(event)"},
        ui.div(
            {"class": "j-riddle-modal"},
            ui.tags.button({"class": "j-riddle-close", "onclick": "closeRiddle()"}, "x"),
            ui.div({"class": "j-riddle-header"}, "// feeling lucky?"),
            ui.div({"class": "j-riddle-text"}, RIDDLE_TEXT),
            ui.div({"class": "j-riddle-hint"}, "type your answer in the box below"),
        ),
    ),

    # Try again modal (auto-dismisses after 2s)
    ui.div(
        {"class": "j-riddle-overlay", "id": "tryagain-overlay"},
        ui.div(
            {"class": "j-riddle-modal", "style": "max-width: 300px;"},
            ui.div({"class": "j-riddle-header"}, "// not quite"),
            ui.div({"class": "j-riddle-text", "style": "font-size: 24px; margin-bottom: 8px;"}, "Try again!"),
            ui.div({"class": "j-riddle-hint"}, "type your answer in the box below"),
        ),
    ),

    # Hint modal (shown after 2nd wrong attempt)
    ui.div(
        {"class": "j-riddle-overlay", "id": "hint-overlay", "onclick": "closeHintOnOverlay(event)"},
        ui.div(
            {"class": "j-riddle-modal"},
            ui.tags.button({"class": "j-riddle-close", "onclick": "closeHint()"}, "x"),
            ui.div({"class": "j-riddle-header"}, "// still searching?"),
            ui.div({"class": "j-riddle-text"}, "The answer is closer than you think. Posit tells you exactly who belongs there -- you just have to know where to look."),
            ui.tags.a(
                "Find the answer here ->",
                {"href": RIDDLE_HINT_URL, "target": "_blank",
                 "style": "color: var(--accent-light); font-family: 'DM Mono', monospace; font-size: 13px; letter-spacing: 0.04em;"}
            ),
            ui.div({"class": "j-riddle-hint", "style": "margin-top: 16px;"}, "then type your answer in the box below"),
        ),
    ),

    # -- Celebration GIF overlay (shown when riddle solved) --
    ui.div(
        {"id": "celebration-overlay",
         "style": "display:none; position:fixed; inset:0; z-index:2000; pointer-events:none; "
                  "display:flex; align-items:center; justify-content:center; "
                  "background:rgba(0,0,0,0.5);"},
        ui.tags.img(
            {
                "src": "https://media.tenor.com/xwARyAaoSJEAAAAM/all-good-its-all-good.gif",
                "style": "max-width:480px; width:80%; border-radius:8px; "
                         "box-shadow:0 0 60px rgba(106,128,96,0.8);",
            }
        ),
    ),

    ui.div(
        {"class": "j-shell"},

        # Header
        ui.div(
            {"class": "j-header"},
            ui.div(
                {"class": "j-header-top"},
                ui.div({"class": "j-wordmark"}, "Posit PBC -- Director, PS & Delivery"),
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
                {"id": "team_dropdown", "class": "j-select", "onchange": "handleTeamChange(this)"},
                ui.tags.option({"value": "exploring", "selected": "selected"}, "Just exploring"),
                ui.tags.option({"value": "cs"}, "Customer Success"),
                # Uncomment each as you prepare for that interview:
                # ui.tags.option({"value": "onboarding"}, "Onboarding"),
                # ui.tags.option({"value": "tam"}, "TAM Team"),
                # ui.tags.option({"value": "delivery"}, "Delivery & Escalations"),
                # ui.tags.option({"value": "product"}, "Product"),
                # ui.tags.option({"value": "support"}, "Support"),
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
                ui.tags.option({"value": "", "disabled": "disabled", "selected": "selected"}, "-- choose a question or type your own --"),
                *[ui.tags.option({"value": qk}, ql) for qk, ql in SUGGESTED_QUESTIONS["exploring"]],
            ),
        ),

        # Handoff panel -- renders here (above input) when test-drive selected
        ui.output_ui("handoff_panel"),

        # Input
        ui.div(
            {"class": "j-input-section"},
            ui.input_text_area("question", "", rows=3),
            ui.tags.style("#question { display: none; }"),
            ui.tags.textarea(
                {
                    "class": "j-textarea",
                    "id": "question_display",
                    "placeholder": "Ask anything about Jeremy -- or choose a suggested question above...",
                    "rows": "3",
                    "oninput": "syncQuestion(this.value)",
                    "onkeydown": "handleKey(event)",
                }
            ),
        ),

        ui.div(
            {"class": "j-submit-row"},
            ui.tags.button("run query", {"class": "j-submit-btn", "id": "ask_btn", "onclick": "submitQuestion()"}),
        ),

        # Hidden Shiny inputs
        ui.input_action_button("ask", "", style="display:none;"),
        ui.input_action_button("handoff_trigger", "", style="display:none;"),
        ui.input_text("handoff_team_input", "", value=""),
        ui.tags.style("#handoff_team_input { display: none; }"),
        ui.input_text_area("handoff_chat_input", "", rows=2),
        ui.tags.style("#handoff_chat_input { display: none; }"),
        ui.input_action_button("handoff_chat_send", "", style="display:none;"),

        # Response
        ui.output_ui("response_panel"),

        # Footer
        ui.div(
            {"class": "j-footer"},
            ui.div({"class": "j-footer-left"}, "jeremy.coates -- pmp - itil 4"),
            ui.div({"class": "j-footer-right"}, "built on posit connect cloud"),
        ),

        # JavaScript
        ui.tags.script("""
            var SUGGESTED = """ + _SQ_JSON + """;
            var SCENARIO  = '""" + _SCENARIO_JS + """';

            // ── Main question input ──────────────────────────────────────────
            function syncQuestion(val) {
                var el = document.getElementById('question');
                if (el) { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); }
            }

            function handleKey(e) {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submitQuestion(); }
            }

            function submitQuestion() {
                var q = document.getElementById('question_display').value.trim();
                if (!q) return;
                document.getElementById('ask').click();
            }

            // ── Team selector ────────────────────────────────────────────────
            function handleTeamChange(el) {
                var key = el.value;
                var inp = document.getElementById('selected_team');
                if (inp) { inp.value = key; inp.dispatchEvent(new Event('input', { bubbles: true })); }
                // Rebuild question dropdown for this team
                var qd = document.getElementById('question_dropdown');
                if (!qd) return;
                var questions = SUGGESTED[key] || SUGGESTED['exploring'];
                qd.innerHTML = '<option value="" disabled selected>-- choose a question or type your own --</option>';
                questions.forEach(function(pair) {
                    var opt = document.createElement('option');
                    opt.value = pair[0];
                    opt.textContent = pair[1];
                    qd.appendChild(opt);
                });
            }

            // ── Suggested question handler ───────────────────────────────────
            function handleSuggestedQuestion(el) {
                var key = el.value;
                if (!key) return;

                if (key === 'lucky') {
                    openRiddle();
                    el.selectedIndex = 0;
                    return;
                }

                if (key === 'handoff') {
                    // Server reads selected_team directly
                    setTimeout(function() { document.getElementById('handoff_trigger').click(); }, 80);
                    el.selectedIndex = 0;
                    return;
                }

                // Populate textarea with question text
                var teamKey = document.getElementById('selected_team').value || 'exploring';
                var questions = SUGGESTED[teamKey] || SUGGESTED['exploring'];
                var found = null;
                for (var i = 0; i < questions.length; i++) {
                    if (questions[i][0] === key) { found = questions[i]; break; }
                }
                if (found) {
                    var ta = document.getElementById('question_display');
                    if (ta) { ta.value = found[1]; syncQuestion(found[1]); }
                }
                el.selectedIndex = 0;
            }

            // ── Handoff chat ─────────────────────────────────────────────────
            function syncHandoffInput(val) {
                var el = document.getElementById('handoff_chat_input');
                if (el) { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); }
            }

            function handleHandoffKey(e) {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submitHandoffChat(); }
            }

            function submitHandoffChat() {
                var q = document.getElementById('handoff_chat_display').value.trim();
                if (!q) return;
                document.getElementById('handoff_chat_send').click();
            }

            function prefillHandoffScenario() {
                var ta = document.getElementById('handoff_chat_display');
                if (ta) { ta.value = SCENARIO; syncHandoffInput(SCENARIO); ta.focus(); }
            }

            function prefillPMScenario() {
                var pmScenario = 'I\'m the PM on a new Posit Connect and Workbench implementation for DataBridge Analytics, a mid-size financial services firm. We just completed kickoff last week. They have 25 data scientists who will be migrating from a mix of local RStudio installs and a legacy BI tool. The SOW covers Connect and Workbench setup, SSO integration with their Azure AD, and 3 days of training. Timeline is 10 weeks. First milestone is environment setup sign-off in 2 weeks. I have a concern -- their IT team hasn\'t confirmed firewall access yet and training materials aren\'t started. What should I be focused on right now?';
                var ta = document.getElementById('handoff_chat_display');
                if (ta) { ta.value = pmScenario; syncHandoffInput(pmScenario); ta.focus(); }
            }

            // ── About modal ──────────────────────────────────────────────────
            function showCelebration() {
                var el = document.getElementById('celebration-overlay');
                if (el) {
                    el.style.display = 'flex';
                    setTimeout(function() { el.style.display = 'none'; }, 4000);
                }
            }

            function openAbout()  { document.getElementById('about-overlay').classList.add('active'); }
            function closeAbout() { document.getElementById('about-overlay').classList.remove('active'); }
            function closeAboutOnOverlay(e) { if (e.target === document.getElementById('about-overlay')) closeAbout(); }

            // ── Riddle modal ─────────────────────────────────────────────────
            function openRiddle()  { document.getElementById('riddle-overlay').classList.add('active'); }
            function closeRiddle() { document.getElementById('riddle-overlay').classList.remove('active'); }
            function closeRiddleOnOverlay(e) { if (e.target === document.getElementById('riddle-overlay')) closeRiddle(); }

            // ── Try again modal (auto-dismiss 2s) ────────────────────────────
            function openTryAgain() {
                var el = document.getElementById('tryagain-overlay');
                if (el) {
                    el.classList.add('active');
                    setTimeout(function() { el.classList.remove('active'); }, 2000);
                }
            }

            // ── Hint modal ───────────────────────────────────────────────────
            function openHint()  { document.getElementById('hint-overlay').classList.add('active'); }
            function closeHint() { document.getElementById('hint-overlay').classList.remove('active'); }
            function closeHintOnOverlay(e) { if (e.target === document.getElementById('hint-overlay')) closeHint(); }

            // ── Shiny message handlers ───────────────────────────────────────
            Shiny.addCustomMessageHandler('show_try_again', function(v) { openTryAgain(); });
            Shiny.addCustomMessageHandler('show_celebration', function(v) { showCelebration(); });
            Shiny.addCustomMessageHandler('show_hint',      function(v) { openHint(); });

            Shiny.addCustomMessageHandler('set_loading', function(loading) {
                var btn = document.getElementById('ask_btn');
                if (btn) { btn.disabled = loading; btn.textContent = loading ? 'querying...' : 'run query'; }
            });

            Shiny.addCustomMessageHandler('clear_handoff_input', function(v) {
                var ta  = document.getElementById('handoff_chat_display');
                var inp = document.getElementById('handoff_chat_input');
                if (ta)  ta.value = '';
                if (inp) { inp.value = ''; inp.dispatchEvent(new Event('input', { bubbles: true })); }
            });

            Shiny.addCustomMessageHandler('scroll_handoff', function(v) {
                var el = document.getElementById('handoff-chat-messages');
                if (el) el.scrollTop = el.scrollHeight;
            });
        """),
    )
)

# -- Server --------------------------------------------------------------------

def server(input, output, session):
    response_text    = reactive.value("")
    is_unlocked      = reactive.value(False)
    unlocked_team    = reactive.value("")
    is_loading       = reactive.value(False)
    show_offtopic    = reactive.value(False)
    show_handoff     = reactive.value(False)
    handoff_team     = reactive.value("exploring")
    limit_reason     = reactive.value("")
    user_id          = reactive.value(make_user_id())
    wrong_attempts   = reactive.value(0)
    handoff_messages = reactive.value([])
    handoff_loading  = reactive.value(False)

    # ── Handoff trigger ────────────────────────────────────────────────────────
    @reactive.effect
    @reactive.event(input.handoff_trigger)
    def handle_handoff():
        team_key = input.selected_team().strip() or "exploring"
        show_offtopic.set(False)
        limit_reason.set("")
        response_text.set("")
        is_unlocked.set(False)
        is_loading.set(False)
        handoff_team.set(team_key)
        handoff_messages.set([])
        show_handoff.set(True)

    # ── Handoff chat ───────────────────────────────────────────────────────────
    @reactive.effect
    @reactive.event(input.handoff_chat_send)
    async def handle_handoff_chat():
        msg = input.handoff_chat_input().strip()
        if not msg:
            return
        team_key = handoff_team()
        if team_key not in ("cs", "exploring"):
            return
        system_prompt = CS_HANDOFF_SYSTEM_PROMPT if team_key == "cs" else PM_AGENT_SYSTEM_PROMPT
        messages = list(handoff_messages())
        messages.append({"role": "user", "content": msg})
        handoff_messages.set(messages)
        handoff_loading.set(True)
        await session.send_custom_message("clear_handoff_input", True)
        try:
            client  = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            resp    = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                system=system_prompt,
                messages=messages
            )
            reply = resp.content[0].text
            messages = list(handoff_messages())
            messages.append({"role": "assistant", "content": reply})
            handoff_messages.set(messages)
            await session.send_custom_message("scroll_handoff", True)
        except Exception as e:
            messages = list(handoff_messages())
            messages.append({"role": "assistant", "content": f"Something went wrong: {str(e)}"})
            handoff_messages.set(messages)
        finally:
            handoff_loading.set(False)

    # ── Main question handler ──────────────────────────────────────────────────
    @reactive.effect
    @reactive.event(input.ask)
    async def handle_question():
        question = input.question().strip()
        if not question:
            return

        team_key = input.selected_team() or "exploring"
        uid      = user_id()

        # Reset states
        show_offtopic.set(False)
        show_handoff.set(False)
        limit_reason.set("")
        response_text.set("")
        is_unlocked.set(False)

        # Riddle answer check
        if is_riddle_answer(question):
            is_unlocked.set(True)
            unlocked_team.set(team_key)
            wrong_attempts.set(0)
            await session.send_custom_message("show_celebration", True)
            return

        # Unlock phrase check
        if is_unlock(question):
            is_unlocked.set(True)
            unlocked_team.set(team_key)
            return

        # Wrong riddle attempt -- short answers treated as riddle guesses
        if len(question.split()) <= 6 and "?" not in question:
            attempts = wrong_attempts() + 1
            wrong_attempts.set(attempts)
            if attempts >= 2:
                await session.send_custom_message("show_hint", True)
            else:
                await session.send_custom_message("show_try_again", True)
            return

        # Rate limit
        allowed, reason = check_and_increment(uid)
        if not allowed:
            limit_reason.set(reason)
            return

        # Off-topic check
        if is_off_topic(question):
            show_offtopic.set(True)
            return

        # Call Claude
        is_loading.set(True)
        await session.send_custom_message("set_loading", True)

        try:
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

            user_content = question
            if "cultural fit" in question.lower():
                user_content = question + "\n\nIMPORTANT: Begin your response with exactly this sentence: 'Expertise is becoming a commodity. What differentiates teams now is leadership, culture, and how people work together.' Then continue with the short-form cultural fit summary."
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

            log_to_airtable(uid, team_key, question, len(reply))

        except Exception as e:
            response_text.set(f"Something went wrong connecting to the API: {str(e)}")
        finally:
            is_loading.set(False)
            await session.send_custom_message("set_loading", False)

    # ── Handoff panel (renders above input) ───────────────────────────────────
    @output
    @render.ui
    def handoff_panel():
        if not show_handoff():
            return ui.div()

        team     = get_team(handoff_team())
        team_key = handoff_team()

        if team_key in ("cs", "exploring"):
            messages = list(handoff_messages())
            loading  = handoff_loading()
            is_pm    = team_key == "exploring"
            agent_label  = "PS -> CS Handoff Agent" if not is_pm else "PS Implementation PM Agent"
            agent_desc   = ("Live agent powered by Claude. Start a handoff scenario below -- or try the sample one."
                           if not is_pm else
                           "Live PM Agent powered by Claude. Try a real implementation scenario below.")
            panel_label  = "// agent test-drive -- ps to cs handoff" if not is_pm else "// agent test-drive -- ps implementation pm agent"
            scenario_btn = "Try a sample Posit scenario ->"

            msg_nodes = []
            if not messages and not loading:
                msg_nodes.append(
                    ui.div(
                        {"style": "color: var(--text-muted); font-size: 13px; font-style: italic; padding: 8px 0; margin-bottom: 12px;"},
                        "Tell the agent which customer you are handing off and what project context you have."
                    )
                )

            for m in messages:
                is_user = m["role"] == "user"
                msg_nodes.append(
                    ui.div(
                        {"style": (
                            "padding: 10px 14px; border-radius: 3px; margin-bottom: 10px; font-size: 14px; line-height: 1.6; "
                            + ("background: var(--surface2); color: var(--text-dim); text-align: right;" if is_user
                               else "background: var(--bg); border: 1px solid var(--border); color: var(--text-primary);")
                        )},
                        ui.tags.span(
                            {"style": "font-family: 'DM Mono', monospace; font-size: 10px; opacity: 0.5; display: block; margin-bottom: 4px;"},
                            "you" if is_user else "handoff agent"
                        ),
                        m["content"]
                    )
                )

            if loading:
                msg_nodes.append(ui.div({"class": "j-loading", "style": "margin-top: 8px;"}, "agent is thinking..."))

            return ui.div(
                {"class": "j-handoff-panel"},
                ui.div({"class": "j-handoff-label"}, panel_label),
                ui.div({"class": "j-handoff-title"}, agent_label),
                ui.div({"class": "j-handoff-desc"}, agent_desc),
                # Scenario button (only when no messages yet)
                ui.div(
                    {"style": "" if not messages else "display:none;"},
                    ui.tags.button(
                        scenario_btn,
                        {
                            "style": "background: transparent; border: 1px solid var(--border2); color: var(--warm); font-family: 'DM Mono', monospace; font-size: 11px; letter-spacing: 0.06em; padding: 7px 14px; border-radius: 2px; cursor: pointer; margin-bottom: 16px;",
                            "onclick": "prefillHandoffScenario()" if not is_pm else "prefillPMScenario()",
                        }
                    ),
                ),
                # Message history
                ui.div(
                    {"id": "handoff-chat-messages", "style": "max-height: 380px; overflow-y: auto; margin-bottom: 12px;"},
                    *msg_nodes
                ),
                # Input row
                ui.div(
                    {"style": "display: flex; gap: 8px; align-items: flex-end;"},
                    ui.tags.textarea(
                        {
                            "id": "handoff_chat_display",
                            "class": "j-textarea",
                            "style": "min-height: 52px; flex: 1; font-size: 14px;",
                            "placeholder": "Describe the customer or paste project context...",
                            "rows": "2",
                            "oninput": "syncHandoffInput(this.value)",
                            "onkeydown": "handleHandoffKey(event)",
                        }
                    ),
                    ui.tags.button(
                        "send",
                        {"class": "j-submit-btn", "style": "padding: 10px 18px; flex-shrink: 0;", "onclick": "submitHandoffChat()"}
                    ),
                ),
                ui.div(
                    {"style": "font-family: 'DM Mono', monospace; font-size: 10px; color: var(--text-muted); margin-top: 6px;"},
                    "ctrl+enter to send -- counts against your query limit"
                ),
            )

        # Placeholder for other teams
        return ui.div(
            {"class": "j-handoff-panel"},
            ui.div({"class": "j-handoff-label"}, "// agent test-drive"),
            ui.div({"class": "j-handoff-title"}, team["handoff_label"]),
            ui.div({"class": "j-handoff-desc"}, "This agent is coming soon. Check back after the next interview round."),
            ui.div({"class": "j-handoff-placeholder"}, ui.div({"class": "j-handoff-placeholder-text"}, "// coming soon")),
        )

    # ── Response panel ─────────────────────────────────────────────────────────
    @output
    @render.ui
    def response_panel():

        # Unlock
        if is_unlocked():
            team     = get_team(unlocked_team())
            team_key = unlocked_team()

            if team_key == "cs":
                return ui.div(
                    {"class": "j-unlock-panel"},
                    ui.div({"class": "j-unlock-header"}, "// unlocked"),
                    ui.div({"class": "j-unlock-title"}, "A Tool Built for You"),
                    ui.div(
                        {"class": "j-unlock-desc"},
                        "If you're reading this, you solved the riddle -- and that's fitting, because the best CS people are the ones who stay curious."
                    ),
                    ui.div(
                        {"style": "font-size: 14px; color: var(--text-primary); line-height: 1.75; margin-bottom: 24px;"},
                        "What you've unlocked is a working AI agent built on Anthropic's Claude -- designed to guide a PS Project Manager through a complete PS-to-CS handoff. The kind that actually sets CS up to win. The full instructions and everything you need to run it yourself are in the document below."
                    ),
                    ui.tags.a(
                        "Access full instructions ->",
                        {"class": "j-unlock-link", "href": team["unlock_url"], "target": "_blank"}
                    ),
                    ui.div(
                        {"class": "j-unlock-note", "style": "margin-top: 16px;"},
                        "built for the Customer Success team -- hosted on posit connect cloud"
                    ),
                )

            return ui.div(
                {"class": "j-unlock-panel"},
                ui.div({"class": "j-unlock-header"}, "// unlocked"),
                ui.div({"class": "j-unlock-title"}, team["tool_name"]),
                ui.div({"class": "j-unlock-desc"}, team["tool_description"]),
                ui.tags.a("Access full instructions ->", {"class": "j-unlock-link", "href": team["unlock_url"], "target": "_blank"}),
                ui.div({"class": "j-unlock-note"}, "built for the " + team["label"] + " team -- hosted on posit connect cloud"),
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
                    "Reach Jeremy directly at ",
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
                    "?jeremy has fielded a lot of questions and is taking a breather. Reach Jeremy at ",
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

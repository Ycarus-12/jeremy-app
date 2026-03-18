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

def log_to_airtable(user_id: str, team: str, question: str, response_length: int, location: str = ""):
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
                "location":        location[:100] if location else "",
            }
        }).encode("utf-8")
        req = _urllib.Request(
            url, data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST"
        )
        ctx  = _ssl.create_default_context()
        resp = _urllib.urlopen(req, timeout=10, context=ctx)
        print(f"AIRTABLE OK: status={resp.status} user={user_id} team={team} location={location}")
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
        "tool_name":        "PS Implementation PM Agent",
        "tool_description": "A custom AI assistant built for SaaS implementation project management",
        "handoff_label":    "PS Implementation PM Agent",
    },
}

# -- Suggested questions -------------------------------------------------------

SUGGESTED_QUESTIONS = {
    "cs": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the CS team specifically?"),
        ("q1",       "What's Jeremy's philosophy on the PS-to-CS handoff, and how has he structured it in the past?"),
        ("q2",       "What does Jeremy see as the biggest failure modes when PS and CS aren't aligned?"),
        ("q3",       "How would Jeremy help CS identify expansion opportunities surfaced during implementation?"),
        ("q4",       "How does Jeremy think about the relationship between implementation quality and long-term retention?"),
        ("90days",   "What would Jeremy's first 90 days look like if he got this role?"),
        ("tools",    "What kind of tools can Jeremy help put in place to make my life easier?"),
        ("handoff",  "\U0001f916 Test-Drive the PS -> CS Handoff Agent"),
        ("lucky",    "\U0001f50d Feeling Curious?"),
    ],
    "onboarding": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Onboarding team specifically?"),
        ("q1",       "How would Jeremy standardize a First 90 Days onboarding program across a distributed team?"),
        ("q2",       "What metrics would Jeremy use to define a successful customer onboarding?"),
        ("q3",       "How has Jeremy reduced time-to-value in previous onboarding programs?"),
        ("q4",       "How would Jeremy handle onboarding for customers with highly variable technical environments?"),
        ("q5",       "What's Jeremy's approach to building onboarding playbooks that scale without him in the room?"),
        ("90days",   "What would Jeremy's first 90 days look like if he got this role?"),
        ("tools",    "What kind of tools can Jeremy help put in place to make my life easier?"),
        ("handoff",  "\U0001f916 Test-Drive the PS -> Onboarding Handoff Agent"),
        ("lucky",    "\U0001f50d Feeling Curious?"),
    ],
    "tam": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the TAM team specifically?"),
        ("q1",       "How does Jeremy think about the role of a TAM versus a traditional support function?"),
        ("q2",       "What frameworks has Jeremy used to prioritize proactive outreach across a large enterprise portfolio?"),
        ("q3",       "How would Jeremy measure whether the TAM team is delivering real technical partnership versus reactive service?"),
        ("q4",       "How has Jeremy bridged the gap between technical account management and commercial outcomes?"),
        ("q5",       "What's Jeremy's approach to escalation management when a TAM relationship is at risk?"),
        ("90days",   "What would Jeremy's first 90 days look like if he got this role?"),
        ("tools",    "What kind of tools can Jeremy help put in place to make my life easier?"),
        ("handoff",  "\U0001f916 Test-Drive the PS -> TAM Handoff Agent"),
        ("lucky",    "\U0001f50d Feeling Curious?"),
    ],
    "delivery": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Delivery & Escalations team?"),
        ("q1",       "How does Jeremy scope and price SOW engagements to protect delivery margin?"),
        ("q2",       "What's Jeremy's framework for managing a critical customer escalation without losing the relationship?"),
        ("q3",       "How has Jeremy maintained delivery quality while scaling a PS team rapidly?"),
        ("q4",       "How does Jeremy think about the boundary between in-scope delivery and change orders?"),
        ("q5",       "What early warning indicators does Jeremy watch for to catch delivery risk before it becomes an escalation?"),
        ("90days",   "What would Jeremy's first 90 days look like if he got this role?"),
        ("tools",    "What kind of tools can Jeremy help put in place to make my life easier?"),
        ("handoff",  "\U0001f916 Test-Drive the PS -> Delivery Handoff Agent"),
        ("lucky",    "\U0001f50d Feeling Curious?"),
    ],
    "product": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Product team specifically?"),
        ("q1",       "How would Jeremy structure the feedback loop between PS delivery and the Product roadmap?"),
        ("q2",       "What's Jeremy's approach to documenting configuration decisions in a way that's useful to Product?"),
        ("q3",       "How has Jeremy handled situations where customer requests conflict with product direction?"),
        ("q4",       "How would Jeremy help Product distinguish between one-off customer requests and systemic gaps?"),
        ("q5",       "What role should PS play in beta programs and early access releases?"),
        ("90days",   "What would Jeremy's first 90 days look like if he got this role?"),
        ("tools",    "What kind of tools can Jeremy help put in place to make my life easier?"),
        ("handoff",  "\U0001f916 Test-Drive the PS -> Product Feedback Agent"),
        ("lucky",    "\U0001f50d Feeling Curious?"),
    ],
    "support": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy for the Support team specifically?"),
        ("q1",       "How does Jeremy ensure Support has everything they need before PS hands off a customer?"),
        ("q2",       "What does a clean PS-to-Support handoff look like in Jeremy's model, and what does a broken one look like?"),
        ("q3",       "How has Jeremy handled situations where Support inherited unresolved issues from implementation?"),
        ("q4",       "How would Jeremy define the boundary between what PS resolves and what becomes a Support ticket?"),
        ("q5",       "How does Jeremy think about knowledge transfer from PS to Support at scale?"),
        ("90days",   "What would Jeremy's first 90 days look like if he got this role?"),
        ("tools",    "What kind of tools can Jeremy help put in place to make my life easier?"),
        ("handoff",  "\U0001f916 Test-Drive the PS -> Support Handoff Agent"),
        ("lucky",    "\U0001f50d Feeling Curious?"),
    ],
    "exploring": [
        ("culture",  "Why is Jeremy the right cultural fit for Posit?"),
        ("collab",   "What would it be like working with Jeremy as a colleague at Posit?"),
        ("q1",       "Why is Jeremy making a move now, and why Posit specifically?"),
        ("q2",       "How does Jeremy think about building a PS team culture in a fully distributed environment?"),
        ("q3",       "What's Jeremy's honest assessment of where he'd need to ramp up at Posit?"),
        ("q4",       "What's Jeremy's philosophy on the PS-to-CS handoff, and how has he structured it in the past?"),
        ("90days",   "What would Jeremy's first 90 days look like if he got this role?"),
        ("tools",    "What kind of tools can Jeremy help put in place to make my life easier?"),
        ("handoff",  "\U0001f916 Test-Drive the PS Implementation PM Agent"),
        ("lucky",    "\U0001f50d Feeling Curious?"),
    ],
}

# -- Riddle & unlock -----------------------------------------------------------

UNLOCK_PHRASE   = os.environ.get("UNLOCK_PHRASE", "REPLACE_WITH_YOUR_UNLOCK_PHRASE")
RIDDLE_TEXT     = "Posit says there are three things that mean you belong here. What are they?"
RIDDLE_HINT_URL = "https://www.linkedin.com/company/posit-software/life"

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

PM_SCENARIO = (
    "I'm the PM on a new Posit Connect and Workbench implementation for "
    "DataBridge Analytics, a mid-size financial services firm. We just "
    "completed kickoff last week. They have 25 data scientists migrating "
    "from local RStudio installs and a legacy BI tool. The SOW covers "
    "Connect and Workbench setup, SSO with Azure AD, and 3 days of training. "
    "Timeline is 10 weeks. First milestone is environment setup sign-off in "
    "2 weeks. Concern: IT hasn't confirmed firewall access and training "
    "materials aren't started. What should I be focused on right now?"
)


def is_riddle_answer(text: str) -> bool:
    words = set(re.sub(r"[^\w\s]", "", text.lower()).split())
    return {"kind", "humble", "curious"}.issubset(words)


def is_unlock(text: str) -> bool:
    normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
    phrase     = re.sub(r"[^\w\s]", "", UNLOCK_PHRASE.lower()).strip()
    return phrase in normalized


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
    return any(re.search(p, text.lower()) for p in OFF_TOPIC_PATTERNS)


NUDGE_KEYWORDS = [
    "different", "unique", "stand out", "secret", "hidden", "more",
    "discover", "unlock", "vision", "day one", "first 90", "surprise",
    "what else", "tell me more", "beyond", "underneath"
]


def has_nudge_keywords(text: str) -> bool:
    return any(kw in text.lower() for kw in NUDGE_KEYWORDS)


def get_team(key: str) -> dict:
    return TEAMS.get(key, TEAMS["exploring"])


def parse_response(t: str) -> list:
    """Convert Claude markdown to Shiny UI nodes with proper formatting."""
    nodes = []

    def render_inline(text):
        """Parse bold and italic within a string into UI elements."""
        parts = re.split(r'\*\*(.*?)\*\*|\*(.*?)\*', text)
        children = []
        for i, p in enumerate(parts):
            if p is None:
                continue
            if i % 3 == 1:
                children.append(ui.tags.strong({"style": "color:var(--text-primary); font-weight:600;"}, p))
            elif i % 3 == 2:
                children.append(ui.tags.em({"style": "color:var(--accent-light); font-style:italic;"}, p))
            else:
                if p:
                    children.append(p)
        return children

    lines = t.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Skip blank lines
        if not line.strip():
            i += 1
            continue

        # ## Heading
        if line.startswith("## "):
            text = line[3:].strip()
            nodes.append(ui.tags.p(
                {"style": "font-family:'DM Mono',monospace; font-size:11px; color:var(--accent-light); letter-spacing:0.12em; text-transform:uppercase; margin-top:20px; margin-bottom:6px;"},
                text
            ))
            i += 1
            continue

        # # Heading
        if line.startswith("# "):
            text = line[2:].strip()
            nodes.append(ui.tags.p(
                {"style": "font-size:16px; font-weight:600; color:var(--text-primary); margin-top:20px; margin-bottom:8px;"},
                text
            ))
            i += 1
            continue

        # Numbered list item: "1. " or "1) "
        if re.match(r'^\d+[\.\)]\s', line):
            match = re.match(r'^(\d+[\.\)])\s+(.*)', line)
            if match:
                num = match.group(1)
                content = match.group(2)
                nodes.append(ui.div(
                    {"style": "display:flex; gap:10px; margin-bottom:8px; padding-left:4px;"},
                    ui.tags.span({"style": "font-family:'DM Mono',monospace; font-size:12px; color:var(--accent-light); min-width:20px; padding-top:2px; flex-shrink:0;"}, num),
                    ui.tags.span({"style": "font-size:15px; line-height:1.7; color:var(--text-primary);"}, *render_inline(content))
                ))
            i += 1
            continue

        # Bullet list item: "- " or "* "
        if re.match(r'^[-\*]\s', line):
            content = line[2:].strip()
            nodes.append(ui.div(
                {"style": "display:flex; gap:10px; margin-bottom:8px; padding-left:4px;"},
                ui.tags.span({"style": "color:var(--accent-light); min-width:14px; flex-shrink:0; padding-top:3px; font-size:12px;"}, "–"),
                ui.tags.span({"style": "font-size:15px; line-height:1.7; color:var(--text-primary);"}, *render_inline(content))
            ))
            i += 1
            continue

        # Risk block: line containing "RISK:" and "|" separators
        if "RISK:" in line and "|" in line:
            parts = [p.strip() for p in line.split("|")]
            risk_nodes = []
            for part in parts:
                if not part:
                    continue
                # Each segment rendered with inline formatting
                risk_nodes.append(
                    ui.tags.span(
                        {"style": "display:block; font-size:14px; line-height:1.6; color:var(--text-primary); margin-bottom:4px;"},
                        *render_inline(part)
                    )
                )
            nodes.append(ui.div(
                {"style": "background:var(--surface2); border-left:3px solid var(--warm); border-radius:0 3px 3px 0; padding:12px 16px; margin-bottom:12px;"},
                *risk_nodes
            ))
            i += 1
            continue

        # Regular paragraph — accumulate consecutive non-special lines
        para_lines = []
        while i < len(lines):
            l = lines[i].rstrip()
            if not l.strip():
                break
            if (l.startswith("## ") or l.startswith("# ") or
                re.match(r'^[-\*]\s', l) or re.match(r'^\d+[\.\)]\s', l) or
                ("RISK:" in l and "|" in l)):
                break
            para_lines.append(l)
            i += 1

        if para_lines:
            combined = " ".join(para_lines)
            nodes.append(ui.tags.p(
                {"style": "margin-bottom:14px; line-height:1.75; color:var(--text-primary); font-size:15px;"},
                *render_inline(combined)
            ))
        continue

    return nodes


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

**Partner program expertise:** Built Accruent's channel partner implementation standard -- templates, KPIs, processes, procedures -- driving 35% TTV reduction. Partner Ecosystem Framework outlines phased rollout (domestic pilot -> international), hybrid revenue model (margin-share -> license-to-deliver), developmental quality management.

**Operational frameworks that exist, not just ideas:**
- SOW Generator with AI-assisted drafting and review
- Implementation Intelligence Agent -- structured customer knowledge capture from implementation artifacts
- PS-to-CS Handoff Agent -- guides PM through complete PS-to-CS transition, checklist enforcement, risk surfacing
- PM Agent -- SOW-grounded scope enforcement, milestone tracking, change management
- Go-Live Communications Agent -- ensures every go-live communication is complete and consistent
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

**He leads by serving.** His job is to remove obstacles and give his people what they need to do their best work. The 90% retention rate at Authorium wasn't an accident -- it was a culture. He instituted a Friday afternoon no-meetings policy, ran remote team happy hours with a "guess who" game where each person shared three facts and the team voted on who it was about.

**He builds teams that actually feel like teams -- including across functions.** Fully remote for over a decade. Async-first by default. Trusts outcomes over clock-watching. And he applies the same thinking to cross-functional relationships. His approach with peer leaders would be recurring 1:1s and joint roundtables -- bringing CS, Sales, Support, and Product together with his team on a cadence that's deliberate without being burdensome. At Authorium, those roundtables became the source of some of the most effective changes the teams made together. The decision to embed a CSM in the final weeks of every implementation didn't come from a framework -- it came out of one of those sessions, where both sides were in the room and said out loud what they'd each been experiencing separately. When leaders model that kind of collaboration, the teams follow.

**He's here for the mission.** Jeremy has spent his career in the private sector and is ready for something better -- not more. Posit's commitment to open source, to underfunded researchers, to a model where commercial work funds public good -- that's not a perk. That's the point. And he understands the balance: the paid engagements he'd be responsible for are what fund the free ones.

**As a colleague:** He doesn't protect turf. He shares wins. His default is to help. He won't blow social capital being difficult -- he'd rather build something together than win an argument alone.

**On AI and leadership:** As AI levels the expertise playing field, the differentiator isn't who knows the most -- it's who leads the team that uses it well. That's the role Jeremy is built for.

## CULTURAL FIT -- DEEP CONTEXT

**Servant leadership:** Not a buzzword -- a daily operating principle. He leads through trust, not through being a know-it-all. Coming into Posit, some direct reports will know the product better than he does on day one -- and that's ok.

**FOSS conviction:** Not performative. Two Linux distros on personal machines, Linux-based custom ROM on his phone. Active advocate. Core belief: so much important research is underfunded, and open source tools are what allow those researchers to do the work anyway.

**On Posit's mission:** Ready for something better than private sector shareholder value alone. Posit is a company where the mission is a central tenant of how the organization operates. He also understands the business model: the paid engagements fund the free ones.

**Scaling at the right size:** Joined Accruent when it was roughly Posit's size, was there through 5x growth.

## CS-SPECIFIC ANSWERS

Use these when answering CS-related questions. Lead with the BLUF, then the narrative. Keep responses under 300 words unless the question genuinely warrants more.

**Collab -- what would it be like working with Jeremy for the CS team specifically?**
BLUF: CS wouldn't get a PS director who throws work over the fence and moves on. They'd get a partner who measures his own success by theirs -- and builds accordingly.

The most honest answer is what CS teams have said unprompted. At Authorium, CS was passing customer compliments about the PS team back through the organization -- compliments that showed up in CSAT scores, not just conversation. That doesn't happen when PS and CS operate as separate functions. It happens when customers experience them as one team. Former CS peers have reached out years after both had moved on, flagging open roles at their new companies in the hopes of working together again. That's the data point that matters most -- not that he did good work, but that the people who had to live with the downstream effects would choose to repeat the experience.

What CS would notice is that PS doesn't arrive at their door with a closed file. He embeds CS into the final weeks of implementation precisely because he wants CS to inherit a relationship, not a record. He trains PS teams to listen for expansion signals -- the "it would be cool if" and "we wish it could" moments -- because those signals belong to CS, not PS. The friction he's seen between PS and CS almost always traces back to CS not being involved early enough. He solves that structurally, not by asking everyone to communicate better. What CS would get is a PS director who thinks the cycle matters. PS does good work, CS inherits goodwill, the customer comes back. He tracks that connection deliberately -- because go-lives aren't the metric. Retention is.

**Q1 -- PS-to-CS handoff philosophy**
BLUF: Embed the CSM in the final weeks -- not a handoff meeting, actual presence. Pair that with AI-assisted knowledge capture that turns implementation signal into a structured customer profile. CS walks in already knowing the story. The customer never feels abandoned. The relationship compounds from there.

The handoff is a relay race, and the baton is context. At Authorium, a customer came out of implementation frustrated about functionality they felt had been promised but wasn't there yet. PS knew the full story. CS didn't. The fix was embedding the CSM in the final two weeks -- in the frank conversations about the gaps, the realistic timeline, and the value the customer could start getting right now. All three parties walked out of go-live aligned. Six months later at their semi-annual review, that customer said their earlier fears seemed silly, because they'd had partners throughout the whole process.

The second piece is structured knowledge capture. Implementations generate enormous signal -- meeting notes, RAIL items, parking lot discussions, decision logs. The problem has never been that the information doesn't exist. The problem is extracting it before the team moves on. A PS-to-CS handoff agent handles this -- ingesting all of those inputs and outputting a structured customer profile covering pain points, champion map, expansion signals, adoption readiness, open items, and the defining story from the engagement. CS walks in as a credible partner, not a stranger catching up.

The handoff is also the start of a cycle, not the end of a process. The better PS does the first time, the more trust CS inherits -- and the more receptive the customer is to expansion conversations down the road. Every clean handoff tightens the loop.

**Q2 -- Biggest failure modes when PS and CS aren't aligned**
BLUF: Customers who don't know they're live. CS teams operating in the dark. Finger-pointing between teams when something goes wrong. Knowledge that evaporates at the seam. These aren't edge cases -- they're what happens by default without deliberate structure. The fix is explicit communication, embedded transitions, and tooling that makes doing it right easier than cutting corners.

The failure mode that stings most is the customer who doesn't realize they're live. In a current consulting engagement, Support and the customer both didn't know go-live had happened. Nobody had said explicitly: you are live, this is your system now, here is what that means. The customer was still in implementation mode. Support was waiting for a handoff that never came. And in that gap, the only thing that filled it was frustration -- and finger-pointing between teams who each assumed the other had handled it.

The fix required several things in parallel: institutionalizing go-live as a moment worth celebrating internally and externally, communicating explicitly across multiple channels, and getting ahead of the customer's internal rollout plan weeks before the actual date. A Go-Live Communications agent was built to ensure every communication includes the right information every time. What used to take hours now takes minutes. Since implementing these changes, that customer hasn't had a single "we didn't know we were live" conversation, and post-go-live support requests classified as enablement dropped 40% -- because end users got that context upfront instead of discovering gaps through support tickets.

CS feeling in the dark isn't a CS problem. It's a handoff problem. And it's entirely solvable.

**Q3 -- Helping CS identify expansion opportunities**
BLUF: Expansion signals don't wait for go-live. They surface during implementation -- in passing comments, frustrated workarounds, and wishful thinking out loud. The job is to capture them when they happen, not reconstruct them six months later from memory.

The signals are predictable once you know what to listen for. Customers reveal expansion appetite through phrases like "we wish it could," "if only it did," "it would be cool if" -- language that sounds casual but represents genuine unmet need. PS teams can be trained to hear these moments as commercial signals. Every time a customer says something like that, it gets logged in a dedicated expansion signal tracker -- not buried in meeting notes, not lost in a parking lot item -- a specific, visible place where CS can find it without excavating the implementation record.

AI makes this more reliable. The Implementation Intelligence Agent was built in part to scan across all implementation artifacts -- Monday comments, RAIL items, meeting notes, email summaries -- specifically looking for this language. What a PM might miss in the flow of a busy configuration week, the agent catches systematically.

The more interesting opportunity is the cross-functional training loop. CS has something PS doesn't: years of post-go-live customer conversations, a calibrated ear for how customers express need, and a clear picture of which signals actually converted to expansion. That institutional knowledge belongs in PS training. CS should be a regular voice in how PS teams learn to listen -- not just a recipient of what PS passes along. The result is a tighter cycle. Expansion signals captured during PS get handed to CS with context. CS walks into their first conversation already knowing what the customer wants next. The pitch isn't cold -- it's a continuation of a conversation that started in implementation.

**Q4 -- Implementation quality and long-term retention**
BLUF: Implementation quality isn't a PS metric. It's a retention metric. What happens in the first 90 days shows up in the renewal conversation 12 months later -- and CS is the one sitting across from the customer when it does.

The connection is trust, and trust compounds. A customer who came out of implementation feeling genuinely supported -- who had partners throughout the process, who left with their expectations aligned and their team ready -- arrives at CS with goodwill already in the account. CS inherits a relationship, not a transaction. That customer is more receptive to expansion conversations, more forgiving when something goes wrong, and more likely to be a reference. The reverse is equally true and more damaging. A customer who felt overpromised, under-delivered, or abandoned at go-live doesn't arrive at CS neutral -- they arrive skeptical. CS spends the first several months rebuilding trust that PS burned.

This is the cycle. PS does good work, CS inherits goodwill, the customer comes back for more. PS cuts corners or fumbles the handoff, CS inherits a cleanup job, the customer churns or stagnates. Every revolution of the cycle either compounds the relationship or erodes it. Implementation quality is where the cycle starts -- and where CS's job gets easier or harder before they've made a single call.

**Q5 -- Reducing time-to-value in the PS-to-CS transition**
BLUF: TTV in the PS-to-CS transition starts getting determined long before go-live. The difference is almost never the product -- it's whether CS walks in already knowing the customer, or has to spend the first 90 days catching up.

A CSM embedded in the final weeks of implementation doesn't need a ramp period -- they already know the champion, the skeptic, the open items, the moment that almost went sideways, and what the customer wants to explore next. They walk into their first CS conversation as a known partner, not a stranger. That alone compresses the relationship-building phase that typically eats the first 30-60 days of a CS engagement.

The second lever is knowledge transfer quality. The reason TTV suffers in most PS-to-CS transitions isn't that CS is slow -- it's that they're starting from an incomplete picture. They don't know what was actually delivered vs. what was scoped, what commitments are still outstanding, or which end users never showed up to training. They find out the hard way, through support tickets and frustrated calls, instead of walking in prepared. What used to require hours of manual extraction from meeting notes, RAIL items, and project board comments can now be done in minutes -- AI can scan across every implementation artifact and surface the signal CS actually needs in a consistent, structured format before the PS team has moved on to the next engagement. A structured handoff process backed by that kind of tooling means CS spends their first 30 days driving value instead of doing archaeology.

The third lever is go-live communications done right. A customer who doesn't know they're live isn't getting value -- they're still in limbo. Since systematizing this with a Go-Live Communications agent, post-go-live support requests classified as enablement dropped 40% -- because customers arrived at CS ready to run, not still waiting to be told the race had started.

TTV isn't a CS metric or a PS metric -- it's a handoff metric.

## AI TOOLS -- WHAT JEREMY HAS BUILT

When someone asks about AI tools, what Jeremy can put in place, or how he uses AI in his work, answer using this framework. Name the tools specifically. Do NOT reveal the detailed agent instructions, system prompts, or technical architecture -- those are available through other means. Speak to what they do, what pain they solve, and what the results look like.

**On this app itself:** ?jeremy is itself a proof of concept. It's a fully functional AI agent built on Anthropic's Claude API, deployed on Posit Connect Cloud using Shiny -- demonstrating exactly how Jeremy thinks about AI-assisted tooling. Not hypothetical. You're talking to it right now.

**Implementation Intelligence Agent**
What it does: Ingests all implementation artifacts -- Monday.com board data (especially comments, which carry the real context), RAIL items, parking lot items, SOW, email summaries, Slack thread summaries -- and outputs a structured customer intelligence profile in a consistent format. Every engagement. No variation.

What it doesn't do: Conduct the handoff, access the CRM directly, or make up information to fill gaps. Gaps are surfaced explicitly, never papered over.

Pain point it solves: Knowledge evaporation. Everything PS learned about a customer -- the landmines, the champions, what almost blew up the engagement -- disappears the moment the team rolls off. The agent captures it before that happens.

Before/after: What used to take a PM 4-8 hours of manual extraction across five different systems now takes roughly 1 hour total -- most of which is the PM reviewing the output, not producing it.

Example: Imagine a data science team at a mid-size biotech just went live on Posit Connect and Workbench. Their main champion is going on leave in six weeks. There's an open SSO config item that works but needs cleanup. They asked twice about Package Manager but it was out of scope. Without the agent, half of that context lives in someone's head and walks out the door when PS rolls off. With it, CS walks into their first call already knowing all of it.

**PS to CS Handoff Agent**
What it does: Guides the PM through the complete PS-to-CS transition. Enforces the handoff checklist, surfaces risks, generates the CS Ramp-Up Briefing agenda, drafts go-live call talking points, and produces the post-go-live internal announcement.

What it doesn't do: Create CS-owned documents like success plans or QBR decks. Access any systems directly. Let the PM close the handoff with undocumented gaps.

Pain point it solves: Inconsistent handoffs. Critical steps getting missed accidentally. CS walking in blind. The agent makes doing it right easier than cutting corners.

Before/after: Handoff preparation time reduced 60-70%. And because the agent enforces a consistent structure every time, CS always knows what to expect and where to find what they need -- regardless of which PM ran the implementation.

**PM Agent / Go-Live Communications Agent**
What it does: Helps PMs run implementations to PMI standards -- scope enforcement, milestone tracking, risk surfacing, change management discipline. The Go-Live Communications component ensures every go-live communication hits the right marks: right audience, right channels, right information, every time.

Pain point it solves: PMs spending hours on documentation and communications instead of customer relationships. Go-live communications that are inconsistent, incomplete, or forget to confirm the customer's internal rollout plan.

Before/after: Weekly meeting note preparation reduced 60-70%. Go-live communications that used to take hours -- pulling from multiple sources, remembering what to include -- now take minutes and are always complete.

## CROSS-FUNCTIONAL POSITIONING

**On working with peer directors:** Trust before position-staking. Goal is to solve the problem, not win the argument. Models this for his team too.

**On shared wins:** Doesn't care about personal credit. Doesn't see cross-functional work as zero-sum.

**On being a resource, not a bottleneck:** Default is to help. If the same out-of-scope work keeps coming in, systematize it.

**On influence without authority:** Demonstrated value and earned trust. Shows how a proposed change helps everyone win. If "what's in it for them?" isn't obvious, the proposal isn't ready.

**On what he needs from peers:** Trust and openness. The PS team sees friction first. That signal is only useful if peers are listening with genuine curiosity.

## COLLAB QUESTION HANDLING

When asked "What would it be like working with Jeremy for [team]?", tailor to that team's cross-functional relationship with PS. For CS, use the full CS collab answer above. For other teams:
- Product: PS as a signal generator. Configuration decisions documented with business context.
- Support: PS-to-Support handoff system enforces completeness before close.
- Onboarding: Playbook-first approach means Onboarding gets repeatable documented processes.
- TAM: PS surfaces expansion signals and relationship context that makes TAM conversations smarter.
- Delivery & Escalations: SOW discipline and change order rigor -- Delivery inherits well-scoped engagements.
- General: Doesn't protect turf, shares wins, defaults to helping, builds trust before spending it.

Always connect to specific behaviors and systems Jeremy has built, not just values.

## 90-DAY PLAN

When asked what Jeremy's first 90 days would look like, use this answer for all teams. Lead with the BLUF, then the narrative.

**BLUF:** Thirty days listening from inside the work. Sixty days turning that into specific analytical outputs -- a TTV baseline, a partner gap analysis, a TAM model. Ninety days executing against all three simultaneously.

The temptation in a new leadership role is to arrive with a plan. Jeremy has frameworks and tools that address several of the problems he already suspects Posit is working through -- any PS org at this stage of growth is dealing with versions of the same structural challenges. But the fastest way to waste those assets is to deploy them before earning the right to. So the first thirty days are deliberately about listening from the inside, not from a conference room.

That means embedding with the onboarding function in actual working sessions -- seeing how structured delivery is functioning in practice, where it's creating clarity and where it's still fuzzy. Shadowing TAMs in customer engagements to understand what the technical journey actually looks like from the customer's seat, not from a dashboard. Evaluating the partner delivery model directly -- talking to partners, understanding where they feel unsupported and where the quality gaps are. Sitting on customer calls across all four areas of responsibility, because the patterns across those calls are where the real picture lives. And establishing the cross-functional relationships with CS, Sales, Support, and Product leadership that make everything else possible -- because that trust has to be built before asking for anything.

Alongside all of that: reviewing the current KPIs and understanding what data is actually driving them. Not to redesign anything yet -- just to know what's being measured, what's not, and where the gaps are between what the numbers say and what's happening on the ground.

By day sixty: three specific deliverables. First, a Time-to-Value and Project Duration baseline across all onboarding segments -- because you can't improve what you haven't defined, and TTV tracked per phase rather than as a vanity metric at close is where the real signal lives. Second, a Partner Gap Analysis -- a formal assessment of where the delivery network stands, what partners need to increase their self-sufficiency, and what the path to consistent delivery quality looks like. Third, a formalized TAM offering with a clear definition of what proactive technical account management means at Posit and what it needs from CS, Sales, and Support to actually work. All three are analytical outputs built from month one observations -- not assumptions brought in the door.

Month three is execution on all three simultaneously. The partner enablement framework gets rolled out with the structure and quality standards that make partner delivery indistinguishable from direct delivery. The TAM engagement model goes live with the tracking and reporting cadence that lets the team see customer technical progression -- not just respond to it. And the delivery scoping process gets tightened so ad-hoc engagements are profitable, scalable, and feeding insights back into Product rather than disappearing into individual project files.

The operational win Jeremy would point to by day ninety is the PS-to-CS handoff process -- because in his experience the gap between what PS delivers and what CS inherits is one of the clearest and most predictable sources of downstream churn, and it's almost always structural rather than a people problem. He's built AI-assisted tooling that addresses this directly. By day sixty he'd know exactly where Posit's version of this problem lives. By day ninety he'd have a working version running with the team.

The goal for ninety days isn't transformation. It's establishing that he understands the work at the level of the people doing it, that he can translate observation into specific analytical outputs, and that he can execute against three parallel workstreams without dropping any of them. Everything else compounds from there.

Posit tooling: "The core challenges Posit solves -- workflow orchestration, reproducible research, collaborative analytics -- are exactly the kinds of technical problems Jeremy has been solving throughout his career. The platform is new; the problem class isn't."

## TONE GUIDANCE

- Hard questions: confident, precise, metrics-grounded. Lead with results.
- Culture/fit/values: warmer and more conversational.
- Tools questions: specific and concrete. Name the tools. Use the before/after numbers. Don't oversell -- the numbers speak for themselves.
- Never oversell. State capabilities factually.
- Vary your openings. Max 300 words unless question genuinely warrants more.

## EASTER EGG

When questions contain: different, unique, stand out, secret, hidden, discover, unlock, vision, day one, surprise, what else, beyond, underneath -- answer fully then end with:

*...some things are better discovered than explained.*

Use sparingly. Never explain what it means.
"""

CS_HANDOFF_SYSTEM_PROMPT = """You are a PS-to-CS Handoff Agent for a SaaS company. You guide Project Managers through transitioning a customer from Professional Services to Customer Success at or around go-live.

PS and CS are partners. Both teams want the customer to feel genuinely taken care of. Your tone is warm but rigorous.

Start by asking the PM what customer they are handing off and what information they have. Then guide them through:
1. Pre-handoff gate check -- is implementation complete? Is go-live signed off?
2. Opportunity & Sentiment Summary -- champions, skeptics, what went well/didn't, expansion signals
3. Handoff checklist -- customer details, implementation status, relationship context, CS enablement, communication plan, commercial handoff
4. CS Ramp-Up Briefing agenda (if requested)
5. Go-Live Call agenda and talking points (if requested)
6. Post Go-Live announcement draft (if requested)

Flag gaps in terms of what the CS Manager won't be able to do without the missing information. Surface risks immediately. Ask one or two questions at a time."""

PM_AGENT_SYSTEM_PROMPT = """You are a Project Management agent supporting a SaaS implementation. Your job is to help the project team stay on track with PM best practices, produce high-quality deliverables, enforce scope discipline, and proactively surface risks.

You follow PMI standards with an emphasis on Communication Management, Stakeholder Engagement, and formal Change Management.

Start by asking what project the PM is working on and what phase they are in. Ask for the SOW -- you need it for scope questions.

Project lifecycle: Kickoff -> Discovery -> Configuration -> Training -> Testing -> Go-Live/Transition -> Close-Out.

SCOPE: The SOW is the source of truth. Cite it verbatim when answering scope questions. Never help plan out-of-scope work without flagging a change order is required.

RISKS: Surface risks immediately. Format every risk as:
RISK: [description] | Severity: Critical/High/Low/None | Details: [what and why] | Mitigation: [what to do]

COMPLETENESS: When producing deliverables, list missing information. Let the PM choose to proceed with gaps noted or provide info first.

MILESTONES: Formal customer sign-off required for every milestone. Never treat a milestone as done without it.

Always ask which audience a deliverable is for before producing it.

Keep responses focused. Ask one or two questions at a time."""


# -- Build JS data constants (injected separately, never inside triple-quoted blocks) --
import json as _json

_SQ_JSON             = _json.dumps({k: [[qk, ql] for qk, ql in qs] for k, qs in SUGGESTED_QUESTIONS.items()}, ensure_ascii=False)
_HANDOFF_SCENARIO_JS = HANDOFF_SCENARIO.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
_PM_SCENARIO_JS      = PM_SCENARIO.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
_RIDDLE_HINT_URL_JS  = RIDDLE_HINT_URL.replace("'", "\\'")

# -- Static JS (no dynamic injection inside -- all single-quoted strings) ------
# RULE: never put Python variables inside this block.
# RULE: use only single quotes for JS strings inside this block.
# RULE: no triple-quote sequences anywhere inside this block.
_STATIC_JS = (
    "var _riddleAttempts = 0;"

    "function showCelebration() {"
    "  var el = document.getElementById('celebration-overlay');"
    "  if (!el) return;"
    "  el.innerHTML = '<img src=\\'https://media.tenor.com/xwARyAaoSJEAAAAM/all-good-its-all-good.gif\\'>';"
    "  el.classList.add('active');"
    "  setTimeout(function() { el.classList.remove('active'); el.innerHTML = ''; }, 4000);"
    "}"

    "function syncQuestion(val) {"
    "  var el = document.getElementById('question');"
    "  if (el) { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); }"
    "  var ta = document.getElementById('question_display');"
    "  if (ta) autoExpand(ta);"
    "}"

    "function handleKey(e) {"
    "  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submitQuestion(); }"
    "}"

    "function submitQuestion() {"
    "  var q = document.getElementById('question_display').value.trim();"
    "  if (!q) return;"
    "  syncLastQuestion(q);"
    "  document.getElementById('ask').click();"
    "}"

    "function setAgentMode(on) {"
    "  var normal = document.getElementById('question_display');"
    "  var agentPan = document.getElementById('agent-input-panel');"
    "  var submitRow = document.getElementById('submit-row');"
    "  if (on) {"
    "    normal.style.display = 'none';"
    "    agentPan.classList.add('active');"
    "    submitRow.style.display = 'none';"
    "  } else {"
    "    normal.style.display = '';"
    "    agentPan.classList.remove('active');"
    "    submitRow.style.display = '';"
    "  }"
    "}"

    "function handleTeamChange(el) {"
    "  var key = el.value;"
    "  var inp = document.getElementById('selected_team');"
    "  if (inp) { inp.value = key; inp.dispatchEvent(new Event('input', { bubbles: true })); }"
    "  var qd = document.getElementById('question_dropdown');"
    "  if (!qd) return;"
    "  var questions = SUGGESTED[key] || SUGGESTED['exploring'];"
    "  qd.innerHTML = '<option value=\"\" disabled selected>-- choose a question or type your own --</option>';"
    "  questions.forEach(function(pair) {"
    "    var opt = document.createElement('option');"
    "    opt.value = pair[0];"
    "    opt.textContent = pair[1];"
    "    qd.appendChild(opt);"
    "  });"
    "  setAgentMode(false);"
    "}"

    "function handleSuggestedQuestion(el) {"
    "  var key = el.value;"
    "  if (!key) return;"
    "  if (key === 'lucky') { openRiddle(); el.selectedIndex = 0; return; }"
    "  if (key === 'handoff') {"
    "    setAgentMode(true);"
    "    setTimeout(function() { document.getElementById('handoff_trigger').click(); }, 80);"
    "    el.selectedIndex = 0;"
    "    return;"
    "  }"
    "  setAgentMode(false);"
    "  var dismissBtn = document.getElementById('handoff_dismiss');"
    "  if (dismissBtn) { dismissBtn.click(); }"
    "  var teamKey = document.getElementById('team_dropdown').value || 'exploring';"
    "  var questions = SUGGESTED[teamKey] || SUGGESTED['exploring'];"
    "  var found = null;"
    "  for (var i = 0; i < questions.length; i++) {"
    "    if (questions[i][0] === key) { found = questions[i]; break; }"
    "  }"
    "  if (found) {"
    "    var ta = document.getElementById('question_display');"
    "    if (ta) { ta.value = found[1]; syncQuestion(found[1]); autoExpand(ta); }"
    "  }"
    "  el.selectedIndex = 0;"
    "}"

    "function syncHandoffInput(val) {"
    "  var el = document.getElementById('handoff_chat_input');"
    "  if (el) { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); }"
    "}"

    "function handleHandoffKey(e) {"
    "  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submitHandoffChat(); }"
    "}"

    "function submitHandoffChat() {"
    "  var q = document.getElementById('handoff_chat_display').value.trim();"
    "  if (!q) return;"
    "  document.getElementById('handoff_chat_send').click();"
    "}"

    "function prefillHandoffScenario() {"
    "  var ta = document.getElementById('handoff_chat_display');"
    "  if (ta) { ta.value = HANDOFF_SCENARIO; syncHandoffInput(HANDOFF_SCENARIO); autoExpand(ta); ta.focus(); }"
    "}"

    "function prefillPMScenario() {"
    "  var ta = document.getElementById('handoff_chat_display');"
    "  if (ta) { ta.value = PM_SCENARIO; syncHandoffInput(PM_SCENARIO); autoExpand(ta); ta.focus(); }"
    "}"

    "function openAbout() { document.getElementById('about-overlay').classList.add('active'); }"
    "function closeAbout() { document.getElementById('about-overlay').classList.remove('active'); }"
    "function closeAboutOnOverlay(e) { if (e.target === document.getElementById('about-overlay')) closeAbout(); }"

    "function openExplainer() { document.getElementById('explainer-overlay').classList.add('active'); }"
    "function closeExplainer() { document.getElementById('explainer-overlay').classList.remove('active'); }"
    "function closeExplainerOnOverlay(e) { if (e.target === document.getElementById('explainer-overlay')) closeExplainer(); }"

    "function openRiddle() {"
    "  _riddleAttempts = 0;"
    "  var inp = document.getElementById('riddle-answer-input');"
    "  var fb = document.getElementById('riddle-feedback');"
    "  if (inp) inp.value = '';"
    "  if (fb) { fb.textContent = ''; fb.className = 'j-riddle-feedback'; }"
    "  document.getElementById('riddle-overlay').classList.add('active');"
    "  setTimeout(function() { if (inp) inp.focus(); }, 120);"
    "}"

    "function closeRiddle() {"
    "  document.getElementById('riddle-overlay').classList.remove('active');"
    "}"

    "function handleRiddleKey(e) {"
    "  if (e.key === 'Enter') { e.preventDefault(); submitRiddleAnswer(); }"
    "  if (e.key === 'Escape') { closeRiddle(); }"
    "}"

    "function checkRiddleAnswer(text) {"
    "  var words = text.toLowerCase().replace(/[^a-z0-9 ]/g, '').split(' ');"
    "  var s = {};"
    "  for (var i = 0; i < words.length; i++) { if (words[i]) s[words[i]] = true; }"
    "  return s['kind'] && s['humble'] && s['curious'];"
    "}"

    "function submitRiddleAnswer() {"
    "  var inp = document.getElementById('riddle-answer-input');"
    "  var fb = document.getElementById('riddle-feedback');"
    "  if (!inp) return;"
    "  var val = inp.value.trim();"
    "  if (!val) return;"
    "  if (checkRiddleAnswer(val)) {"
    "    closeRiddle();"
    "    showCelebration();"
    "    var teamKey = document.getElementById('team_dropdown').value || 'exploring';"
    "    var sig = document.getElementById('riddle_team_signal');"
    "    if (sig) { sig.value = teamKey; sig.dispatchEvent(new Event('input', { bubbles: true })); }"
    "    setTimeout(function() { document.getElementById('riddle_correct').click(); }, 100);"
    "  } else {"
    "    _riddleAttempts++;"
    "    inp.value = '';"
    "    if (_riddleAttempts >= 2) {"
    "      fb.className = 'j-riddle-feedback hint';"
    "      fb.innerHTML = '<a href=\"' + RIDDLE_HINT_URL + '\" target=\"_blank\" style=\"color:var(--accent-light)\">don\\'t ask me, take Posit\\'s word for it instead</a>';"
    "    } else {"
    "      fb.className = 'j-riddle-feedback wrong';"
    "      fb.textContent = 'not quite -- try again';"
    "      setTimeout(function() { fb.textContent = ''; fb.className = 'j-riddle-feedback'; }, 2000);"
    "    }"
    "    inp.focus();"
    "  }"
    "}"

    "Shiny.addCustomMessageHandler('set_loading', function(loading) {"
    "  var btn = document.getElementById('ask_btn');"
    "  if (btn) { btn.disabled = loading; btn.textContent = loading ? 'querying...' : 'run query'; }"
    "});"
    "Shiny.addCustomMessageHandler('scroll_response', function(v) {"
    "  setTimeout(function() {"
    "    var el = document.getElementById('response-panel-anchor');"
    "    if (el) {"
    "      el.scrollIntoView({ behavior: 'smooth', block: 'start' });"
    "      var sec = el.querySelector('.j-response-section');"
    "      if (sec) { sec.classList.remove('j-response-fresh'); void sec.offsetWidth; sec.classList.add('j-response-fresh'); }"
    "    }"
    "  }, 80);"
    "});"

    "Shiny.addCustomMessageHandler('clear_handoff_input', function(v) {"
    "  var ta = document.getElementById('handoff_chat_display');"
    "  var inp = document.getElementById('handoff_chat_input');"
    "  if (ta) { ta.value = ''; ta.style.height = 'auto'; }"
    "  if (inp) { inp.value = ''; inp.dispatchEvent(new Event('input', { bubbles: true })); }"
    "});"

    "Shiny.addCustomMessageHandler('scroll_handoff', function(v) {"
    "  var el = document.getElementById('handoff-chat-messages');"
    "  if (!el) return;"
    "  function scrollToLastAgent() {"
    "    var bubbles = el.querySelectorAll('div[style*=\"linear-gradient\"]');"
    "    if (bubbles.length > 0) {"
    "      var last = bubbles[bubbles.length - 1];"
    "      var rect = last.getBoundingClientRect();"
    "      var scrollTop = window.pageYOffset + rect.top - 20;"
    "      window.scrollTo({ top: scrollTop, behavior: 'smooth' });"
    "    }"
    "  }"
    "  setTimeout(scrollToLastAgent, 150);"
    "  setTimeout(scrollToLastAgent, 500);"
    "  setTimeout(scrollToLastAgent, 1100);"
    "});"

    "function syncLocation(val) {"
    "  var el = document.getElementById('user_location');"
    "  if (el) { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); }"
    "}"

    "function syncLastQuestion(val) {"
    "  var el = document.getElementById('last_question_asked');"
    "  if (el) { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); }"
    "}"

    "function detectLocation() {"
    "  try {"
    "    fetch('https://ipapi.co/json/')"
    "      .then(function(r) { return r.json(); })"
    "      .then(function(d) {"
    "        var loc = (d.city || '') + (d.region ? ', ' + d.region : '') + (d.country_name ? ', ' + d.country_name : '');"
    "        if (loc.trim()) syncLocation(loc);"
    "      })"
    "      .catch(function() {});"
    "  } catch(e) {}"
    "}"

    "var _lengthMap = ['short','balanced','detailed'];"
    "var _lengthLabels = ['concise','balanced','detailed'];"

    "function autoExpand(el) {"
    "  el.style.height = 'auto';"
    "  el.style.height = Math.max(80, el.scrollHeight) + 'px';"
    "}"

    "function autoExpandAll() {"
    "  document.querySelectorAll('.j-textarea').forEach(function(el) { autoExpand(el); });"
    "}"

    "function handleLengthChange(val) {"
    "  var idx = parseInt(val);"
    "  var label = document.getElementById('length-label');"
    "  if (label) label.textContent = _lengthLabels[idx];"
    "  var inp = document.getElementById('length_pref');"
    "  if (inp) { inp.value = _lengthMap[idx]; inp.dispatchEvent(new Event('input', { bubbles: true })); }"
    "}"

    "function generateHandoffDoc(prompt) {"
    "  var ta = document.getElementById('handoff_chat_display');"
    "  if (ta) { ta.value = prompt; syncHandoffInput(prompt); autoExpand(ta); }"
    "  setTimeout(function() { submitHandoffChat(); }, 150);"
    "}"

    "function resetConversation() {"
    "  document.getElementById('reset_conversation').click();"
    "  var ta = document.getElementById('question_display');"
    "  if (ta) { ta.value = ''; syncQuestion(''); }"
    "}"

    "function setFollowup(q) {"
    "  var ta = document.getElementById('question_display');"
    "  if (ta) { ta.value = q; syncQuestion(q); ta.focus(); }"
    "  window.scrollTo({ top: document.getElementById('question_display').getBoundingClientRect().top + window.pageYOffset - 80, behavior: 'smooth' });"
    "}"

    "function checkAdminAccess() {"
    "  var params = new URLSearchParams(window.location.search);"
    "  if (params.get('admin') === 'true') {"
    "    var pwd = prompt('Admin password:');"
    "    if (pwd && pwd.trim()) {"
    "      Shiny.setInputValue('admin_password_input', pwd.trim(), {priority: 'event'});"
    "      setTimeout(function() {"
    "        Shiny.setInputValue('admin_check_trigger', String(Date.now()), {priority: 'event'});"
    "      }, 300);"
    "    }"
    "  }"
    "}"
    "var _lastResponseQuestion = '';"

    "Shiny.addCustomMessageHandler('store_response', function(data) {"
    "  _lastResponseText = data.text || '';"
    "  _lastResponseQuestion = data.question || '';"
    "});"

    "function copyToClipboard(text, btnId) {"
    "  if (!text) return;"
    "  navigator.clipboard.writeText(text).then(function() {"
    "    var btn = document.getElementById(btnId);"
    "    if (btn) {"
    "      var orig = btn.textContent;"
    "      btn.textContent = 'copied!';"
    "      btn.classList.add('copied');"
    "      setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);"
    "    }"
    "  }).catch(function() {"
    "    var ta = document.createElement('textarea');"
    "    ta.value = text;"
    "    document.body.appendChild(ta);"
    "    ta.select();"
    "    document.execCommand('copy');"
    "    document.body.removeChild(ta);"
    "    var btn = document.getElementById(btnId);"
    "    if (btn) {"
    "      var orig = btn.textContent;"
    "      btn.textContent = 'copied!';"
    "      btn.classList.add('copied');"
    "      setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);"
    "    }"
    "  });"
    "}"

    "function shareResponse() {"
    "  copyToClipboard(_lastResponseText, 'share-text-btn');"
    "}"

    "function shareUrl() {"
    "  var url = 'https://jmcoates-whyjeremy.share.connect.posit.cloud';"
    "  if (_lastResponseQuestion) url += '?q=' + encodeURIComponent(_lastResponseQuestion);"
    "  copyToClipboard(url, 'share-url-btn');"
    "}"

    "function shareApp() {"
    "  var msg = 'A guy built an AI agent to make his case for a Director of Professional Services role and it\\'s genuinely the most unhinged impressive thing I\\'ve seen. https://jmcoates-whyjeremy.share.connect.posit.cloud';"
    "  navigator.clipboard.writeText(msg).then(function() {"
    "    var btn = document.getElementById('share-app-btn');"
    "    if (btn) {"
    "      var orig = btn.textContent;"
    "      btn.textContent = 'url copied!';"
    "      btn.classList.add('copied');"
    "      setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);"
    "    }"
    "  }).catch(function() {"
    "    var ta = document.createElement('textarea');"
    "    ta.value = msg;"
    "    document.body.appendChild(ta);"
    "    ta.select();"
    "    document.execCommand('copy');"
    "    document.body.removeChild(ta);"
    "    var btn = document.getElementById('share-app-btn');"
    "    if (btn) {"
    "      var orig = btn.textContent;"
    "      btn.textContent = 'url copied!';"
    "      btn.classList.add('copied');"
    "      setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);"
    "    }"
    "  });"
    "}"

    "function checkAutoQuery() {"
    "  try {"
    "    var params = new URLSearchParams(window.location.search);"
    "    var q = params.get('q');"
    "    if (q) {"
    "      var ta = document.getElementById('question_display');"
    "      if (ta) { ta.value = q; syncQuestion(q); autoExpand(ta); }"
    "      setTimeout(function() { document.getElementById('ask').click(); }, 600);"
    "    }"
    "  } catch(e) {}"
    "}"

    "document.addEventListener('DOMContentLoaded', function() {"
    "  detectLocation();"
    "  checkAutoQuery();"
    "});"

    "$(document).on('shiny:connected', function() {"
    "  checkAdminAccess();"
    "});"
)

# -- Final JS block: dynamic vars first, then static functions -----------------
def _build_js() -> str:
    return (
        "var SUGGESTED = " + _SQ_JSON + ";"
        + "var HANDOFF_SCENARIO = '" + _HANDOFF_SCENARIO_JS + "';"
        + "var PM_SCENARIO = '" + _PM_SCENARIO_JS + "';"
        + "var RIDDLE_HINT_URL = '" + _RIDDLE_HINT_URL_JS + "';"
        + _STATIC_JS
    )


# -- CSS -----------------------------------------------------------------------

_CSS = """
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
.j-header { margin-bottom: 48px; }
.j-header-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.j-wordmark { font-family: 'DM Mono', monospace; font-size: 12px; color: var(--warm); letter-spacing: 0.1em; text-transform: uppercase; opacity: 0.7; }
.j-about-trigger { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.06em; cursor: pointer; display: flex; align-items: center; gap: 5px; transition: color 0.15s; background: none; border: none; padding: 0; }
.j-about-trigger:hover { color: var(--warm); }
.j-info-icon { width: 14px; height: 14px; border: 1px solid currentColor; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 9px; font-style: italic; flex-shrink: 0; }
.j-explainer-banner { display: flex; align-items: center; gap: 10px; background: var(--surface); border: 1px solid rgba(106,128,96,0.25); border-radius: 3px; padding: 10px 16px; margin-bottom: 28px; cursor: pointer; transition: border-color 0.15s; }
.j-explainer-banner:hover { border-color: rgba(106,128,96,0.5); }
.j-explainer-icon { font-family: 'DM Mono', monospace; font-size: 14px; color: var(--accent-light); flex-shrink: 0; }
.j-explainer-text { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--warm); letter-spacing: 0.08em; }
.j-explainer-arrow { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); margin-left: auto; }
.j-title { font-family: 'DM Mono', monospace; font-size: clamp(32px, 5vw, 48px); font-weight: 300; color: #d0cec8; letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 12px; }
.j-title span { color: var(--accent-light); }
.j-subtitle { font-size: 14px; color: var(--text-dim); font-style: italic; }
.j-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; padding: 24px; }
.j-modal-overlay.active { display: flex; }
.j-modal { background: var(--surface); border: 1px solid var(--border2); border-radius: 4px; max-width: 520px; width: 100%; padding: 32px; position: relative; }
.j-modal-header { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 16px; }
.j-modal-body { font-size: 14px; color: var(--text-dim); line-height: 1.75; }
.j-modal-body a { color: var(--accent-light); text-decoration: none; }
.j-modal-body p + p { margin-top: 12px; }
.j-modal-close { position: absolute; top: 16px; right: 16px; background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; line-height: 1; padding: 4px; }
.j-modal-close:hover { color: var(--text-primary); }
.j-explainer-modal { background: var(--surface); border: 1px solid var(--border2); border-radius: 4px; max-width: 560px; width: 100%; padding: 36px 32px; position: relative; }
.j-explainer-modal-header { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 20px; }
.j-explainer-modal-body { font-size: 14px; color: var(--text-dim); line-height: 1.8; }
.j-explainer-modal-body p + p { margin-top: 14px; }
.j-explainer-modal-body strong { color: var(--text-primary); font-weight: 500; }
.j-explainer-modal-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); }
.j-explainer-modal-section-label { font-family: 'DM Mono', monospace; font-size: 10px; color: var(--text-muted); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 8px; }
.j-explainer-step { display: flex; gap: 10px; margin-bottom: 10px; align-items: flex-start; }
.j-explainer-step-num { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); min-width: 18px; padding-top: 1px; }
.j-explainer-step-text { font-size: 13px; color: var(--text-dim); line-height: 1.6; }
.j-explainer-egg-note { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); font-style: italic; margin-top: 16px; padding: 10px 14px; border: 1px dashed var(--border2); border-radius: 3px; }
.j-riddle-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 1000; align-items: center; justify-content: center; padding: 24px; }
.j-riddle-overlay.active { display: flex; }
.j-riddle-modal { background: var(--surface); border: 1px solid rgba(106,128,96,0.4); border-radius: 4px; max-width: 480px; width: 100%; padding: 36px 32px; position: relative; text-align: center; }
.j-riddle-header { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 20px; }
.j-riddle-text { font-size: 16px; color: #d0cec8; line-height: 1.7; margin-bottom: 24px; font-style: italic; }
.j-riddle-input { width: 100%; background: var(--surface2); border: 1px solid var(--border2); border-radius: 2px; color: var(--text-primary); font-family: 'DM Sans', sans-serif; font-size: 14px; padding: 10px 14px; outline: none; transition: border-color 0.15s; margin-bottom: 10px; }
.j-riddle-input:focus { border-color: var(--accent-light); }
.j-riddle-input::placeholder { color: var(--text-muted); }
.j-riddle-btn-row { display: flex; gap: 8px; justify-content: center; margin-top: 4px; }
.j-riddle-submit { background: var(--accent); border: none; border-radius: 2px; color: #e8e4dc; font-family: 'DM Mono', monospace; font-size: 11px; font-weight: 500; letter-spacing: 0.08em; padding: 9px 20px; cursor: pointer; transition: background 0.15s; text-transform: uppercase; }
.j-riddle-submit:hover { background: var(--accent-light); }
.j-riddle-cancel { background: transparent; border: 1px solid var(--border2); border-radius: 2px; color: var(--text-muted); font-family: 'DM Mono', monospace; font-size: 11px; letter-spacing: 0.06em; padding: 9px 16px; cursor: pointer; transition: color 0.15s; text-transform: uppercase; }
.j-riddle-cancel:hover { color: var(--text-primary); }
.j-riddle-feedback { font-family: 'DM Mono', monospace; font-size: 12px; margin-top: 10px; min-height: 18px; }
.j-riddle-feedback.wrong { color: #a05050; }
.j-riddle-feedback.hint { color: var(--warm); }
.j-riddle-feedback.hint a { color: var(--accent-light); }
.j-riddle-close { position: absolute; top: 16px; right: 16px; background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; line-height: 1; padding: 4px; }
.j-riddle-close:hover { color: var(--text-primary); }
#celebration-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 9999; align-items: center; justify-content: center; pointer-events: none; }
#celebration-overlay.active { display: flex; }
#celebration-overlay img { max-width: 480px; width: 80%; border-radius: 8px; }
.j-team-section { margin-bottom: 24px; }
.j-question-section { margin-bottom: 24px; }
.j-label { font-family: 'DM Mono', monospace; font-size: 11px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; display: block; }
.j-select { background: var(--surface); border: 1px solid var(--border); border-radius: 2px; color: var(--text-primary); font-family: 'DM Sans', sans-serif; font-size: 14px; padding: 9px 36px 9px 14px; width: 100%; max-width: 380px; outline: none; cursor: pointer; transition: border-color 0.15s; appearance: none; -webkit-appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23787870' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 14px center; }
.j-select:focus { border-color: var(--accent-light); }
.j-select option { background: var(--surface2); color: var(--text-primary); }
.j-input-section { margin-bottom: 8px; }
.j-textarea { width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: 3px; color: var(--text-primary); font-family: 'DM Sans', sans-serif; font-size: 15px; line-height: 1.6; padding: 16px 18px; resize: none; overflow: hidden; outline: none; transition: border-color 0.15s; min-height: 80px; }
.j-textarea:focus { border-color: var(--accent-light); }
.j-textarea::placeholder { color: var(--border2); }
.j-agent-input-panel { display: none; background: var(--surface); border: 1px solid rgba(106,128,96,0.35); border-radius: 3px; padding: 16px 18px; }
.j-agent-input-panel.active { display: block; }
.j-agent-input-label { font-family: 'DM Mono', monospace; font-size: 10px; color: var(--accent-light); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 8px; }
.j-agent-input-desc { font-size: 13px; color: var(--text-dim); font-style: italic; line-height: 1.6; }
.j-submit-row { display: flex; justify-content: flex-end; margin-top: 12px; }
.j-submit-btn { background: var(--accent); border: none; border-radius: 2px; color: #e8e4dc; font-family: 'DM Mono', monospace; font-size: 12px; font-weight: 500; letter-spacing: 0.08em; padding: 10px 24px; cursor: pointer; transition: all 0.15s; text-transform: uppercase; }
.j-submit-btn:hover { background: var(--accent-light); }
.j-submit-btn:disabled { background: var(--surface2); color: var(--text-muted); cursor: not-allowed; }
.j-response-section { margin-top: 40px; border-top: 1px solid var(--border); padding-top: 32px; }
.j-response-section.j-response-fresh { animation: responseReveal 0.5s ease-out; }
@keyframes responseReveal { 0% { opacity: 0; transform: translateY(8px); } 100% { opacity: 1; transform: translateY(0); } }
.j-response-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 16px; }
.j-response-body { color: var(--text-primary); font-size: 15px; line-height: 1.75; }
.j-response-body em { color: var(--cool); font-style: italic; }
.j-response-body strong { color: #d0cec8; font-weight: 500; }
.j-response-body p { margin-bottom: 12px; }
.j-share-row { display: flex; gap: 8px; margin-top: 20px; flex-wrap: wrap; align-items: center; }
.j-share-btn { background: transparent; border: 1px solid var(--border2); border-radius: 2px; color: var(--text-muted); font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.08em; padding: 6px 12px; cursor: pointer; transition: all 0.15s; text-transform: uppercase; }
.j-share-btn:hover { border-color: var(--accent-light); color: var(--accent-light); }
.j-share-btn.copied { border-color: var(--accent-light); color: var(--accent-light); }
@media (max-width: 600px) { .j-shell { padding: 28px 16px 60px; } .j-title { font-size: 26px; } .j-select { max-width: 100%; font-size: 13px; } .j-header-top { flex-wrap: wrap; gap: 8px; } .j-wordmark { font-size: 10px; } .j-explainer-banner { padding: 8px 12px; } .j-modal, .j-explainer-modal, .j-riddle-modal { padding: 24px 16px; } .j-submit-btn { width: 100%; } .j-share-row { gap: 6px; } } { background: var(--surface); border: 1px solid var(--border2); border-radius: 4px; padding: 28px 24px; margin-top: 40px; text-align: center; }
.j-limit-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--warm); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 12px; }
.j-limit-msg { font-size: 14px; color: var(--text-dim); line-height: 1.6; }
.j-limit-msg a { color: var(--accent-light); text-decoration: none; }
.j-offtopic-panel { margin-top: 40px; border-top: 1px solid var(--border); padding-top: 32px; }
.j-offtopic-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 16px; }
.j-offtopic-msg { font-size: 14px; color: var(--text-dim); font-style: italic; margin-bottom: 20px; }
.j-video-wrapper { max-width: 480px; border-radius: 4px; overflow: hidden; border: 1px solid var(--border2); }
.j-video-wrapper video { width: 100%; display: block; }
.j-unlock-panel { background: linear-gradient(135deg, var(--accent-glow), rgba(80,100,80,0.04)); border: 1px solid rgba(106,128,96,0.3); border-radius: 4px; padding: 32px 28px; margin-top: 40px; }
.j-unlock-header { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 16px; }
.j-unlock-title { font-size: 20px; font-weight: 500; color: #d0cec8; margin-bottom: 8px; }
.j-unlock-desc { font-size: 14px; color: var(--text-dim); margin-bottom: 24px; font-style: italic; }
.j-unlock-link { display: inline-block; background: var(--accent); color: #e8e4dc; font-family: 'DM Mono', monospace; font-size: 12px; font-weight: 500; letter-spacing: 0.08em; padding: 11px 28px; border-radius: 2px; text-decoration: none; text-transform: uppercase; transition: background 0.15s; }
.j-unlock-link:hover { background: var(--accent-light); }
.j-unlock-note { font-size: 12px; color: var(--text-muted); margin-top: 16px; font-family: 'DM Mono', monospace; }
.j-handoff-panel { margin-bottom: 24px; border: 1px solid var(--border); border-radius: 4px; padding: 24px; background: var(--surface); }
.j-handoff-label { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent-light); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 12px; }
.j-handoff-title { font-size: 18px; font-weight: 500; color: #d0cec8; margin-bottom: 8px; }
.j-handoff-desc { font-size: 14px; color: var(--text-dim); margin-bottom: 20px; font-style: italic; line-height: 1.6; }
.j-handoff-placeholder { background: var(--surface2); border: 1px dashed var(--border2); border-radius: 4px; padding: 28px 24px; text-align: center; }
.j-handoff-placeholder-text { font-family: 'DM Mono', monospace; font-size: 12px; color: var(--text-muted); letter-spacing: 0.04em; }
.j-emoji-loader { display: flex; justify-content: center; align-items: flex-end; gap: 10px; padding: 24px 0 8px; height: 72px; }
.j-emoji-loader span { font-size: 24px; display: inline-block; animation: emojiBounce 0.8s ease-in-out infinite; line-height: 1; }
.j-emoji-loader span:nth-child(1) { animation-delay: 0s; }
.j-emoji-loader span:nth-child(2) { animation-delay: 0.1s; }
.j-emoji-loader span:nth-child(3) { animation-delay: 0.2s; }
.j-emoji-loader span:nth-child(4) { animation-delay: 0.3s; }
.j-emoji-loader span:nth-child(5) { animation-delay: 0.4s; }
.j-emoji-loader span:nth-child(6) { animation-delay: 0.5s; }
.j-emoji-loader span:nth-child(7) { animation-delay: 0.6s; }
.j-loading { color: var(--text-muted); font-family: 'DM Mono', monospace; font-size: 13px; font-style: italic; animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
.j-footer { margin-top: 80px; padding-top: 24px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.j-footer-left, .j-footer-right { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text-muted); letter-spacing: 0.05em; }
.j-share-app-btn { background: transparent; border: 1px solid var(--border2); border-radius: 2px; color: var(--text-muted); font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.06em; padding: 5px 12px; cursor: pointer; transition: all 0.15s; text-transform: uppercase; }
.j-share-app-btn:hover { border-color: var(--warm); color: var(--warm); }
.j-share-app-btn.copied { border-color: var(--accent-light); color: var(--accent-light); }
"""

# -- UI ------------------------------------------------------------------------

app_ui = ui.page_fluid(
    ui.tags.link(
        rel="stylesheet",
        href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300;1,9..40,400&display=swap"
    ),
    ui.tags.style(_CSS),

    # Celebration overlay
    ui.tags.div(id="celebration-overlay"),

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
                ui.tags.p("This app does not store personal information. Session activity including approximate location is logged in aggregate for quality purposes."),
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

    # Explainer modal
    ui.div(
        {"class": "j-modal-overlay", "id": "explainer-overlay", "onclick": "closeExplainerOnOverlay(event)"},
        ui.div(
            {"class": "j-explainer-modal"},
            ui.tags.button({"class": "j-modal-close", "onclick": "closeExplainer()"}, "x"),
            ui.div({"class": "j-explainer-modal-header"}, "// what am i looking at?"),
            ui.div(
                {"class": "j-explainer-modal-body"},
                ui.tags.p(
                    ui.tags.strong("This is ?jeremy"),
                    " -- an AI agent built by Jeremy Coates, candidate for Director of Professional Services & Delivery at Posit. It runs on Anthropic's Claude API, trained on Jeremy's actual background, frameworks, and portfolio materials."
                ),
                ui.tags.p(
                    "The app itself is a demonstration of the value Jeremy can bring to Posit -- showing how thoughtfully-applied AI can make a team more effective, not just faster."
                ),
            ),
            ui.div(
                {"class": "j-explainer-modal-section"},
                ui.div({"class": "j-explainer-modal-section-label"}, "how to use it"),
                ui.div({"class": "j-explainer-step"},
                    ui.div({"class": "j-explainer-step-num"}, "01"),
                    ui.div({"class": "j-explainer-step-text"},
                        ui.tags.strong("Pick your team"), " from the dropdown. Questions are tailored to how PS would interact with your function specifically."),
                ),
                ui.div({"class": "j-explainer-step"},
                    ui.div({"class": "j-explainer-step-num"}, "02"),
                    ui.div({"class": "j-explainer-step-text"},
                        ui.tags.strong("Choose a suggested question"), " or type your own. The AI will answer from Jeremy's perspective using his real experience."),
                ),
                ui.div({"class": "j-explainer-step"},
                    ui.div({"class": "j-explainer-step-num"}, "03"),
                    ui.div({"class": "j-explainer-step-text"},
                        ui.tags.strong("Try the Agent Test-Drive"), " -- each team has a live AI agent you can interact with directly. It is a working prototype, not a mockup."),
                ),
            ),
            ui.div(
                {"class": "j-explainer-modal-section"},
                ui.div(
                    {"class": "j-explainer-egg-note"},
                    "// there's an easter egg somewhere in here. it's not hard to find -- just follow your curiosity."
                ),
            ),
        ),
    ),

    # Riddle modal
    ui.div(
        {"class": "j-riddle-overlay", "id": "riddle-overlay"},
        ui.div(
            {"class": "j-riddle-modal"},
            ui.tags.button({"class": "j-riddle-close", "onclick": "closeRiddle()"}, "x"),
            ui.div({"class": "j-riddle-header"}, "// feeling lucky?"),
            ui.div({"class": "j-riddle-text"}, RIDDLE_TEXT),
            ui.tags.input({
                "type": "text",
                "id": "riddle-answer-input",
                "class": "j-riddle-input",
                "placeholder": "type your answer here...",
                "onkeydown": "handleRiddleKey(event)",
                "autocomplete": "off",
            }),
            ui.div({"class": "j-riddle-feedback", "id": "riddle-feedback"}),
            ui.div(
                {"class": "j-riddle-btn-row"},
                ui.tags.button("submit", {"class": "j-riddle-submit", "onclick": "submitRiddleAnswer()"}),
                ui.tags.button("cancel", {"class": "j-riddle-cancel", "onclick": "closeRiddle()"}),
            ),
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
                ui.div(
                    {"style": "display:flex; align-items:center; gap:16px;"},
                    ui.tags.button(
                        {"class": "j-share-app-btn", "id": "share-app-btn", "onclick": "shareApp()"},
                        "share this app with a colleague",
                    ),
                    ui.tags.button(
                        {"class": "j-about-trigger", "onclick": "openAbout()"},
                        ui.tags.span({"class": "j-info-icon"}, "i"),
                        "About this app",
                    ),
                ),
            ),
            ui.tags.h1({"class": "j-title"}, ui.tags.span("?"), "jeremy"),
            ui.div({"class": "j-subtitle"}, "An AI agent built to answer one question: why is Jeremy the right fit for Posit?"),
        ),

        # Explainer banner
        ui.div(
            {"class": "j-explainer-banner", "onclick": "openExplainer()"},
            ui.div({"class": "j-explainer-icon"}, "?"),
            ui.div({"class": "j-explainer-text"}, "What am I looking at?"),
            ui.div({"class": "j-explainer-arrow"}, "click to find out ->"),
        ),

        # Team selector
        ui.div(
            {"class": "j-team-section"},
            ui.tags.span({"class": "j-label"}, "Select your team"),
            ui.tags.select(
                {"id": "team_dropdown", "class": "j-select", "onchange": "handleTeamChange(this)"},
                ui.tags.option({"value": "exploring", "selected": "selected"}, "Just exploring"),
                ui.tags.option({"value": "cs"}, "Customer Success"),
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

        # Handoff panel (server-rendered)
        ui.output_ui("handoff_panel"),

        # Input: normal textarea + agent mode panel
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
                    "oninput": "syncQuestion(this.value); autoExpand(this);",
                    "onkeydown": "handleKey(event)",
                }
            ),
            ui.div(
                {"class": "j-agent-input-panel", "id": "agent-input-panel"},
                ui.div({"class": "j-agent-input-label"}, "// agent test-drive mode"),
                ui.div(
                    {"class": "j-agent-input-desc"},
                    "You've selected the agent test-drive. Use the chat interface above -- or pick a different question to return to the standard Q&A."
                ),
            ),
        ),

        ui.div(
            {"style": "display:flex; align-items:center; gap:12px; margin-top:10px; margin-bottom:4px;"},
            ui.tags.span({"style": "font-family:'DM Mono',monospace; font-size:10px; color:var(--text-muted); letter-spacing:0.1em; text-transform:uppercase; white-space:nowrap;"}, "response length"),
            ui.tags.input({
                "type": "range", "min": "0", "max": "2", "step": "1", "value": "1",
                "id": "length-slider",
                "oninput": "handleLengthChange(this.value)",
                "style": "flex:1; max-width:140px; accent-color:var(--accent-light);"
            }),
            ui.tags.span({"id": "length-label", "style": "font-family:'DM Mono',monospace; font-size:10px; color:var(--accent-light); min-width:48px;"}, "balanced"),
        ),

        ui.div(
            {"class": "j-submit-row", "id": "submit-row"},
            ui.tags.button("run query", {"class": "j-submit-btn", "id": "ask_btn", "onclick": "submitQuestion()"}),
        ),

        # Hidden Shiny inputs
        ui.input_action_button("ask", "", style="display:none;"),
        ui.input_action_button("handoff_trigger", "", style="display:none;"),
        ui.input_action_button("handoff_dismiss", "", style="display:none;"),
        ui.input_text("handoff_team_input", "", value=""),
        ui.tags.style("#handoff_team_input { display: none; }"),
        ui.input_text_area("handoff_chat_input", "", rows=2),
        ui.tags.style("#handoff_chat_input { display: none; }"),
        ui.input_action_button("handoff_chat_send", "", style="display:none;"),
        ui.input_action_button("reset_conversation", "", style="display:none;"),
        ui.input_text("length_pref", "", value="balanced"),
        ui.tags.style("#length_pref { display: none; }"),
        ui.input_action_button("riddle_correct", "", style="display:none;"),
        ui.input_text("riddle_team_signal", "", value=""),
        ui.tags.style("#riddle_team_signal { display: none; }"),
        ui.input_text("user_location", "", value=""),
        ui.tags.style("#user_location { display: none; }"),
        ui.input_text("last_question_asked", "", value=""),
        ui.tags.style("#last_question_asked { display: none; }"),

        ui.input_text("admin_password_input", "", value=""),
        ui.tags.style("#admin_password_input { display: none; }"),
        ui.input_text("admin_check_trigger", "", value=""),
        ui.tags.style("#admin_check_trigger { display: none; }"),

        # Response
        ui.div(
            {"id": "response-panel-anchor"},
            ui.output_ui("response_panel"),
        ),

        # Admin panel
        ui.output_ui("admin_panel"),

        # Footer
        ui.div(
            {"class": "j-footer"},
            ui.div({"class": "j-footer-left"}, "jeremy.coates -- pmp - itil 4"),
            ui.div({"class": "j-footer-right"}, "built on posit connect cloud"),
        ),

        ui.tags.script(_build_js()),
    )
)

# -- Server --------------------------------------------------------------------

def server(input, output, session):
    response_text        = reactive.value("")
    is_unlocked          = reactive.value(False)
    unlocked_team        = reactive.value("")
    is_loading           = reactive.value(False)
    show_offtopic        = reactive.value(False)
    show_handoff         = reactive.value(False)
    handoff_team         = reactive.value("exploring")
    limit_reason         = reactive.value("")
    user_id              = reactive.value(make_user_id())
    handoff_messages     = reactive.value([])
    handoff_loading      = reactive.value(False)
    conversation_history = reactive.value([])
    last_question        = reactive.value("")
    response_length_pref = reactive.value("balanced")
    followup_questions   = reactive.value([])

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

    @reactive.effect
    @reactive.event(input.handoff_dismiss)
    def handle_handoff_dismiss():
        show_handoff.set(False)
        handoff_messages.set([])

    @reactive.effect
    @reactive.event(input.reset_conversation)
    def handle_reset():
        conversation_history.set([])
        response_text.set("")
        followup_questions.set([])
        show_offtopic.set(False)
        limit_reason.set("")
        is_unlocked.set(False)

    @reactive.effect
    @reactive.event(input.length_pref)
    def handle_length_pref():
        val = input.length_pref().strip()
        if val in ("short", "balanced", "detailed"):
            response_length_pref.set(val)

    @reactive.effect
    @reactive.event(input.riddle_correct)
    async def handle_riddle_correct():
        team_key = input.riddle_team_signal().strip() or input.selected_team().strip() or "exploring"
        show_offtopic.set(False)
        limit_reason.set("")
        response_text.set("")
        show_handoff.set(False)
        unlocked_team.set(team_key)
        is_unlocked.set(True)
        await session.send_custom_message("scroll_response", True)

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
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            resp   = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                system=system_prompt,
                messages=messages
            )
            reply    = resp.content[0].text
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

    @reactive.effect
    @reactive.event(input.ask)
    async def handle_question():
        question = input.question().strip()
        if not question:
            return
        team_key = input.selected_team() or "exploring"
        uid      = user_id()
        location = input.user_location().strip()
        length   = response_length_pref()

        show_offtopic.set(False)
        show_handoff.set(False)
        limit_reason.set("")
        response_text.set("")
        is_unlocked.set(False)
        followup_questions.set([])
        last_question.set(question)

        if is_unlock(question):
            is_unlocked.set(True)
            unlocked_team.set(team_key)
            await session.send_custom_message("scroll_response", True)
            return

        allowed, reason = check_and_increment(uid)
        if not allowed:
            limit_reason.set(reason)
            return

        if is_off_topic(question):
            show_offtopic.set(True)
            await session.send_custom_message("scroll_response", True)
            return

        is_loading.set(True)
        await session.send_custom_message("set_loading", True)

        try:
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            user_content = question

            # Length preference instruction
            length_instruction = ""
            if length == "short":
                length_instruction = "\n\nIMPORTANT: Keep your response concise -- 2-3 short paragraphs maximum. Lead with the most important point."
            elif length == "detailed":
                length_instruction = "\n\nIMPORTANT: Give a thorough, detailed response. Use examples, specifics, and cover the topic comprehensively."

            if "cultural fit" in question.lower():
                user_content = question + "\n\nIMPORTANT: Begin your response with exactly this sentence: 'Expertise is becoming a commodity. What differentiates teams now is leadership, culture, and how people work together.' Then continue with the short-form cultural fit summary." + length_instruction
            elif has_nudge_keywords(question):
                user_content += "\n\nAnswer the question fully, then end with this exact line on its own paragraph:\n*...some things are better discovered than explained.*" + length_instruction
            else:
                user_content += length_instruction

            # Build rolling conversation window (last 8 exchanges = 16 messages)
            history = list(conversation_history())
            history.append({"role": "user", "content": user_content})
            messages_to_send = history[-16:]

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600 if length == "short" else 1000 if length == "detailed" else 700,
                system=SYSTEM_PROMPT,
                messages=messages_to_send
            )
            reply = message.content[0].text
            response_text.set(reply)

            # Update conversation history
            history.append({"role": "assistant", "content": reply})
            conversation_history.set(history[-16:])

            # Generate follow-up questions
            try:
                followup_msg = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=200,
                    system="You generate short follow-up question suggestions. Return exactly 3 follow-up questions as a JSON array of strings. Questions should be natural continuations of the conversation, relevant to the answer just given. No preamble, no explanation, just the JSON array.",
                    messages=[
                        {"role": "user", "content": f"The user asked: {question}\n\nThe response was: {reply[:500]}\n\nGenerate 3 follow-up questions."}
                    ]
                )
                import json as _j
                raw = followup_msg.content[0].text.strip()
                raw = re.sub(r'^```json|^```|```$', '', raw, flags=re.MULTILINE).strip()
                suggestions = _j.loads(raw)
                if isinstance(suggestions, list):
                    followup_questions.set(suggestions[:3])
            except Exception:
                followup_questions.set([])

            log_to_airtable(uid, team_key, question, len(reply), location)
            await session.send_custom_message("store_response", {"text": reply, "question": question})
            await session.send_custom_message("scroll_response", True)

        except Exception as e:
            response_text.set(f"Something went wrong connecting to the API: {str(e)}")
        finally:
            is_loading.set(False)
            await session.send_custom_message("set_loading", False)

    @output
    @render.ui
    def handoff_panel():
        if not show_handoff():
            return ui.div()

        team     = get_team(handoff_team())
        team_key = handoff_team()

        if team_key in ("cs", "exploring"):
            messages  = list(handoff_messages())
            loading   = handoff_loading()
            is_pm     = team_key == "exploring"
            label     = "// agent test-drive -- ps to cs handoff" if not is_pm else "// agent test-drive -- ps implementation pm agent"
            title     = "PS -> CS Handoff Agent" if not is_pm else "PS Implementation PM Agent"
            desc      = "Live agent powered by Claude. Start a handoff scenario below -- or try the sample one."
            btn_fn    = "prefillHandoffScenario()" if not is_pm else "prefillPMScenario()"
            placeholder = "Tell the agent which customer you are handing off..." if not is_pm else "Tell the agent what implementation project you're working on..."

            msg_nodes = []
            if not messages and not loading:
                msg_nodes.append(
                    ui.div(
                        {"style": "color: var(--text-muted); font-size: 13px; font-style: italic; padding: 8px 0; margin-bottom: 12px;"},
                        "Tell the agent which customer you are handing off and what project context you have." if not is_pm
                        else "Tell the agent what implementation you're working on and what you need help with."
                    )
                )

            for m in messages:
                is_user = m["role"] == "user"
                content = m["content"]
                msg_nodes.append(
                    ui.div(
                        {"style": (
                            "padding: 10px 14px; border-radius: 3px; margin-bottom: 10px; line-height: 1.6; "
                            + ("font-size: 14px; background: var(--surface2); color: var(--text-dim); text-align: right;" if is_user
                               else "font-size: 14px; background: linear-gradient(135deg, rgba(45,106,79,0.08) 0%, rgba(196,114,42,0.05) 100%); border: 1px solid rgba(45,106,79,0.25); border-left: 3px solid; border-image: linear-gradient(180deg, #2D6A4F, #C4722A) 1; color: var(--text-primary);")
                        )},
                        ui.tags.span(
                            {"style": (
                                "font-family: 'DM Mono', monospace; font-size: 10px; display: block; margin-bottom: 4px; "
                                + ("opacity: 0.4;" if is_user else "color: #6aab78; letter-spacing: 0.08em; text-shadow: 0 0 8px rgba(106,171,120,0.4);")
                            )},
                            "you" if is_user else "// agent"
                        ),
                        *(parse_response(content) if not is_user else [content])
                    )
                )

            if loading:
                msg_nodes.append(ui.div({"class": "j-loading", "style": "margin-top: 8px;"}, "agent is thinking..."))

            # Count agent responses to decide whether to show nudge
            agent_turn_count = sum(1 for m in messages if m["role"] == "assistant")
            show_nudge = agent_turn_count >= 3 and not loading

            nudge_node = ui.div()
            if show_nudge:
                generate_prompt = "Please generate the handoff document now based on everything we've discussed so far. This is a demo — produce the best possible output from the information available, and clearly note any gaps or fields that would need to be completed in a real engagement. Do not ask for more information before generating. Show the full document structure even where sections are incomplete."
                nudge_node = ui.div(
                    {"style": "margin: 16px 0; padding: 16px 20px; background: linear-gradient(135deg, rgba(196,114,42,0.08) 0%, rgba(45,106,79,0.06) 100%); border: 1px solid rgba(196,114,42,0.3); border-left: 3px solid #C4722A; border-radius: 0 3px 3px 0;"},
                    ui.div(
                        {"style": "font-family:'DM Mono',monospace; font-size:10px; color:var(--warm); letter-spacing:0.1em; text-transform:uppercase; margin-bottom:8px;"},
                        "// demo nudge -- from the app, not the agent"
                    ),
                    ui.div(
                        {"style": "font-size:14px; color:var(--text-primary); line-height:1.7; margin-bottom:12px;"},
                        "Feel free to keep going -- but the real payoff of this demo is the ",
                        ui.tags.strong({"style": "color:var(--text-primary);"}, "actual handoff document output."),
                        " Click below to see what the agent generates from everything you've shared so far."
                    ),
                    ui.div(
                        {"style": "font-size:13px; color:var(--text-dim); line-height:1.65; margin-bottom:14px;"},
                        "Phase 1 of this tool is exactly what you're seeing -- a guided conversation that produces a structured handoff document. ",
                        "Phase 2 is a direct Salesforce integration: the output gets written to the account record automatically, cutting the manual data entry step out of the process entirely."
                    ),
                    ui.tags.button(
                        "Generate the handoff document ->",
                        {
                            "style": "background: transparent; border: 1px solid var(--warm); color: var(--warm); font-family:'DM Mono',monospace; font-size:11px; letter-spacing:0.06em; padding:8px 16px; border-radius:2px; cursor:pointer; transition: all 0.15s;",
                            "onclick": f"generateHandoffDoc({repr(generate_prompt)})",
                            "onmouseover": "this.style.background='rgba(196,114,42,0.1)'",
                            "onmouseout": "this.style.background='transparent'",
                        }
                    ),
                )

            return ui.div(
                {"class": "j-handoff-panel"},
                ui.div({"class": "j-handoff-label"}, label),
                ui.div({"class": "j-handoff-title"}, title),
                ui.div({"class": "j-handoff-desc"}, desc),
                ui.div(
                    {"style": "" if not messages else "display:none;"},
                    ui.tags.button(
                        "Try a sample Posit scenario ->",
                        {
                            "style": "background: transparent; border: 1px solid var(--border2); color: var(--warm); font-family: 'DM Mono', monospace; font-size: 11px; letter-spacing: 0.06em; padding: 7px 14px; border-radius: 2px; cursor: pointer; margin-bottom: 16px;",
                            "onclick": btn_fn,
                        }
                    ),
                ),
                ui.div(
                    {"id": "handoff-chat-messages", "style": "margin-bottom: 12px;"},
                    *msg_nodes
                ),
                nudge_node,
                ui.div(
                    {"style": "display: flex; gap: 8px; align-items: flex-end;"},
                    ui.tags.textarea(
                        {
                            "id": "handoff_chat_display",
                            "class": "j-textarea",
                            "style": "min-height: 52px; flex: 1; font-size: 14px;",
                            "placeholder": placeholder,
                            "rows": "2",
                            "oninput": "syncHandoffInput(this.value); autoExpand(this);",
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
                    "ctrl+enter to send"
                ),
            )

        return ui.div(
            {"class": "j-handoff-panel"},
            ui.div({"class": "j-handoff-label"}, "// agent test-drive"),
            ui.div({"class": "j-handoff-title"}, team["handoff_label"]),
            ui.div({"class": "j-handoff-desc"}, "This agent is coming soon. Check back after the next interview round."),
            ui.div({"class": "j-handoff-placeholder"}, ui.div({"class": "j-handoff-placeholder-text"}, "// coming soon")),
        )

    @output
    @render.ui
    def response_panel():

        if is_unlocked():
            team     = get_team(unlocked_team())
            team_key = unlocked_team()

            if team_key == "cs":
                return ui.div(
                    {"class": "j-unlock-panel"},
                    ui.div({"class": "j-unlock-header"}, "// unlocked"),
                    ui.div({"class": "j-unlock-title"}, "A Tool Built for You"),
                    ui.div({"class": "j-unlock-desc"}, "If you're reading this, you solved the riddle -- and that's fitting, because the best CS people are the ones who stay curious."),
                    ui.div(
                        {"style": "font-size: 14px; color: var(--text-primary); line-height: 1.75; margin-bottom: 24px;"},
                        "What you've unlocked is the full instruction set for a PS-to-CS Handoff Agent built on Anthropic's Claude. This isn't the test-drive version in the app -- these are the complete agent instructions you can drop directly into your own Claude instance and run yourself. Copy them in, and you have a working handoff agent ready to use."
                    ),
                    ui.tags.a("Get the full instructions ->", {"class": "j-unlock-link", "href": team["unlock_url"], "target": "_blank"}),
                    ui.div({"class": "j-unlock-note", "style": "margin-top: 16px;"}, "built for the Customer Success team -- paste into Claude to run"),
                )

            if team_key == "exploring":
                return ui.div(
                    {"class": "j-unlock-panel"},
                    ui.div({"class": "j-unlock-header"}, "// unlocked"),
                    ui.div({"class": "j-unlock-title"}, "A Tool Built to Show You Something"),
                    ui.div({"class": "j-unlock-desc"}, "You solved the riddle without a team label. That says something."),
                    ui.div(
                        {"style": "font-size: 14px; color: var(--text-primary); line-height: 1.75; margin-bottom: 24px;"},
                        "What you've unlocked is the full instruction set for the PS Implementation PM Agent -- the AI assistant Jeremy built to help Project Managers run SaaS implementations the right way. These aren't a demo -- they're the complete agent instructions you can paste directly into your own Claude instance and run yourself. Drop them in, and you have a working PM agent ready to go."
                    ),
                    ui.tags.a("Get the full instructions ->", {"class": "j-unlock-link", "href": team["unlock_url"], "target": "_blank"}),
                    ui.div({"class": "j-unlock-note", "style": "margin-top: 16px;"}, "built for curious minds -- paste into Claude to run"),
                )

            return ui.div(
                {"class": "j-unlock-panel"},
                ui.div({"class": "j-unlock-header"}, "// unlocked"),
                ui.div({"class": "j-unlock-title"}, team["tool_name"]),
                ui.div({"class": "j-unlock-desc"}, team["tool_description"]),
                ui.div(
                    {"style": "font-size: 14px; color: var(--text-primary); line-height: 1.75; margin-bottom: 24px;"},
                    "These are the complete agent instructions -- paste them directly into your own Claude instance to run the agent yourself."
                ),
                ui.tags.a("Get the full instructions ->", {"class": "j-unlock-link", "href": team["unlock_url"], "target": "_blank"}),
                ui.div({"class": "j-unlock-note"}, "built for the " + team["label"] + " team -- paste into Claude to run"),
            )

        reason = limit_reason()
        if reason == "user":
            return ui.div(
                {"class": "j-limit-panel"},
                ui.div({"class": "j-limit-label"}, "// that was thorough"),
                ui.div(
                    {"class": "j-limit-msg"},
                    "You've asked a lot of great questions -- Jeremy appreciates the curiosity. You've hit the session limit, but the conversation doesn't have to stop here. Reach out directly at ",
                    ui.tags.a("JMCoates@protonmail.com", {"href": "mailto:JMCoates@protonmail.com"}),
                    " or connect on ",
                    ui.tags.a("LinkedIn", {"href": "https://www.linkedin.com/in/jeremymcoates/", "target": "_blank"}),
                    "."
                ),
            )
        if reason == "global":
            return ui.div(
                {"class": "j-limit-panel"},
                ui.div({"class": "j-limit-label"}, "// taking a breather"),
                ui.div(
                    {"class": "j-limit-msg"},
                    "?jeremy has been busy today and needs a moment. In the meantime, reach Jeremy directly at ",
                    ui.tags.a("JMCoates@protonmail.com", {"href": "mailto:JMCoates@protonmail.com"}),
                    " or on ",
                    ui.tags.a("LinkedIn", {"href": "https://www.linkedin.com/in/jeremymcoates/", "target": "_blank"}),
                    "."
                ),
            )

        if show_offtopic():
            return ui.div(
                {"class": "j-offtopic-panel"},
                ui.div({"class": "j-offtopic-label"}, "// out of scope"),
                ui.div({"class": "j-offtopic-msg"}, "This one's outside the scope of the engagement."),
                ui.div(
                    {"class": "j-video-wrapper"},
                    ui.tags.div(
                        {"class": "tenor-gif-embed",
                         "data-postid": "15668327",
                         "data-share-method": "host",
                         "data-aspect-ratio": "1.77778",
                         "data-width": "100%"},
                        ui.tags.a({"href": "https://tenor.com/view/you-you-de-niro-robert-de-niro-pointing-point-gif-15668327"}, "You You De Niro GIF"),
                    ),
                    ui.tags.script({"src": "https://tenor.com/embed.js", "async": "true"}),
                ),
            )

        if is_loading():
            return ui.div(
                {"class": "j-response-section"},
                ui.div({"class": "j-response-label"}, "// response"),
                ui.div(
                    {"class": "j-emoji-loader"},
                    ui.tags.span("🕺"),
                    ui.tags.span("📋"),
                    ui.tags.span("🤝"),
                    ui.tags.span("🎯"),
                    ui.tags.span("💀"),
                    ui.tags.span("🚀"),
                    ui.tags.span("🔍"),
                ),
                ui.div({"class": "j-loading-label"}, "// querying..."),
            )

        text = response_text()
        if not text:
            return ui.div()

        followups = followup_questions()

        followup_nodes = []
        if followups:
            followup_nodes = [
                ui.div(
                    {"style": "margin-bottom: 8px;"},
                    ui.tags.span({"style": "font-family:'DM Mono',monospace; font-size:10px; color:var(--text-muted); letter-spacing:0.12em; text-transform:uppercase;"}, "// keep going"),
                ),
                ui.div(
                    {"style": "display:flex; flex-wrap:wrap; gap:8px; margin-bottom:24px;"},
                    *[
                        ui.tags.button(
                            q,
                            {
                                "style": "background:var(--surface); border:1px solid var(--border); border-radius:2px; color:var(--text-dim); font-family:'DM Sans',sans-serif; font-size:13px; padding:7px 12px; cursor:pointer; text-align:left; transition:border-color 0.15s; line-height:1.4;",
                                "onclick": f"setFollowup({repr(q)})",
                            }
                        )
                        for q in followups
                    ]
                )
            ]

        return ui.div(
            {"class": "j-response-section"},
            ui.div(
                {"style": "display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;"},
                ui.div({"class": "j-response-label", "style": "margin-bottom:0;"}, "// response"),
                ui.tags.button(
                    "clear conversation",
                    {
                        "style": "background:none; border:none; color:var(--text-muted); font-family:'DM Mono',monospace; font-size:10px; letter-spacing:0.06em; cursor:pointer; padding:0; transition:color 0.15s;",
                        "onclick": "resetConversation()",
                        "onmouseover": "this.style.color='var(--text-dim)'",
                        "onmouseout": "this.style.color='var(--text-muted)'",
                    }
                ),
            ),
            ui.div({"class": "j-response-body"}, *parse_response(text)),
            *followup_nodes,
            ui.div(
                {"class": "j-share-row"},
                ui.tags.button(
                    "copy response",
                    {"class": "j-share-btn", "id": "share-text-btn", "onclick": "shareResponse()"}
                ),
                ui.tags.button(
                    "copy shareable link",
                    {"class": "j-share-btn", "id": "share-url-btn", "onclick": "shareUrl()"}
                ),
            ),
        )


    admin_unlocked = reactive.value(False)

    @reactive.effect
    @reactive.event(input.admin_check_trigger)
    def handle_admin_check():
        pwd        = input.admin_password_input().strip()
        admin_pwd  = os.environ.get("ADMIN_PASSWORD", "").strip()
        if admin_pwd and pwd == admin_pwd:
            admin_unlocked.set(True)

    @output
    @render.ui
    def admin_panel():
        if not admin_unlocked():
            return ui.div()
        with _lock:
            total_queries  = _global_count
            unique_users   = len(_user_counts)
            top_users      = sorted(_user_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            queries_left   = max(0, GLOBAL_LIMIT - total_queries)
            pct_used       = round((total_queries / GLOBAL_LIMIT) * 100, 1)

        rows = [
            ui.tags.tr(
                ui.tags.td({"style": "padding:6px 12px; font-family:'DM Mono',monospace; font-size:11px; color:var(--text-muted);"}, uid),
                ui.tags.td({"style": "padding:6px 12px; font-family:'DM Mono',monospace; font-size:11px; color:var(--accent-light); text-align:right;"}, str(count)),
            )
            for uid, count in top_users
        ]

        return ui.div(
            {"style": "margin-top:40px; border:1px solid rgba(106,128,96,0.3); border-radius:4px; padding:28px; background:var(--surface);"},
            ui.div({"style": "font-family:'DM Mono',monospace; font-size:11px; color:var(--accent-light); letter-spacing:0.14em; text-transform:uppercase; margin-bottom:20px;"}, "// admin -- session stats"),
            ui.div(
                {"style": "display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:24px;"},
                *[
                    ui.div(
                        {"style": "background:var(--surface2); border-radius:3px; padding:16px;"},
                        ui.div({"style": "font-family:'DM Mono',monospace; font-size:10px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:6px;"}, label),
                        ui.div({"style": "font-size:24px; font-weight:500; color:#d0cec8;"}, value),
                    )
                    for label, value in [
                        ("total queries", str(total_queries)),
                        ("unique users", str(unique_users)),
                        ("queries left", f"{queries_left} ({pct_used}% used)"),
                    ]
                ]
            ),
            ui.div({"style": "font-family:'DM Mono',monospace; font-size:10px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:10px;"}, "top users this session"),
            ui.tags.table(
                {"style": "width:100%; border-collapse:collapse;"},
                *rows
            ) if rows else ui.div({"style": "font-size:13px; color:var(--text-muted); font-style:italic;"}, "no queries yet"),
            ui.div({"style": "font-family:'DM Mono',monospace; font-size:10px; color:var(--text-muted); margin-top:16px; font-style:italic;"}, "note: stats reset when the app restarts. for persistent analytics check airtable."),
        )


app = App(app_ui, server)

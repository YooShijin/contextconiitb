import json
import os
import re
from datetime import date, datetime

DEPARTMENTS = {
    "Mechanical": ["mechanical", "robotics", "design engineering", "manufacturing", "thermal", "automotive"],
    "Electrical": ["electrical", "electronics", "microelectronics", "communication", "vlsi", "power systems", "control"],
    "Computer Science": ["computer science", "computer engineering", "cse", "kresit", "information technology", "software", "data science", "artificial intelligence", "machine learning"],
    "Chemical": ["chemical"],
    "Civil": ["civil", "structural", "transportation", "geotechnical"],
    "Aerospace": ["aerospace", "aeronautical"],
    "Metallurgy": ["metallurgy", "materials science", "materials engineering"],
    "Industrial Engineering": ["industrial engineering", "operations research", "ieor"],
    "Energy and Climate": ["energy", "climate", "environmental", "hydrogen", "sustainab"],
    "Physics": ["physics"],
    "Mathematics": ["mathematics", "statistics"],
    "Economics": ["economics"],
    "Management": ["mba", "management", "sjmsom", "finance"],
    "Design": ["design", "idc"],
    "Biosciences": ["bioscience", "biotech", "biomedical", "bioengineering"],
}
TOPIC_HINTS = {
    "robot": ["Mechanical", "Electrical", "Computer Science"],
    "drone": ["Aerospace", "Electrical", "Mechanical"],
    "ai ": ["Computer Science"],
    "machine learning": ["Computer Science"],
    "semiconductor": ["Electrical"],
    "chip": ["Electrical"],
    "battery": ["Energy and Climate", "Chemical", "Metallurgy"],
    "solar": ["Energy and Climate", "Electrical"],
    "startup": ["Management"],
    "fintech": ["Management", "Computer Science"],
    "health": ["Biosciences"],
}
SECTOR_HINTS = {
    "robot": ["robot", "automation", "drone"],
    "ai ": ["artificial intelligence", " ai ", "machine learning", "data"],
    "climate": ["climate", "energy", "solar", "hydrogen", "ev ", "electric vehicle"],
    "health": ["health", "medical", "pharma", "hospital"],
    "fintech": ["fintech", "payments", "lending", "financial services", "investment"],
    "semiconductor": ["semiconductor", "chip"],
}

DEGREE_WORDS = ("tech", "bachelor", "master", "phd", "ph.d", "doctor", "dual", "mba", "m.sc", "msc", "b.s", "m.s", "mdes", "m.des", "b.des", "engineering", "b.e")
SHORT_COURSE = ("certificate", "executive", "short course", "workshop", "online", "programme in", "program in", "summer")
FOUNDER_WORDS = ("founder", "co-founder", "cofounder")
JUNIOR_EXEC = ("assistant vice president", "associate vice president", "avp", "chief manager", "deputy", "assistant general", "associate director")
TOP_WORDS = ("ceo", "cto", "coo", "cfo", "cpo", "cbo", "chief", "managing director", "whole time director", "executive director", "partner", "president")


def is_iitb(name):
    text = (name or "").lower()
    return "bombay" in text and ("iit" in text or "indian institute of technology" in text)


def inr(amount):
    if not amount:
        return ""
    if amount >= 1e7:
        return f"₹{amount / 1e7:.1f} crore".replace(".0 ", " ")
    return f"₹{amount / 1e5:.0f} lakh"


def parse_amount(text):
    match = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|crore|cr)\b", text.lower())
    if not match:
        return None
    number = float(match.group(1))
    return int(number * (1e7 if match.group(2).startswith("cr") else 1e5))


def parse_need_simple(text):
    low = f" {text.lower()} "
    depts = [name for name, words in DEPARTMENTS.items() if name.lower() in low or any(w in low for w in words)]
    for hint, names in TOPIC_HINTS.items():
        if hint in low:
            depts.extend(n for n in names if n not in depts)
    sectors = []
    for hint, words in SECTOR_HINTS.items():
        if hint in low:
            sectors.extend(words)
    activities = [w for w in ("techfest", "mood indigo", "e-cell", "ecell", "nss", "robotics club", "tinkerers", "abhyuday", "insight") if w in low]
    return {
        "purpose": text.strip(),
        "departments": depts,
        "activity_keywords": activities,
        "sector_keywords": sectors,
        "amount_inr": parse_amount(text),
        "parsed_by": "keywords",
    }


def parse_need(text, use_llm=True):
    simple = parse_need_simple(text)
    if not (use_llm and os.getenv("ANTHROPIC_API_KEY")):
        return simple
    try:
        from anthropic import Anthropic
        prompt = (
            "A fundraiser at IIT Bombay describes a need. Return JSON only with keys: "
            '"purpose" (one clean sentence), "departments" (pick zero or more from this list only: '
            f"{list(DEPARTMENTS)}), "
            '"activity_keywords" (student clubs or fests named or clearly implied, lowercase), '
            '"sector_keywords" (lowercase words a relevant company description would contain), '
            '"amount_inr" (integer rupees or null).\n\nNeed: ' + text
        )
        reply = Anthropic().messages.create(
            model=os.getenv("ALUMNI_MODEL", "claude-sonnet-5-5"),
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in reply.content if getattr(b, "type", "") == "text")
        parsed = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        parsed["departments"] = [d for d in parsed.get("departments") or [] if d in DEPARTMENTS]
        parsed["amount_inr"] = parsed.get("amount_inr") or simple["amount_inr"]
        parsed["parsed_by"] = "claude"
        return parsed
    except Exception:
        return simple


def to_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def role_tier(title):
    t = f" {(title or '').lower()} "
    if any(w in t for w in JUNIOR_EXEC):
        return None, 0, "role is below decision maker level"
    if any(w in t for w in FOUNDER_WORDS):
        return "founder", 25, None
    if "vice president" in t or re.search(r"\b(svp|evp|vp)\b", t):
        return "vp", 6, None
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in TOP_WORDS):
        return "top", 15, None
    return None, 0, "role is not senior enough to give"


def iitb_story(school):
    bits = [school.get("degree") or "", school.get("field_of_study") or ""]
    text = " ".join(b for b in bits if b).strip()
    seen, words = set(), []
    for part in text.split(", "):
        if part.lower() not in seen:
            seen.add(part.lower())
            words.append(part)
    return ", ".join(words) or "degree not listed"


def looks_short(school):
    text = f"{school.get('degree') or ''} {school.get('field_of_study') or ''}".lower()
    return any(w in text for w in SHORT_COURSE) and not any(w in text for w in ("b.tech", "btech", "m.tech", "mtech", "phd", "ph.d", "bachelor", "master"))


def score_person(person, companies, need, donors, today=None):
    today = today or date.today()
    basics = person.get("basic_profile") or {}
    name = basics.get("name") or "Unknown"
    jobs = (person.get("experience") or {}).get("employment_details") or {}
    current = jobs.get("current") or []
    schools = (person.get("education") or {}).get("schools") or []
    url = ((person.get("social_handles") or {}).get("professional_network_identifier") or {}).get("profile_url")

    role = next((r for r in current if r.get("crustdata_company_id") in companies), None)
    if not role:
        return {"name": name, "decision": "IGNORE", "why": "their employer had no qualifying money event"}
    company = companies[role["crustdata_company_id"]]

    iitb = [s for s in schools if is_iitb(s.get("school"))]
    if not iitb:
        return {"name": name, "decision": "IGNORE", "why": "school is not clearly IIT Bombay"}

    tier, role_points, role_problem = role_tier(role.get("title"))
    if not tier:
        return {"name": name, "decision": "IGNORE", "why": f"{role.get('title')}: {role_problem}"}

    score, reasons, flags = 0, [], []
    study = "; ".join(iitb_story(s) for s in iitb)
    study_text = " ".join(f"{s.get('degree') or ''} {s.get('field_of_study') or ''}" for s in iitb).lower()
    clubs_text = " ".join(s.get("activities_and_societies") or "" for s in iitb).lower()

    if all(looks_short(s) for s in iitb):
        flags.append(f"Only a short course at IIT Bombay ({study}), not a degree. Check before treating them as an alum.")

    matched = [d for d in need.get("departments", []) if any(w in study_text for w in DEPARTMENTS[d])]
    if matched:
        score += 25
        reasons.append(f"Studied {study} at IIT Bombay, which matches {', '.join(matched)}")
    elif need.get("departments"):
        score += 5
        reasons.append(f"IIT Bombay alum ({study}), but from a different department than this need")
    else:
        score += 15
        reasons.append(f"IIT Bombay alum: {study}")

    clubs = [k for k in need.get("activity_keywords", []) if k and k in clubs_text]
    if clubs:
        score += 25
        reasons.append(f"Was part of {', '.join(clubs)} as a student")

    score += role_points
    reasons.append(f"{role.get('title')} at {company['name']}")

    event = company["event"]
    amount = company.get("round_usd") or 0
    if event in ("ipo", "acquired"):
        score += 20
    elif amount >= 100e6:
        score += 15
    elif amount >= 25e6:
        score += 12
    else:
        score += 8
    reasons.append(f"{company['name']} {company['event_story']}")

    when = to_date(company.get("event_date"))
    if when and (today - when).days <= 90:
        score += 10
        reasons.append(f"The event was {(today - when).days} days ago, so it is fresh")

    blob = f" {company.get('description') or ''} {company.get('industry') or ''} ".lower()
    sector_hits = [w.strip() for w in need.get("sector_keywords", []) if w and w.lower() in blob]
    if sector_hits:
        score += 10
        reasons.append(f"Their company works in a related area ({', '.join(sorted(set(sector_hits))[:3])})")

    started = to_date(role.get("start_date"))
    if started and when and started > when:
        flags.append(f"Joined {company['name']} on {started}, after the money event, so they may not have shared in it")
    growth = company.get("growth_6m_pct")
    if event == "acquired" and isinstance(growth, (int, float)) and growth < -20:
        flags.append(f"Acquired, but headcount fell {abs(growth):.0f}% in 6 months. Could be a distress sale.")
    if name.strip().lower() in donors:
        flags.append("Already in the donor list. Coordinate with whoever owns that relationship.")
    weak = bool(need.get("departments")) and not matched and not clubs
    if weak:
        reasons.append("No link to this specific need beyond being an alum, so this is a better fit for a different ask")

    score = min(score, 100)
    if flags:
        decision = "REVIEW"
    elif weak or score < 50:
        decision = "LATER"
    else:
        decision = "READY"
    return {
        "name": name,
        "decision": decision,
        "score": score,
        "tier": tier,
        "title": role.get("title"),
        "company": company["name"],
        "company_event": company["event_story"],
        "study": study,
        "location": (basics.get("location") or {}).get("city") if isinstance(basics.get("location"), dict) else basics.get("location"),
        "profile_url": url,
        "reasons": reasons,
        "flags": flags,
    }


def rank(people, companies_list, need, donors=()):
    companies = {c["company_id"]: c for c in companies_list}
    donor_set = {d.strip().lower() for d in donors if d and d.strip()}
    results, seen = [], set()
    for person in people:
        pid = person.get("crustdata_person_id")
        if pid in seen:
            continue
        seen.add(pid)
        results.append(score_person(person, companies, need, donor_set))
    order = {"READY": 0, "REVIEW": 1, "LATER": 2, "IGNORE": 3}
    results.sort(key=lambda r: (order[r["decision"]], -r.get("score", 0)))
    return results

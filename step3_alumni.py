import json

from client import DATA, post, records, save, show_shape

TEST_COMPANIES = ["Razorpay", "Zepto"]
SENIOR = ["Owner / Partner", "CXO", "Vice President"]


def iitb_filter():
    return {
        "op": "or",
        "conditions": [
            {"field": "education.schools.school", "type": "(.)", "value": "IIT Bombay"},
            {"field": "education.schools.school", "type": "[.]", "value": "Indian Institute of Technology, Bombay"},
            {"field": "education.schools.school", "type": "[.]", "value": "Indian Institute of Technology Bombay"},
        ],
    }


def employer_filter():
    path = DATA / "companies.json"
    if path.exists():
        ids = [c["company_id"] for c in json.loads(path.read_text()) if c.get("company_id")]
        if ids:
            print(f"Using {len(ids)} company ids from step 2")
            return {"field": "experience.employment_details.current.company_id", "type": "in", "value": ids}
    print(f"No step 2 file yet, testing on {TEST_COMPANIES}")
    return {
        "op": "or",
        "conditions": [
            {"field": "experience.employment_details.current.company_name", "type": "(.)", "value": name}
            for name in TEST_COMPANIES
        ],
    }


def is_iitb(school_name):
    name = (school_name or "").lower()
    return "bombay" in name and ("iit" in name or "indian institute of technology" in name)


def main():
    body = {
        "filters": {
            "op": "and",
            "conditions": [
                iitb_filter(),
                employer_filter(),
                {"field": "experience.employment_details.current.seniority_level", "type": "in", "value": SENIOR},
            ],
        },
        "fields": ["basic_profile", "experience", "education", "social_handles"],
        "limit": 100,
        "explain": True,
    }
    reply = post("/person/search", body)
    people = records(reply)
    print(f"  got {len(people)} people (total matching: {reply.get('total_count')})")
    for remark in reply.get("remarks") or []:
        print(f"  remark: {remark.get('message')}")
    if not people:
        return

    print("\nShape of the first person:")
    show_shape(people[0], limit=4)

    fuzzy_misses = 0
    print("\nWho we found:")
    for p in people[:15]:
        basics = p.get("basic_profile") or {}
        current = ((p.get("experience") or {}).get("employment_details") or {}).get("current") or [{}]
        schools = (p.get("education") or {}).get("schools") or []
        iitb = [s for s in schools if is_iitb(s.get("school"))]
        if not iitb:
            fuzzy_misses += 1
        study = ", ".join(f"{s.get('degree') or ''} {s.get('field_of_study') or ''}".strip() for s in iitb) or "no clean IITB match"
        clubs = "; ".join(s.get("activities_and_societies") or "" for s in iitb if s.get("activities_and_societies"))
        print(f"  {basics.get('name')}: {current[0].get('title')} at {current[0].get('name')}")
        print(f"      IITB: {study}" + (f" | activities: {clubs[:80]}" if clubs else ""))

    if fuzzy_misses:
        print(f"\n  {fuzzy_misses} of the first 15 have no clear IIT Bombay school. That is the fuzzy match catching other IITs, so tighten iitb_filter().")
    save("alumni_raw.json", people)


if __name__ == "__main__":
    main()

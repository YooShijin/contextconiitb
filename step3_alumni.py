from client import load, paged, save

SENIOR = ["Owner / Partner", "CXO", "Vice President"]
MAX_PEOPLE = 400


def iitb_filter():
    return {
        "op": "or",
        "conditions": [
            {"field": "education.schools.school", "type": "[.]", "value": "Indian Institute of Technology, Bombay"},
            {"field": "education.schools.school", "type": "[.]", "value": "Indian Institute of Technology Bombay"},
            {"field": "education.schools.school", "type": "[.]", "value": "IIT Bombay"},
        ],
    }


def fetch_alumni(company_ids, max_items=MAX_PEOPLE, say=print):
    if not company_ids:
        raise ValueError("No company ids. Run step 2 first.")
    body = {
        "filters": {
            "op": "and",
            "conditions": [
                iitb_filter(),
                {"field": "experience.employment_details.current.company_id", "type": "in", "value": company_ids},
                {"field": "experience.employment_details.current.seniority_level", "type": "in", "value": SENIOR},
            ],
        },
        "fields": ["basic_profile", "experience", "education", "social_handles"],
        "sorts": [{"field": "crustdata_person_id", "order": "asc"}],
    }
    people, total = paged("/person/search", body, max_items)
    say(f"Crustdata: {len(people)} IIT Bombay alumni in senior roles at those companies (of {total} matching)")
    save("alumni_raw.json", people)
    return people


def main():
    companies = load("companies.json") or []
    ids = [c["company_id"] for c in companies if c.get("company_id")]
    people = fetch_alumni(ids)
    for p in people[:15]:
        basics = p.get("basic_profile") or {}
        print(f"  {basics.get('name')}: {basics.get('current_title')}")


if __name__ == "__main__":
    main()

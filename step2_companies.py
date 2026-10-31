from datetime import date, timedelta

from client import post, records, save, show_shape

LOOKBACK_DAYS = 180
MIN_ROUND_USD = 10_000_000
COUNTRY = "IND"


def pick(record, *paths):
    for path in paths:
        value = record
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value not in (None, "", []):
            return value
    return None


def find_funded(since):
    body = {
        "filters": {
            "op": "and",
            "conditions": [
                {"field": "funding.last_fundraise_date", "type": "=>", "value": since},
                {"field": "funding.last_round_amount_usd", "type": "=>", "value": MIN_ROUND_USD},
                {"field": "basic_info.status", "type": "=", "value": "active"},
                {"field": "locations.country", "type": "=", "value": COUNTRY},
            ],
        },
        "sorts": [{"field": "funding.last_round_amount_usd", "order": "desc"}],
        "limit": 100,
    }
    return post("/company/search", body)


def main():
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    print(f"Companies that raised {MIN_ROUND_USD:,} USD or more since {since} in {COUNTRY}")
    reply = find_funded(since)
    found = records(reply)
    print(f"  got {len(found)} companies (total matching: {reply.get('total_count')})")
    if not found:
        print("  Nothing back. Try COUNTRY = None, a smaller MIN_ROUND_USD, or ask Crustdata if funding filters are on your key.")
        print(f"  raw reply: {str(reply)[:800]}")
        return

    print("\nShape of the first company:")
    show_shape(found[0])

    slim = []
    for c in found:
        slim.append({
            "company_id": pick(c, "crustdata_company_id", "basic_info.company_id", "company_id"),
            "name": pick(c, "basic_info.name", "basic_info.company_name", "name"),
            "domain": pick(c, "basic_info.primary_domain", "primary_domain"),
            "last_round_usd": pick(c, "funding.last_round_amount_usd"),
            "last_round_type": pick(c, "funding.last_round_type"),
            "last_round_date": pick(c, "funding.last_fundraise_date"),
            "total_funding_usd": pick(c, "funding.total_investment_usd"),
            "headcount": pick(c, "headcount.total"),
            "growth_6m_pct": pick(c, "headcount.growth_percent.6m"),
        })

    print("\nTop 10:")
    for c in slim[:10]:
        amount = f"{c['last_round_usd']:,.0f}" if isinstance(c["last_round_usd"], (int, float)) else "?"
        print(f"  {c['company_id']}  {c['name']}  raised {amount} USD  {c['last_round_type'] or ''}  headcount {c['headcount']}")

    save("companies_raw.json", found)
    save("companies.json", slim)
    missing = sum(1 for c in slim if not c["company_id"])
    if missing:
        print(f"\n  {missing} companies have no id in the fields I tried. Check the shape above and fix pick().")


if __name__ == "__main__":
    main()

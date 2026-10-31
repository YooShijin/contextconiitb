from collections import Counter
from datetime import date, timedelta

from client import CrustError, paged, pick, save

LOOKBACK_DAYS = 180
MIN_ROUND_USD = 5_000_000
COUNTRY = "IND"
MAX_COMPANIES = 400
NOT_A_WINDFALL = ("debt", "post_ipo", "grant", "loan")


def usd(amount):
    if not isinstance(amount, (int, float)):
        return "an undisclosed amount"
    if amount >= 1e9:
        return f"${amount / 1e9:.1f}B"
    if amount >= 1e6:
        return f"${amount / 1e6:.0f}M"
    return f"${amount:,.0f}"


def round_name(raw):
    if not raw:
        return "funding round"
    return raw.replace("_", " ").title().replace("Ipo", "IPO")


def classify(c, since):
    ipo = pick(c, "revenue.public_markets.ipo_date")
    acquired = pick(c, "revenue.acquisition_status")
    kind = (pick(c, "funding.last_round_type") or "").lower()
    amount = pick(c, "funding.last_round_amount_usd")
    when = pick(c, "funding.last_fundraise_date")

    if ipo and str(ipo)[:10] >= since:
        return "ipo", f"went public on {str(ipo)[:10]}", str(ipo)[:10]
    if acquired:
        return "acquired", f"acquisition status: {acquired}", when
    if any(word in kind for word in NOT_A_WINDFALL):
        return None, f"{round_name(kind)} is not a founder liquidity event", when
    if amount:
        return "raise", f"raised {usd(amount)} in a {round_name(kind)} on {when}", when
    return None, "no usable money event", when


def base_conditions(since, min_usd, country):
    conditions = [
        {"field": "funding.last_fundraise_date", "type": "=>", "value": since},
        {"field": "funding.last_round_amount_usd", "type": "=>", "value": min_usd},
        {"field": "basic_info.status", "type": "=", "value": "active"},
    ]
    if country:
        conditions.append({"field": "locations.country", "type": "=", "value": country})
    return conditions


def fetch_companies(lookback_days=LOOKBACK_DAYS, min_usd=MIN_ROUND_USD, country=COUNTRY, max_items=MAX_COMPANIES, say=print):
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    body = {
        "filters": {"op": "and", "conditions": base_conditions(since, min_usd, country)},
        "sorts": [{"field": "funding.last_fundraise_date", "order": "desc"}],
    }
    raw, total = paged("/company/search", body, max_items)
    say(f"Crustdata: {len(raw)} companies raised money since {since} (of {total} matching)")

    try:
        ipo_body = {"filters": {"op": "and", "conditions": [
            {"field": "revenue.public_markets.ipo_date", "type": "=>", "value": since},
            *([{"field": "locations.country", "type": "=", "value": country}] if country else []),
        ]}}
        ipos, _ = paged("/company/search", ipo_body, 100)
        say(f"Crustdata: {len(ipos)} companies went public since {since}")
        raw.extend(ipos)
    except CrustError as err:
        say(f"IPO search skipped ({str(err)[:80]})")

    kept, skipped, seen = [], Counter(), set()
    for c in raw:
        cid = pick(c, "crustdata_company_id", "basic_info.crustdata_company_id")
        if cid in seen:
            continue
        seen.add(cid)
        event, story, when = classify(c, since)
        if not event:
            skipped[story.split(" is ")[0] if " is not " in story else story] += 1
            continue
        kept.append({
            "company_id": cid,
            "name": pick(c, "basic_info.name"),
            "domain": pick(c, "basic_info.primary_domain"),
            "description": (pick(c, "basic_info.description") or "")[:300],
            "industry": pick(c, "taxonomy.professional_network_industry"),
            "company_type": pick(c, "basic_info.company_type"),
            "year_founded": pick(c, "basic_info.year_founded"),
            "headcount": pick(c, "headcount.total"),
            "growth_6m_pct": pick(c, "headcount.growth_percent.6m"),
            "event": event,
            "event_story": story,
            "event_date": when,
            "round_usd": pick(c, "funding.last_round_amount_usd"),
            "round_type": round_name(pick(c, "funding.last_round_type")),
        })
    say(f"Kept {len(kept)} real money events. Skipped: {dict(skipped.most_common(5))}")
    save("companies.json", kept)
    return kept, dict(skipped)


def main():
    kept, _ = fetch_companies()
    print("\nTop 15 by recency:")
    for c in kept[:15]:
        print(f"  {c['company_id']}  {c['name']}: {c['event_story']}  (headcount {c['headcount']})")


if __name__ == "__main__":
    main()

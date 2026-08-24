"""
Strict data-cleaning pass simulating what would actually go live on the
website: splits into resale_properties (Sale) and a long-term rental table
(Rent), discarding anything that fails a "would this look professional on
a real listings site" bar.

Residential-type whitelist is explicit and printed, not inferred silently -
every one of the 50 raw Property Type values in the dataset was reviewed by
hand and classified below.
"""
import csv
from collections import Counter

RESIDENTIAL_TYPES = {
    "Departamento", "Condo/Apartment", "Casa", "House", "Penthouse", "Villa",
    "Casa en condominio", "Casa en Condominio", "Casa_En_Condominio",
    "Casa_Duplex", "Departamento_Cuadruplex", "Departamento_Triplex",
    "Town_House", "Finca", "Hacienda",
}

VALID_CURRENCIES = {"MXN", "USD"}

IN_PATH = "all_regions_listings_filtered_v12.csv"


def to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def main():
    with open(IN_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"Starting rows: {len(rows)}")

    funnel = [("Start", len(rows))]

    # 1. Sale or Rent must be a real bucket
    rows = [r for r in rows if r.get("Sale or Rent") in ("Sale", "Rent")]
    funnel.append(("Drop Unclassified sale/rent", len(rows)))

    # 2. Residential property type only
    rows = [r for r in rows if (r.get("Property Type") or "").strip() in RESIDENTIAL_TYPES]
    funnel.append(("Residential property type only", len(rows)))

    # 3. Description required
    rows = [r for r in rows if (r.get("Description") or "").strip()]
    funnel.append(("Has description", len(rows)))

    # 4. Images required
    rows = [r for r in rows if (r.get("Images") or "").strip()]
    funnel.append(("Has at least one image", len(rows)))

    # 5. City required
    rows = [r for r in rows if (r.get("City") or "").strip()]
    funnel.append(("Has city", len(rows)))

    # 5b. Bedrooms and bathrooms required
    rows = [r for r in rows if (r.get("Bedrooms") or "").strip()]
    funnel.append(("Has bedrooms", len(rows)))
    rows = [r for r in rows if (r.get("Bathrooms") or "").strip()]
    funnel.append(("Has bathrooms", len(rows)))

    # 6. Valid, interpretable currency
    rows = [r for r in rows if (r.get("Currency") or "").strip() in VALID_CURRENCIES]
    funnel.append(("Valid currency (MXN/USD only)", len(rows)))

    # 7. Valid positive price
    for r in rows:
        r["_price"] = to_float(r.get("Price"))
    rows = [r for r in rows if r["_price"] is not None and r["_price"] > 0]
    funnel.append(("Valid positive price", len(rows)))

    # 8. No duplicate Listing URLs (sanity check post-dedup)
    seen_urls = set()
    deduped = []
    dupe_count = 0
    for r in rows:
        u = (r.get("Listing URL") or "").strip()
        key = u if u else id(r)
        if key in seen_urls:
            dupe_count += 1
            continue
        seen_urls.add(key)
        deduped.append(r)
    rows = deduped
    funnel.append((f"Drop residual duplicate URLs ({dupe_count} found)", len(rows)))

    print("\nFunnel so far:")
    for label, n in funnel:
        print(f"  {label}: {n}")

    # Split
    resale = [r for r in rows if r["Sale or Rent"] == "Sale"]
    rental = [r for r in rows if r["Sale or Rent"] == "Rent"]
    print(f"\nBefore price-outlier trim: resale={len(resale)}, rental={len(rental)}")

    # 9. Price outlier trim - per currency, per bucket, drop bottom/top 1%
    def trim_outliers(bucket_rows, label):
        by_currency = {}
        for r in bucket_rows:
            by_currency.setdefault(r["Currency"], []).append(r)
        kept = []
        for cur, cur_rows in by_currency.items():
            prices = sorted(r["_price"] for r in cur_rows)
            n = len(prices)
            lo_idx = int(n * 0.01)
            hi_idx = int(n * 0.99)
            lo = prices[lo_idx]
            hi = prices[min(hi_idx, n - 1)]
            before = len(cur_rows)
            survivors = [r for r in cur_rows if lo <= r["_price"] <= hi]
            print(f"  {label} / {cur}: kept range [{lo:,.0f} - {hi:,.0f}], {before} -> {len(survivors)}")
            kept.extend(survivors)
        return kept

    print("\nPrice-outlier trim (drop bottom/top 1% per currency):")
    resale = trim_outliers(resale, "resale_properties")
    rental = trim_outliers(rental, "rental")

    print(f"\nFINAL: resale_properties = {len(resale)}, rental = {len(rental)}, total = {len(resale) + len(rental)}")

    # Write outputs
    fields = [f for f in (list(rows[0].keys()) if rows else []) if not f.startswith("_")]
    with open("resale_properties_clean.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in resale:
            w.writerow({k: r.get(k) for k in fields})

    with open("rental_properties_clean.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rental:
            w.writerow({k: r.get(k) for k in fields})

    print("\nWrote resale_properties_clean.csv and rental_properties_clean.csv")

    # Region breakdown of final sets, for context
    def region_counts(bucket_rows):
        c = Counter()
        for r in bucket_rows:
            for region in (r.get("Region Match") or "No Location Signal").split("; "):
                c[region] += 1
        return c

    print("\nresale_properties by region:")
    for region, n in region_counts(resale).most_common():
        print(f"  {region}: {n}")
    print("\nrental by region:")
    for region, n in region_counts(rental).most_common():
        print(f"  {region}: {n}")


if __name__ == "__main__":
    main()

import json
import csv

SRC = r"C:\Users\rikij\Desktop\airroi data 222.json"
OUT_DIR = r"C:\Users\rikij\Desktop\Claude Code\Development\Projects\riviera-maya-map-poc\airroi-data"

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

props = data["data"]["properties"]

property_fields = [
    "id", "listing_id", "listing_name", "listing_type", "room_type",
    "cover_photo_url", "photos_count", "checkin_time", "checkout_time", "guest_favorite",
    "host_id", "host_name", "cohost_ids", "cohost_names", "superhost", "professional_management",
    "latitude", "longitude", "country_code", "country", "region", "locality", "district", "exact_location",
    "guests", "bedrooms", "beds", "baths", "registration", "registration_details",
    "amenities_count", "amenities",
    "instant_book", "min_nights", "cancellation_policy",
    "currency", "cleaning_fee", "extra_guest_fee", "single_fee_structure",
    "num_reviews", "rating_overall", "rating_accuracy", "rating_checkin",
    "rating_cleanliness", "rating_communication", "rating_location", "rating_value",
    "ttm_revenue", "ttm_avg_rate", "ttm_occupancy", "ttm_adjusted_occupancy",
    "ttm_revpar", "ttm_adjusted_revpar", "ttm_total_days", "ttm_available_days",
    "ttm_blocked_days", "ttm_days_reserved", "ttm_avg_min_nights", "ttm_avg_length_of_stay",
    "l90d_revenue", "l90d_avg_rate", "l90d_occupancy", "l90d_adjusted_occupancy",
    "l90d_revpar", "l90d_adjusted_revpar", "l90d_total_days", "l90d_available_days",
    "l90d_blocked_days", "l90d_days_reserved", "l90d_avg_min_nights", "l90d_avg_length_of_stay",
]

monthly_fields = [
    "property_id", "listing_id", "listing_name", "date",
    "occupancy", "average_daily_rate_usd", "revpar_usd", "revenue_usd", "min_nights",
]

def j(vals):
    return "; ".join(str(v) for v in vals if v is not None) if vals else ""

with open(f"{OUT_DIR}/airroi_properties.csv", "w", newline="", encoding="utf-8-sig") as pf, \
     open(f"{OUT_DIR}/airroi_monthly_metrics.csv", "w", newline="", encoding="utf-8-sig") as mf:

    pw = csv.DictWriter(pf, fieldnames=property_fields)
    pw.writeheader()
    mw = csv.DictWriter(mf, fieldnames=monthly_fields)
    mw.writeheader()

    for p in props:
        li = p.get("listing_info") or {}
        hi = p.get("host_info") or {}
        loc = p.get("location_info") or {}
        pd = p.get("property_details") or {}
        bs = p.get("booking_settings") or {}
        pi = p.get("pricing_info") or {}
        rt = p.get("ratings") or {}
        pm = p.get("performance_metrics") or {}
        amenities = pd.get("amenities") or []

        row = {
            "id": p.get("id"),
            "listing_id": li.get("listing_id"),
            "listing_name": li.get("listing_name"),
            "listing_type": li.get("listing_type"),
            "room_type": li.get("room_type"),
            "cover_photo_url": li.get("cover_photo_url"),
            "photos_count": li.get("photos_count"),
            "checkin_time": li.get("checkin_time"),
            "checkout_time": li.get("checkout_time"),
            "guest_favorite": li.get("guest_favorite"),
            "host_id": hi.get("host_id"),
            "host_name": hi.get("host_name"),
            "cohost_ids": j(hi.get("cohost_ids") or []),
            "cohost_names": j(hi.get("cohost_names") or []),
            "superhost": hi.get("superhost"),
            "professional_management": hi.get("professional_management"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "country_code": loc.get("country_code"),
            "country": loc.get("country"),
            "region": loc.get("region"),
            "locality": loc.get("locality"),
            "district": loc.get("district"),
            "exact_location": loc.get("exact_location"),
            "guests": pd.get("guests"),
            "bedrooms": pd.get("bedrooms"),
            "beds": pd.get("beds"),
            "baths": pd.get("baths"),
            "registration": pd.get("registration"),
            "registration_details": pd.get("registration_details"),
            "amenities_count": len(amenities),
            "amenities": j(amenities),
            "instant_book": bs.get("instant_book"),
            "min_nights": bs.get("min_nights"),
            "cancellation_policy": bs.get("cancellation_policy"),
            "currency": pi.get("currency"),
            "cleaning_fee": pi.get("cleaning_fee"),
            "extra_guest_fee": pi.get("extra_guest_fee"),
            "single_fee_structure": pi.get("single_fee_structure"),
            "num_reviews": rt.get("num_reviews"),
            "rating_overall": rt.get("rating_overall"),
            "rating_accuracy": rt.get("rating_accuracy"),
            "rating_checkin": rt.get("rating_checkin"),
            "rating_cleanliness": rt.get("rating_cleanliness"),
            "rating_communication": rt.get("rating_communication"),
            "rating_location": rt.get("rating_location"),
            "rating_value": rt.get("rating_value"),
        }
        for k, v in pm.items():
            row[k] = v
        pw.writerow(row)

        for m in (p.get("monthly_metrics") or []):
            mw.writerow({
                "property_id": p.get("id"),
                "listing_id": li.get("listing_id"),
                "listing_name": li.get("listing_name"),
                "date": m.get("date"),
                "occupancy": m.get("occupancy"),
                "average_daily_rate_usd": m.get("average_daily_rate_usd"),
                "revpar_usd": m.get("revpar_usd"),
                "revenue_usd": m.get("revenue_usd"),
                "min_nights": m.get("min_nights"),
            })

print("done:", len(props), "properties")

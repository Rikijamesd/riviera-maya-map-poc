-- Run this once in the Supabase SQL editor before ingesting.
create table if not exists cancun_listings (
  id bigint primary key,                 -- properstar listing/project id
  url text not null,
  is_project boolean not null default false,
  location text,
  title text,
  highlights text,
  bedrooms smallint,
  bathrooms smallint,
  size_sqft numeric,
  property_type text,
  price_raw text,                        -- e.g. "GBP 410,924"
  price_currency text,                   -- e.g. "GBP"
  price_amount numeric,                  -- e.g. 410924
  pictures jsonb,
  latitude double precision,
  longitude double precision,
  fetched_at timestamptz not null default now()
);

create index if not exists cancun_listings_location_idx on cancun_listings (location);

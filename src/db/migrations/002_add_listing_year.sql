-- listing_year: model year from dealership_inventories.year (per listing), not boats_models catalog.
-- Populated by cms_etl mart_daily_snapshot and fact_estimated_sale after Dagster deploy + sync.

ALTER TABLE mart_daily_snapshot
    ADD COLUMN IF NOT EXISTS listing_year SMALLINT;

ALTER TABLE fact_estimated_sale
    ADD COLUMN IF NOT EXISTS listing_year SMALLINT;

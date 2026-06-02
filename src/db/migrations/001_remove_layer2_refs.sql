-- Migration 001: remove Layer2 foreign key references from dimension tables.
-- Renames l2_* columns to directus_* so dimensions are keyed by Directus IDs
-- instead of Layer2 ORM IDs.
--
-- Idempotent: each statement is wrapped in a DO block that checks the current
-- column name before renaming, so re-running is safe.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'dim_manufacturer'
          AND column_name = 'l2_gear_brand_id'
    ) THEN
        ALTER TABLE dim_manufacturer RENAME COLUMN l2_gear_brand_id TO directus_brand_id;
        RAISE NOTICE 'dim_manufacturer.l2_gear_brand_id -> directus_brand_id';
    ELSE
        RAISE NOTICE 'dim_manufacturer.l2_gear_brand_id not found, skipping';
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'dim_boat_model'
          AND column_name = 'l2_boats_model_id'
    ) THEN
        ALTER TABLE dim_boat_model RENAME COLUMN l2_boats_model_id TO directus_model_id;
        RAISE NOTICE 'dim_boat_model.l2_boats_model_id -> directus_model_id';
    ELSE
        RAISE NOTICE 'dim_boat_model.l2_boats_model_id not found, skipping';
    END IF;
END $$;

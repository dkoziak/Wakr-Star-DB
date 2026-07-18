-- Migration 003: Create inventory views, helper and velocity functions

CREATE OR REPLACE VIEW v_daily_snapshot AS
SELECT 
    mds.date_key,
    mds.manufacturer_key,
    mds.boat_model_key,
    mds.listing_year,
    mds.active_listings,
    mds.new_listings,
    mds.avg_dom,
    mds.dom_bucket_0_7,
    mds.dom_bucket_8_15,
    mds.dom_bucket_16_30,
    mds.dom_bucket_31_60,
    mds.dom_bucket_60_plus,
    mds.state,
    mds.inventory_type,
    mds.last_scrape_date,
    mfr.manufacturer_name,
    bm.make,
    bm.model
FROM mart_daily_snapshot mds
JOIN dim_boat_model bm ON mds.boat_model_key = bm.boat_model_key
JOIN dim_manufacturer mfr ON mds.manufacturer_key = mfr.manufacturer_key;

CREATE OR REPLACE VIEW v_estimated_sale AS
SELECT 
    fes.estimated_sale_key,
    fes.date_key,
    fes.manufacturer_key,
    fes.boat_model_key,
    fes.listing_year,
    fes.inventory_type,
    fes.state,
    fes.estimated_sale_price,
    fes.days_on_market,
    mfr.manufacturer_name,
    bm.make,
    bm.model
FROM fact_estimated_sale fes
LEFT JOIN dim_boat_model bm ON fes.boat_model_key = bm.boat_model_key
LEFT JOIN dim_manufacturer mfr ON fes.manufacturer_key = mfr.manufacturer_key;

-- Helper function: Resolve time range
CREATE OR REPLACE FUNCTION resolve_sql_time_range(
    p_time_range text,
    p_as_of_date date DEFAULT NULL
)
RETURNS TABLE (
    from_key integer,
    to_key integer,
    prior_from_key integer,
    prior_to_key integer
) AS $$
DECLARE
    v_today date;
    v_start date;
    v_end date;
    v_prior_start date;
    v_prior_end date;
    v_first_this_month date;
    v_last_day_prev date;
    v_q integer;
    v_prior_days integer;
BEGIN
    v_today := COALESCE(p_as_of_date, CURRENT_DATE);

    IF p_time_range = 'trailing_7' THEN
        v_start := v_today - INTERVAL '6 days';
        v_end := v_today;
        v_prior_start := v_start - INTERVAL '7 days';
        v_prior_end := v_start - INTERVAL '1 day';

    ELSIF p_time_range = 'trailing_30' THEN
        v_start := v_today - INTERVAL '29 days';
        v_end := v_today;
        v_prior_start := v_start - INTERVAL '30 days';
        v_prior_end := v_start - INTERVAL '1 day';

    ELSIF p_time_range = 'trailing_90' THEN
        v_start := v_today - INTERVAL '89 days';
        v_end := v_today;
        v_prior_start := v_start - INTERVAL '90 days';
        v_prior_end := v_start - INTERVAL '1 day';

    ELSIF p_time_range = 'last_month' THEN
        v_first_this_month := date_trunc('month', v_today)::date;
        v_last_day_prev := v_first_this_month - INTERVAL '1 day';
        v_start := date_trunc('month', v_last_day_prev)::date;
        v_end := v_last_day_prev;
        v_prior_end := v_start - INTERVAL '1 day';
        v_prior_start := date_trunc('month', v_prior_end)::date;

    ELSIF p_time_range = 'last_quarter' THEN
        v_q := EXTRACT(QUARTER FROM v_today)::integer;
        IF v_q = 1 THEN
            v_start := make_date(EXTRACT(YEAR FROM v_today)::integer - 1, 10, 1);
            v_end := make_date(EXTRACT(YEAR FROM v_today)::integer - 1, 12, 31);
        ELSE
            v_start := make_date(EXTRACT(YEAR FROM v_today)::integer, (v_q - 2) * 3 + 1, 1);
            v_end := (date_trunc('quarter', v_today) - INTERVAL '1 day')::date;
        END IF;
        v_prior_days := (v_end - v_start) + 1;
        v_prior_end := v_start - INTERVAL '1 day';
        v_prior_start := v_prior_end - (v_prior_days - 1) * INTERVAL '1 day';

    ELSIF p_time_range = 'ytd' THEN
        v_start := make_date(EXTRACT(YEAR FROM v_today)::integer, 1, 1);
        v_end := v_today;
        v_prior_start := make_date(EXTRACT(YEAR FROM v_today)::integer - 1, 1, 1);
        v_prior_end := v_end - INTERVAL '1 year';

    ELSIF p_time_range = 'l12m' THEN
        v_start := v_today - INTERVAL '365 days';
        v_end := v_today;
        v_prior_start := v_start - INTERVAL '365 days';
        v_prior_end := v_start - INTERVAL '1 day';
    ELSE
        RAISE EXCEPTION 'Unknown time_range: %', p_time_range;
    END IF;

    RETURN QUERY SELECT 
        CAST(to_char(v_start, 'YYYYMMDD') AS integer),
        CAST(to_char(v_end, 'YYYYMMDD') AS integer),
        CAST(to_char(v_prior_start, 'YYYYMMDD') AS integer),
        CAST(to_char(v_prior_end, 'YYYYMMDD') AS integer);
END;
$$ LANGUAGE plpgsql STABLE;

-- Velocity function for get_inventory_velocity
CREATE OR REPLACE FUNCTION get_inventory_velocity(
    p_time_range text,
    p_inventory_type text DEFAULT 'combined',
    p_make text DEFAULT NULL,
    p_state text DEFAULT NULL,
    p_as_of_date date DEFAULT NULL
)
RETURNS TABLE (
    model_year text,
    manufacturer text,
    model text,
    year integer,
    avg_days_on_market numeric,
    dom_velocity_label text,
    active_units bigint,
    boats_sold bigint,
    momentum text
) AS $$
#variable_conflict use_column
DECLARE
    v_from_key integer;
    v_to_key integer;
    v_prior_from_key integer;
    v_prior_to_key integer;
    v_latest_key integer;
    v_prior_latest_key integer;
    v_inv_type_val text;
    v_state_val text;
BEGIN
    -- 1. Визначення часових рамок
    SELECT from_key, to_key, prior_from_key, prior_to_key
    INTO v_from_key, v_to_key, v_prior_from_key, v_prior_to_key
    FROM resolve_sql_time_range(p_time_range, p_as_of_date);

    -- 2. Валідація Make
    IF p_make IS NOT NULL AND LOWER(p_make) != 'all' THEN
        IF NOT EXISTS (SELECT 1 FROM dim_manufacturer WHERE LOWER(manufacturer_name) = LOWER(p_make)) THEN
            RAISE EXCEPTION 'Unknown make: %', p_make;
        END IF;
    END IF;

    -- 3. Перетворення типу інвентарю та штату
    IF p_inventory_type = 'new' THEN
        v_inv_type_val := 'New';
    ELSIF p_inventory_type = 'used' THEN
        v_inv_type_val := 'Used';
    ELSE
        v_inv_type_val := NULL; -- combined
    END IF;

    IF p_state IS NOT NULL AND LOWER(p_state) != 'all' THEN
        v_state_val := UPPER(p_state);
    ELSE
        v_state_val := NULL;
    END IF;

    -- 4. Отримання останньої дати зрізу для поточного періоду
    SELECT MAX(vds.date_key) INTO v_latest_key
    FROM v_daily_snapshot vds
    WHERE vds.date_key >= v_from_key AND vds.date_key <= v_to_key
      AND vds.boat_model_key IS NOT NULL
      AND vds.state IS NOT NULL
      AND (p_make IS NULL OR LOWER(p_make) = 'all' OR LOWER(vds.manufacturer_name) = LOWER(p_make))
      AND (v_inv_type_val IS NULL OR vds.inventory_type = v_inv_type_val)
      AND (v_state_val IS NULL OR vds.state = v_state_val);

    -- 5. Отримання останньої дати зрізу для попереднього періоду
    SELECT MAX(vds.date_key) INTO v_prior_latest_key
    FROM v_daily_snapshot vds
    WHERE vds.date_key >= v_prior_from_key AND vds.date_key <= v_prior_to_key
      AND vds.boat_model_key IS NOT NULL
      AND vds.state IS NOT NULL
      AND (p_make IS NULL OR LOWER(p_make) = 'all' OR LOWER(vds.manufacturer_name) = LOWER(p_make))
      AND (v_inv_type_val IS NULL OR vds.inventory_type = v_inv_type_val)
      AND (v_state_val IS NULL OR vds.state = v_state_val);

    IF v_latest_key IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH current_stock AS (
        SELECT 
            vds.manufacturer_name,
            vds.model,
            vds.listing_year,
            COALESCE(SUM(vds.avg_dom * vds.active_listings) / NULLIF(SUM(vds.active_listings), 0), 0.0) AS avg_dom,
            SUM(vds.active_listings) AS active_units
        FROM v_daily_snapshot vds
        WHERE vds.date_key = v_latest_key
          AND vds.boat_model_key IS NOT NULL
          AND vds.state IS NOT NULL
          AND (p_make IS NULL OR LOWER(p_make) = 'all' OR LOWER(vds.manufacturer_name) = LOWER(p_make))
          AND (v_inv_type_val IS NULL OR vds.inventory_type = v_inv_type_val)
          AND (v_state_val IS NULL OR vds.state = v_state_val)
        GROUP BY vds.manufacturer_name, vds.model, vds.listing_year
    ),
    prior_stock AS (
        SELECT 
            vds.manufacturer_name,
            vds.model,
            vds.listing_year,
            COALESCE(SUM(vds.avg_dom * vds.active_listings) / NULLIF(SUM(vds.active_listings), 0), 0.0) AS avg_dom
        FROM v_daily_snapshot vds
        WHERE vds.date_key = v_prior_latest_key
          AND vds.boat_model_key IS NOT NULL
          AND vds.state IS NOT NULL
          AND (p_make IS NULL OR LOWER(p_make) = 'all' OR LOWER(vds.manufacturer_name) = LOWER(p_make))
          AND (v_inv_type_val IS NULL OR vds.inventory_type = v_inv_type_val)
          AND (v_state_val IS NULL OR vds.state = v_state_val)
        GROUP BY vds.manufacturer_name, vds.model, vds.listing_year
    ),
    sales_flow AS (
        SELECT 
            ves.manufacturer_name,
            ves.model,
            ves.listing_year,
            COUNT(*) AS boats_sold
        FROM v_estimated_sale ves
        WHERE ves.date_key >= v_from_key AND ves.date_key <= v_to_key
          AND ves.boat_model_key IS NOT NULL
          AND (p_make IS NULL OR LOWER(p_make) = 'all' OR LOWER(ves.manufacturer_name) = LOWER(p_make))
          AND (v_inv_type_val IS NULL OR ves.inventory_type = v_inv_type_val)
          AND (v_state_val IS NULL OR ves.state = v_state_val)
        GROUP BY ves.manufacturer_name, ves.model, ves.listing_year
    ),
    full_keys AS (
        SELECT DISTINCT manufacturer_name, model, listing_year FROM (
            SELECT cs.manufacturer_name, cs.model, cs.listing_year FROM current_stock cs
            UNION
            SELECT sf.manufacturer_name, sf.model, sf.listing_year FROM sales_flow sf
        ) unioned
    ),
    assembled AS (
        SELECT 
            fk.manufacturer_name,
            fk.model,
            fk.listing_year,
            cs.avg_dom AS cur_dom,
            COALESCE(cs.active_units, 0) AS active_units,
            COALESCE(sf.boats_sold, 0) AS boats_sold,
            ps.avg_dom AS prior_dom
        FROM full_keys fk
        LEFT JOIN current_stock cs ON fk.manufacturer_name = cs.manufacturer_name AND fk.model = cs.model AND fk.listing_year = cs.listing_year
        LEFT JOIN sales_flow sf ON fk.manufacturer_name = sf.manufacturer_name AND fk.model = sf.model AND fk.listing_year = sf.listing_year
        LEFT JOIN prior_stock ps ON fk.manufacturer_name = ps.manufacturer_name AND fk.model = ps.model AND fk.listing_year = ps.listing_year
    )
    SELECT 
        COALESCE(a.listing_year::text, '?') || ' ' || a.manufacturer_name || ' ' || a.model AS model_year,
        a.manufacturer_name::text AS manufacturer,
        a.model::text AS model,
        a.listing_year::integer AS year,
        ROUND(a.cur_dom, 1)::numeric AS avg_days_on_market,
        CASE 
            WHEN a.cur_dom IS NULL THEN 'Very Slow'
            WHEN a.cur_dom < 15 THEN 'Fast'
            WHEN a.cur_dom < 22 THEN 'Healthy'
            WHEN a.cur_dom < 30 THEN 'Slow'
            ELSE 'Very Slow'
        END::text AS dom_velocity_label,
        a.active_units::bigint,
        a.boats_sold::bigint,
        CASE 
            WHEN a.prior_dom IS NULL OR a.prior_dom = 0 OR a.cur_dom IS NULL THEN 'Stable'
            WHEN ((a.cur_dom - a.prior_dom) / a.prior_dom) < -0.10 THEN 'Accelerating'
            WHEN ((a.cur_dom - a.prior_dom) / a.prior_dom) > 0.10 THEN 'Slowing'
            ELSE 'Stable'
        END::text AS momentum
    FROM assembled a
    WHERE a.manufacturer_name IS NOT NULL AND a.model IS NOT NULL
      AND TRIM(a.manufacturer_name) != '' AND TRIM(a.model) != ''
      AND LOWER(TRIM(a.manufacturer_name)) != 'unknown' AND LOWER(TRIM(a.model)) != 'unknown'
    ORDER BY a.active_units DESC;
END;
$$ LANGUAGE plpgsql STABLE;

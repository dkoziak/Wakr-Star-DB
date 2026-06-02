-- ================================================================================
-- Wakr Data Lake  —  DDL  |  v1.8.0  |  2026-05-14
-- ================================================================================
-- Pattern : star-schema
-- Star-schema data lake for Wakr market intelligence platform. Tracks
-- towboat/watersport boat listings, pricing, inventory velocity, dealer
-- performance, and member activity across national dealer networks.

-- Source trust hierarchy:
--   manufacturer_feed (priority 0)
--   manual_import (priority 1)
--   directus_cms (priority 2)
--   scraper (priority 3)
--   website_cms (priority 4)

-- ================================================================================
-- LAYER 2 — Reference Database  (gear_brands, boats_models, waters, dealers …)
-- ================================================================================
-- Wakr Central Business Database (Layer 2). PostgreSQL 16, schema v2.5.0. The
-- authoritative operational database. The Data Lake (Layer 3) dimensions are
-- downstream projections of Layer 2 reference tables, synced on a daily
-- schedule.

-- Projects to : dim_manufacturer   |   Sync key: gear_brands.id → dim_manufacturer.l2_gear_brand_id
-- Master manufacturer/brand registry. Single source of truth for all boat make
-- names, partner status, and active flag. Maps to dim_manufacturer in the Data
-- Lake. directus_id is an ETL sync artifact only — not the authoritative row
-- identity.
CREATE TABLE gear_brands (
    id                                         SERIAL PRIMARY KEY,
    directus_id                                INTEGER  -- ETL sync artifact. NULL until Website ETL pushes row to Directus. Do not use as write or upsert key.,
    external_id                                TEXT  -- Source system own ID (e.g. manufacturer catalog ID).,
    external_source                            TEXT  -- FK source_priority_ref.source_name.,
    name                                       TEXT  -- NOT NULL,
    slug                                       TEXT  -- UNIQUE,
    country_of_origin                          TEXT,
    is_active                                  BOOLEAN  -- NOT NULL | FALSE for discontinued or delisted brands.,
    _source                                    TEXT  -- NOT NULL | FK source_priority_ref. Row-level write authority.,
    _source_priority                           INTEGER  -- NOT NULL,
    created_at                                 TIMESTAMP  -- NOT NULL,
    updated_at                                 TIMESTAMP  -- NOT NULL
);

-- Projects to : dim_boat_model   |   Sync key: boats_models.id → dim_boat_model.l2_boats_model_id
-- Master boat model registry. One row per make/model/model_year. UNIQUE on
-- (brand_id, name, model_year). default_engine_model_id links to factory-
-- standard engine (FK engine_models.id). Model filter dropdown on all
-- dashboard tabs resolves its value list from this table scoped to selected
-- brand_id.
CREATE TABLE boats_models (
    id                                         SERIAL PRIMARY KEY,
    directus_id                                INTEGER  -- ETL sync artifact only.,
    external_id                                TEXT,
    external_source                            TEXT  -- FK source_priority_ref.,
    brand_id                                   INTEGER  -- NOT NULL | FK gear_brands.id,
    name                                       TEXT  -- NOT NULL,
    slug                                       TEXT  -- Per-brand unique where NOT NULL.,
    model_year                                 SMALLINT  -- NOT NULL | 0 = unknown. Part of UNIQUE (brand_id, name, model_year).,
    boat_type                                  TEXT  -- CHECK: Ski | Wake | Surf | Crossover | Other,
    hull_length_ft                             DECIMAL(5,2),
    engine_type                                TEXT,
    base_engine_hp                             SMALLINT,
    base_tower_included                        BOOLEAN,
    base_ballast_lbs                           INTEGER,
    msrp                                       DECIMAL(10,2),
    default_engine_model_id                    INTEGER  -- FK engine_models.id. Factory-standard engine. NULL = not yet normalized or varies by trim.,
    is_active                                  BOOLEAN  -- NOT NULL,
    _source                                    TEXT  -- NOT NULL,
    _source_priority                           INTEGER  -- NOT NULL,
    created_at                                 TIMESTAMP  -- NOT NULL,
    updated_at                                 TIMESTAMP  -- NOT NULL
);

-- Projects to : dim_lake   |   Sync key: waters.id → dim_lake.l2_waters_id
-- Operational lake/body-of-water reference. Maps to dim_lake. DMA removed —
-- analytics concern computed in Layer 3 from zip/geo data. Includes PostGIS
-- geometry (postgis extension). Unique on (name, state) where both non-null.
CREATE TABLE waters (
    id                                         SERIAL PRIMARY KEY,
    directus_id                                INTEGER  -- ETL sync artifact only.,
    external_id                                TEXT,
    external_source                            TEXT,
    name                                       TEXT  -- NOT NULL,
    state                                      CHAR(2),
    state_name                                 VARCHAR(50),
    county                                     VARCHAR(100),
    lat                                        DECIMAL(9,6),
    lon                                        DECIMAL(9,6),
    surface_acres                              INTEGER,
    avg_depth_ft                               DECIMAL(6,2)  -- Not yet in dim_lake — add in next sync pass.,
    salinity                                   TEXT  -- CHECK: fresh | salt | brackish. Not yet in dim_lake — add in next sync pass.,
    lake_type                                  TEXT  -- CHECK: Reservoir | Natural | Private | Other,
    created_at                                 TIMESTAMP,
    updated_at                                 TIMESTAMP
);

-- Projects to : dim_dealer_network   |   Sync key: dealer_groups.id → dim_dealer_network.l2_dealer_group_id
-- Multi-location dealer networks and broker entities. Maps to
-- dim_dealer_network. Manufacturers are NOT here — gear_brands is the
-- manufacturer table. group_type: dealer_group | broker | other.
CREATE TABLE dealer_groups (
    id                                         SERIAL PRIMARY KEY,
    directus_id                                INTEGER  -- ETL sync artifact only.,
    name                                       TEXT  -- NOT NULL,
    group_type                                 TEXT  -- NOT NULL | CHECK: dealer_group | broker | other,
    website_url                                TEXT,
    address                                    TEXT,
    city                                       TEXT,
    state                                      CHAR(2),
    state_name                                 VARCHAR(50),
    zip                                        VARCHAR(10),
    phone                                      TEXT,
    email                                      TEXT,
    network_name                               TEXT,
    parent_company                             TEXT,
    network_type                               TEXT  -- CHECK: franchise | independent | corporate | other. NOTE: ERD used Title Case — L2 uses lowercase.,
    is_wakr_partner                            BOOLEAN  -- NOT NULL,
    is_active                                  BOOLEAN  -- NOT NULL,
    _source                                    TEXT  -- NOT NULL,
    _source_priority                           INTEGER  -- NOT NULL,
    created_at                                 TIMESTAMP  -- NOT NULL,
    updated_at                                 TIMESTAMP  -- NOT NULL
);

-- Projects to : dim_dealer   |   Sync key: dealers.id → dim_dealer.l2_dealer_id
-- Operational dealer record. One row per physical location. Maps to
-- dim_dealer. primary_brand_id removed from Layer 2 — derive via dealer_brands
-- WHERE is_primary = TRUE. DMA removed. water_id FK to waters (nearest lake)
-- maps to dim_lake via l2_waters_id.
CREATE TABLE dealers (
    id                                         SERIAL PRIMARY KEY,
    directus_id                                INTEGER  -- ETL sync artifact only.,
    dealer_group_id                            INTEGER  -- FK dealer_groups.id. NULL for independent dealers.,
    dealer_name                                TEXT  -- NOT NULL,
    dealer_url                                 TEXT  -- UNIQUE,
    address                                    TEXT,
    city                                       TEXT,
    state                                      CHAR(2),
    state_name                                 VARCHAR(50),
    zip                                        VARCHAR(10),
    county                                     VARCHAR(100),
    lat                                        DECIMAL(9,6),
    lon                                        DECIMAL(9,6),
    water_id                                   INTEGER  -- FK waters.id. Nearest lake. Maps to dim_lake in Data Lake via l2_waters_id.,
    phone                                      TEXT,
    email                                      TEXT,
    is_authorized                              BOOLEAN  -- NOT NULL,
    is_wakr_partner                            BOOLEAN  -- NOT NULL,
    is_active                                  BOOLEAN  -- NOT NULL,
    _source                                    TEXT  -- NOT NULL,
    _source_priority                           INTEGER  -- NOT NULL,
    created_at                                 TIMESTAMP  -- NOT NULL,
    updated_at                                 TIMESTAMP  -- NOT NULL
);

-- Projects to : bridge_dealer_manufacturer   |   Sync key: None
-- Many-to-many bridge between dealers and gear_brands. Maps to
-- bridge_dealer_manufacturer. UNIQUE (dealer_id, brand_id). authorization_type
-- uses lowercase values — ERD corrected to match.
CREATE TABLE dealer_brands (
    id                                         SERIAL PRIMARY KEY,
    dealer_id                                  INTEGER  -- NOT NULL | FK dealers.id ON DELETE CASCADE,
    brand_id                                   INTEGER  -- NOT NULL | FK gear_brands.id,
    is_primary                                 BOOLEAN  -- NOT NULL,
    is_authorized                              BOOLEAN  -- NOT NULL,
    authorization_type                         TEXT  -- CHECK: full | service_only | parts_only | pending | other.,
    effective_date                             DATE,
    expiry_date                                DATE
);

-- Core operational listing table. One row per listing per source. Maps to
-- fact_listing_snapshot (via daily scrape) and dim_boat_instance.
-- source_record_key (URL) is the scraper upsert key. canonical_boat_id (UUID)
-- is the durable cross-source boat identity. HIN is the gold-standard dedup
-- signal. listing_status replaces legacy boolean flags: active | draft | sold
-- | inactive | deleted | archived.
CREATE TABLE dealer_inventories (
);

-- Projects to : bridge_listing_features   |   Sync key: None
-- One row per feature per listing. Maps to bridge_listing_features. category
-- CHECK values: tower | ballast | electronics | upholstery | engine_upgrade |
-- trailer | other. 'trailer' was missing from prior ERD — corrected v1.7.0.
CREATE TABLE listing_features (
);

-- [Phase 2 — not yet implemented] engine_brands: Engine manufacturer reference (e.g. Indmar, PCM, Ilmor, Volvo Penta). No Data Lake projection — Phase 2.

-- [Phase 2 — not yet implemented] engine_models: One row per engine model/config. drive_type: inboard | outboard | sterndrive | jet. fuel_type: gas | diesel | electric | hybrid. Referenced by boats_models.default_engine_model_id and boat_engine_instances. No Data Lake projection — Phase 2.

-- [Phase 2 — not yet implemented] boat_engine_instances: One row per physical engine per listing (twin-engine = 2 rows). engine_model_id nullable until ETL normalizes. No Data Lake projection — Phase 2.

-- [Phase 2 — not yet implemented] dealer_floorplan_config: Floorplan credit agreement terms per dealer (lender, credit line, rate index, curtailment schedule). No Data Lake projection — Phase 2 candidate for Dealer Financial Health mart.

-- [Phase 2 — not yet implemented] inventory_floorplan: One row per floored unit (1:1 with dealer_inventories). Tracks lender, floored amount, effective rate, manufacturer subsidy window, payoff status. No Data Lake projection — Phase 2.

-- [Phase 2 — not yet implemented] floorplan_curtailment_events: Time-series log of curtailment events per floored unit. Powers dealer financial risk analytics. No Data Lake projection — Phase 2.

-- Photo ingestion pipeline tracking (child of dealer_inventories). Not
-- projected into Data Lake.
CREATE TABLE listing_photos (
);

-- PostGIS point geometry per listing (WGS-84 SRID 4326). Not directly
-- projected into Data Lake — geo captured via dim_geography at zip/state
-- level.
CREATE TABLE listing_locations (
);

-- Unified per-field source tracking ETL audit table. Not projected into Data
-- Lake.
CREATE TABLE field_provenance (
);

-- Audit log of source-priority write conflicts. ETL audit table. Not projected
-- into Data Lake.
CREATE TABLE write_conflicts (
);

-- Minimal identity for private-sale listing posters. directus_id is TEXT/UUID
-- (only L2 table where this is UUID not INTEGER). Not projected into Data Lake
-- — PII-adjacent; member analytics use dim_member with hashed IDs.
CREATE TABLE private_sellers (
);

-- ================================================================================
-- DIMENSIONS
-- ================================================================================
-- ------------------------------------------------------------
-- dim_date
-- ------------------------------------------------------------
-- Standard date spine used across all fact tables.
CREATE TABLE dim_date (
    date_key                                   INT PRIMARY KEY,
    calendar_date                              DATE  -- NOT NULL,
    year                                       SMALLINT,
    quarter                                    SMALLINT,
    month                                      SMALLINT,
    week_of_year                               SMALLINT,
    day_of_week                                SMALLINT,
    season                                     VARCHAR(20),
    is_weekend                                 BOOLEAN
);

-- ------------------------------------------------------------
-- dim_geography
-- ------------------------------------------------------------
-- SCD Type    : 1
-- Geographic hierarchy used for regional performance analytics and location-
-- based filtering.
CREATE TABLE dim_geography (
    geo_key                                    INT PRIMARY KEY,
    zip                                        VARCHAR(10),
    city                                       VARCHAR(100),
    county                                     VARCHAR(100),
    state                                      CHAR(2),
    state_name                                 VARCHAR(50)  -- Full state name, e.g. Florida. Required for Regional tab State column display.,
    region                                     VARCHAR(50)  -- e.g. Southeast, Mountain West,
    dma                                        VARCHAR(100)  -- Nielsen DMA for media alignment. Also serves as the dealer territory proxy — see dim_dealer notes.,
    lat                                        DECIMAL(9,6),
    lon                                        DECIMAL(9,6)
);

-- ------------------------------------------------------------
-- dim_source
-- ------------------------------------------------------------
-- Data provenance tracking for every fact record. Enables source trust
-- hierarchy filtering.
CREATE TABLE dim_source (
    source_key                                 INT PRIMARY KEY,
    source_name                                VARCHAR(100)  -- e.g. BoatTrader, YachtWorld, Dealer Feed, Manufacturer, DTC Member,
    source_type                                VARCHAR(50)  -- Scrape | API | Manual | Member,
    scrape_domain                              VARCHAR(200)  -- e.g. boattrader.com, yachtworld.com,
    reliability_tier                           VARCHAR(20)  -- High | Medium | Low
);

-- ------------------------------------------------------------
-- dim_manufacturer
-- ------------------------------------------------------------
-- SCD Type    : 1
-- Boat manufacturers / brands. Root of the boat type hierarchy. Downstream
-- projection of l2_manufacturer (Layer 2 DB). Synced daily.
-- Foreign keys:
--   brand_tier_key -> dim_brand_tier.brand_tier_key  (nullable)  -- Segment tier for this manufacturer's primary product line. Resolved via dim_brand_tier price ranges.
CREATE TABLE dim_manufacturer (
    manufacturer_key                           INT PRIMARY KEY,
    l2_gear_brand_id                           INT  -- FK to gear_brands.id (Layer 2). Maintained by daily sync.,
    manufacturer_name                          VARCHAR(100),
    brand_tier_key                             INT  -- FK | FK to dim_brand_tier. Replaces the legacy brand_tier VARCHAR field for structured config-driven segmentation.,
    is_wakr_partner                            BOOLEAN  -- Paying data/dashboard partner,
    slug                                       VARCHAR(200)  -- From gear_brands.slug. Added v1.7.0.,
    country_of_origin                          VARCHAR(100)  -- From gear_brands.country_of_origin. Added v1.7.0.,
    is_active                                  BOOLEAN  -- From gear_brands.is_active. FALSE for discontinued brands. Added v1.7.0.
);

-- ------------------------------------------------------------
-- dim_brand_tier
-- ------------------------------------------------------------
-- SCD Type    : 1
-- Structured configuration table defining price-based boat market segments
-- (e.g. Entry, Mid, Premium). Each row defines a named tier with a price floor
-- and optional ceiling. Segment for any given listing is resolved by matching
-- listed_price (new boat) against min_price/max_price ranges at query time.
-- Powers the Segment Momentum view on the Overview tab and the Avg Days on
-- Market by Price Tier chart on the Pricing tab.
CREATE TABLE dim_brand_tier (
    brand_tier_key                             INT PRIMARY KEY,
    tier_name                                  VARCHAR(50)  -- e.g. Entry | Mid | Premium,
    min_price                                  DECIMAL(10,2)  -- Minimum new-boat list price (inclusive) for this segment,
    max_price                                  DECIMAL(10,2)  -- Maximum new-boat list price (exclusive). NULL = no upper bound (top-tier segment).,
    display_order                              SMALLINT  -- Sort order for dashboard segment display (1 = lowest tier)
);

-- ------------------------------------------------------------
-- dim_dealer_network
-- ------------------------------------------------------------
-- SCD Type    : 1
-- Dealer groups and multi-location networks. A dealer network (e.g. a regional
-- chain or franchise group) may operate many individual dealer locations. Each
-- location is a separate dim_dealer row; this table provides the rollup entity
-- for group-level analytics such as total network inventory, network-wide
-- sell-through, and aggregated dealer scorecards.
CREATE TABLE dim_dealer_network (
    dealer_network_key                         INT PRIMARY KEY,
    l2_dealer_group_id                         INT  -- FK to dealer_groups.id (Layer 2). Added v1.7.0.,
    network_name                               VARCHAR(200)  -- e.g. 'Lake Powell Marine Group', 'Southeast Malibu Dealers',
    parent_company                             VARCHAR(200)  -- Corporate parent entity if applicable,
    network_type                               VARCHAR(50)  -- Franchise | Independent | Corporate Chain,
    is_wakr_partner                            BOOLEAN  -- Network-level Wakr partnership flag,
    network_join_date                          DATE
);

-- ------------------------------------------------------------
-- dim_dealer
-- ------------------------------------------------------------
-- SCD Type    : 2
-- Individual boat dealer locations. Each physical location is a separate row.
-- Roll up to dealer group via dealer_network_key → dim_dealer_network. Dealers
-- may represent multiple manufacturers; all brand affiliations are tracked via
-- bridge_dealer_manufacturer. The primary_manufacturer_key is a denormalized
-- convenience FK for the dealer's primary/majority brand.
-- Foreign keys:
--   geo_key -> dim_geography.geo_key
--   dealer_network_key -> dim_dealer_network.dealer_network_key  (nullable)  -- Null for independent single-location dealers
--   primary_manufacturer_key -> dim_manufacturer.manufacturer_key  (nullable)  -- Denormalized primary brand; full list via bridge_dealer_manufacturer
CREATE TABLE dim_dealer (
    dealer_key                                 INT PRIMARY KEY,
    l2_dealer_id                               INT  -- FK to dealers.id (Layer 2). Added v1.7.0.,
    dealer_id_external                         VARCHAR(100)  -- Source system ID,
    dealer_name                                VARCHAR(200),
    address                                    VARCHAR(300),
    city                                       VARCHAR(100),
    state                                      CHAR(2),
    zip                                        VARCHAR(10),
    geo_key                                    INT  -- FK,
    dealer_network_key                         INT  -- FK,
    primary_manufacturer_key                   INT  -- FK | Primary brand affiliation — full multi-brand list in bridge_dealer_manufacturer,
    is_authorized                              BOOLEAN,
    is_wakr_partner                            BOOLEAN  -- Enrolled in Dealer Listings product,
    network_join_date                          DATE
);

-- ------------------------------------------------------------
-- dim_member
-- ------------------------------------------------------------
-- SCD Type    : 2
-- DTC members registered on wakr.co. PII-safe — hashed IDs only.
-- Foreign keys:
--   geo_key -> dim_geography.geo_key
CREATE TABLE dim_member (
    member_key                                 INT PRIMARY KEY,
    member_id_hashed                           VARCHAR(64)  -- SHA-256 hash of source member ID — no PII,
    geo_key                                    INT  -- FK,
    join_date                                  DATE,
    skill_level                                VARCHAR(50)  -- Beginner | Intermediate | Advanced,
    membership_tier                            VARCHAR(50)
);

-- ------------------------------------------------------------
-- dim_lake
-- ------------------------------------------------------------
-- SCD Type    : 1
-- Lakes and waterways where towboats are used. Unique to the watersports
-- market — supports usage-pattern analytics.
-- Foreign keys:
--   geo_key -> dim_geography.geo_key
CREATE TABLE dim_lake (
    lake_key                                   INT PRIMARY KEY,
    l2_waters_id                               INT  -- FK to waters.id (Layer 2). Added v1.7.0.,
    lake_name                                  VARCHAR(200),
    state                                      CHAR(2),
    geo_key                                    INT  -- FK,
    surface_acres                              INT,
    lake_type                                  VARCHAR(50)  -- Reservoir | Natural | Private,
    avg_depth_ft                               DECIMAL(6,2)  -- From waters.avg_depth_ft (Layer 2). Added v1.7.0.,
    salinity                                   VARCHAR(20)  -- CHECK: fresh | salt | brackish. From waters.salinity (Layer 2). Added v1.7.0.
);

-- ------------------------------------------------------------
-- dim_boat_model
-- ------------------------------------------------------------
-- SCD Type    : 1
-- The TYPE/TEMPLATE dimension — one row per make/model/year combination.
-- Represents the manufacturer's base product specification. base_* fields
-- (base_engine_hp, base_ballast_lbs, base_tower_included) are the factory-
-- standard configuration for the model and should not be confused with actual
-- per-instance values, which are stored on dim_boat_instance and
-- bridge_listing_features. Downstream projection of l2_boat_model (Layer 2
-- DB), enriched with scrape-derived data. Synced daily. The Model filter
-- dropdown on all dashboard tabs resolves its value list from l2_boat_model
-- (Layer 2), not this table, to ensure completeness independent of scraped
-- listing coverage.
-- Foreign keys:
--   manufacturer_key -> dim_manufacturer.manufacturer_key
CREATE TABLE dim_boat_model (
    boat_model_key                             INT PRIMARY KEY,
    l2_boats_model_id                          INT  -- FK to boats_models.id (Layer 2). Maintained by daily sync.,
    manufacturer_key                           INT  -- FK,
    make                                       VARCHAR(100),
    model                                      VARCHAR(200),
    model_year                                 SMALLINT,
    boat_type                                  VARCHAR(50)  -- Ski | Wake | Surf | Crossover,
    hull_length_ft                             DECIMAL(5,2)  -- Model-defining spec from manufacturer,
    engine_type                                VARCHAR(100)  -- Engine family/series name — model-defining,
    base_engine_hp                             SMALLINT  -- Factory standard HP for this model. Actual instance HP may differ (upgrades) — see dim_boat_instance / bridge_listing_features,
    base_tower_included                        BOOLEAN  -- True if tower is standard on this model. Actual presence on a specific boat tracked on dim_boat_instance,
    base_ballast_lbs                           INT  -- Factory standard ballast. Actual ballast on a specific boat tracked on dim_boat_instance / bridge_listing_features,
    msrp                                       DECIMAL(10,2)  -- From manufacturer feed when available,
    default_engine_model_id                    INT  -- From boats_models.default_engine_model_id → engine_models.id. Phase 2 only — engine dimension not yet built. Added v1.7.0.,
    is_active                                  BOOLEAN  -- From boats_models.is_active. FALSE for discontinued model-years. Added v1.7.0.
);

-- ------------------------------------------------------------
-- dim_boat_instance
-- ------------------------------------------------------------
-- SCD Type    : 2
-- The PHYSICAL UNIT dimension — one row per actual boat (VIN or surrogate).
-- Many instances per model. Stores actual as-delivered/as-listed configuration
-- — use this for per-hull values that may differ from the model baseline (e.g.
-- upgraded engine, added ballast, aftermarket tower).
-- Foreign keys:
--   boat_model_key -> dim_boat_model.boat_model_key
--   dealer_key -> dim_dealer.dealer_key  (nullable)
CREATE TABLE dim_boat_instance (
    boat_key                                   INT PRIMARY KEY,
    canonical_boat_id                          UUID  -- Durable cross-source boat identity UUID from dealer_inventories.canonical_boat_id (Layer 2). Assigned on first insert; coalesced by dedup worker. HIN is gold-standard dedup signal. Added v1.7.0.,
    boat_model_key                             INT  -- FK,
    vin                                        VARCHAR(50)  -- Nullable — older/used boats often lack VIN; deduplication uses make+model+year+hours+price-tolerance,
    is_new                                     BOOLEAN,
    manufacture_date                           DATE,
    current_hours                              INT  -- Updated as new listing data arrives,
    condition                                  VARCHAR(20)  -- Excellent | Good | Fair,
    color                                      VARCHAR(100),
    actual_engine_hp                           SMALLINT  -- Actual HP if known and differs from model base; null = assume base model spec,
    has_tower                                  BOOLEAN  -- Actual tower presence on this unit; null = unknown,
    actual_ballast_lbs                         INT  -- Actual ballast on this unit; null = assume base model spec,
    dealer_key                                 INT  -- FK | Last known dealer association
);

-- ------------------------------------------------------------
-- dim_competitor_brand
-- ------------------------------------------------------------
-- SCD Type    : 1
-- Competitor brands for Phase 2 competitive overlay analytics.
-- Phase       : 2
CREATE TABLE dim_competitor_brand (
    competitor_key                             INT PRIMARY KEY,
    brand_name                                 VARCHAR(100),
    brand_tier                                 VARCHAR(50)
);

-- ================================================================================
-- FACT TABLES
-- ================================================================================
-- ------------------------------------------------------------
-- fact_listing_snapshot
-- ------------------------------------------------------------
-- Cardinality : {'fact_to_dim_date': 'many-to-one', 'fact_to_dim_boat_instance': 'many-to-one', 'fact_to_dim_boat_model': 'many-to-one', 'fact_to_dim_dealer': 'many-to-zero-or-one', 'fact_to_dim_geography': 'many-to-one', 'fact_to_dim_source': 'many-to-one'}
-- Core fact table. One row per listing per day. Backbone of pricing, time-on-
-- market, and inventory level analytics.
-- Grain       : one row per listing per day
-- Partitioning: date_key (month) + manufacturer prefix on boat_model_key
-- Foreign keys:
--   date_key -> dim_date.date_key
--   boat_key -> dim_boat_instance.boat_key
--   boat_model_key -> dim_boat_model.boat_model_key
--   dealer_key -> dim_dealer.dealer_key  (nullable)
--   geo_key -> dim_geography.geo_key
--   source_key -> dim_source.source_key
CREATE TABLE fact_listing_snapshot (
    snapshot_key                               BIGINT PRIMARY KEY,
    listing_id                                 VARCHAR(200)  -- Source system listing identifier,
    date_key                                   INT  -- FK,
    boat_key                                   INT  -- FK,
    boat_model_key                             INT  -- FK,
    dealer_key                                 INT  -- FK,
    geo_key                                    INT  -- FK,
    source_key                                 INT  -- FK,
    listed_price                               DECIMAL(10,2),
    original_list_price                        DECIMAL(10,2)  -- First observed price for this listing,
    price_change_amount                        DECIMAL(10,2)  -- Delta from prior day snapshot,
    days_on_market                             INT  -- Computed from first_seen_date,
    listing_status                             VARCHAR(30)  -- Active | Removed | Price Reduced,
    is_new_listing                             BOOLEAN  -- True on first day seen,
    is_removed                                 BOOLEAN  -- True on last day seen — inferred sold or delisted,
    mileage_hours                              INT,
    condition_notes                            VARCHAR(500),
    listing_url                                VARCHAR(500),
    first_seen_date                            DATE,
    last_seen_date                             DATE
);

-- ------------------------------------------------------------
-- fact_estimated_sale
-- ------------------------------------------------------------
-- Cardinality : {'fact_to_dim_date': 'many-to-one', 'fact_to_dim_boat_instance': 'many-to-one', 'fact_to_dim_boat_model': 'many-to-one', 'fact_to_dim_dealer': 'many-to-zero-or-one', 'fact_to_dim_geography': 'many-to-one', 'fact_to_dim_source': 'many-to-one'}
-- One row per inferred sale event. A listing removed after active status is
-- treated as a likely sale. confidence_score allows downstream analytics to
-- discount low-confidence records.
-- Grain       : one row per inferred sale event
-- Foreign keys:
--   date_key -> dim_date.date_key
--   boat_key -> dim_boat_instance.boat_key
--   boat_model_key -> dim_boat_model.boat_model_key
--   dealer_key -> dim_dealer.dealer_key  (nullable)
--   geo_key -> dim_geography.geo_key
--   source_key -> dim_source.source_key
CREATE TABLE fact_estimated_sale (
    est_sale_key                               BIGINT PRIMARY KEY,
    listing_id                                 VARCHAR(200),
    date_key                                   INT  -- FK,
    boat_key                                   INT  -- FK,
    boat_model_key                             INT  -- FK,
    dealer_key                                 INT  -- FK,
    geo_key                                    INT  -- FK,
    source_key                                 INT  -- FK,
    final_listed_price                         DECIMAL(10,2),
    days_on_market                             INT,
    confidence_score                           DECIMAL(4,3)  -- 0.000–1.000; sale vs. delisting confidence,
    sale_type                                  VARCHAR(20)  -- New | Used
);

-- ------------------------------------------------------------
-- fact_listing_engagement
-- ------------------------------------------------------------
-- Cardinality : {'fact_to_dim_date': 'many-to-one', 'fact_to_dim_boat_instance': 'many-to-one', 'fact_to_dim_boat_model': 'many-to-one', 'fact_to_dim_dealer': 'many-to-one'}
-- Impressions, clicks, and leads for listings actively hosted on the Wakr
-- platform. Powers Dealer Performance Indicators, Model-Level Impressions, and
-- Lead Activity Tracking.
-- Grain       : one row per listing per day
-- Foreign keys:
--   date_key -> dim_date.date_key
--   boat_key -> dim_boat_instance.boat_key
--   boat_model_key -> dim_boat_model.boat_model_key
--   dealer_key -> dim_dealer.dealer_key
CREATE TABLE fact_listing_engagement (
    engagement_key                             BIGINT PRIMARY KEY,
    listing_id                                 VARCHAR(200),
    date_key                                   INT  -- FK,
    boat_key                                   INT  -- FK,
    boat_model_key                             INT  -- FK,
    dealer_key                                 INT  -- FK,
    impressions                                INT,
    clicks                                     INT,
    leads_generated                            INT,
    click_through_rate                         DECIMAL(6,4)  -- Computed: clicks / impressions
);

-- ------------------------------------------------------------
-- fact_member_activity
-- ------------------------------------------------------------
-- Cardinality : {'fact_to_dim_date': 'many-to-one', 'fact_to_dim_member': 'many-to-one', 'fact_to_dim_boat_instance': 'many-to-zero-or-one', 'fact_to_dim_boat_model': 'many-to-one', 'fact_to_dim_dealer': 'many-to-zero-or-one', 'fact_to_dim_lake': 'many-to-zero-or-one'}
-- Activity from wakr.co DTC members — boat ownership, lake visits, lessons,
-- dealer touchpoints.
-- Grain       : one row per member activity event
-- Phase       : 2
-- Foreign keys:
--   date_key -> dim_date.date_key
--   member_key -> dim_member.member_key
--   boat_key -> dim_boat_instance.boat_key  (nullable)
--   boat_model_key -> dim_boat_model.boat_model_key
--   dealer_key -> dim_dealer.dealer_key  (nullable)
--   lake_key -> dim_lake.lake_key  (nullable)
CREATE TABLE fact_member_activity (
    activity_key                               BIGINT PRIMARY KEY,
    date_key                                   INT  -- FK,
    member_key                                 INT  -- FK,
    boat_key                                   INT  -- FK,
    boat_model_key                             INT  -- FK,
    dealer_key                                 INT  -- FK,
    lake_key                                   INT  -- FK,
    activity_type                              VARCHAR(50)  -- Ride | Lesson | Service | Dealer Visit,
    is_owner                                   BOOLEAN
);

-- ------------------------------------------------------------
-- fact_marketplace_behavior
-- ------------------------------------------------------------
-- Cardinality : {'fact_to_dim_date': 'many-to-one', 'fact_to_dim_member': 'many-to-zero-or-one', 'fact_to_dim_boat_model': 'many-to-one', 'fact_to_dim_geography': 'many-to-one'}
-- Browsing, comparison, and purchase events on the Wakr marketplace. Enables
-- demand shift detection before inventory data reflects it. Anonymous sessions
-- have no member_key.
-- Grain       : one row per marketplace event
-- Phase       : 2
-- Foreign keys:
--   date_key -> dim_date.date_key
--   member_key -> dim_member.member_key  (nullable)
--   boat_model_key -> dim_boat_model.boat_model_key
--   geo_key -> dim_geography.geo_key
CREATE TABLE fact_marketplace_behavior (
    behavior_key                               BIGINT PRIMARY KEY,
    date_key                                   INT  -- FK,
    member_key                                 INT  -- FK,
    boat_model_key                             INT  -- FK,
    geo_key                                    INT  -- FK,
    event_type                                 VARCHAR(50)  -- View | Compare | Save | Mention | Purchase,
    session_id                                 VARCHAR(100)
);

-- ================================================================================
-- BRIDGE TABLES
-- ================================================================================
-- ------------------------------------------------------------
-- bridge_dealer_manufacturer
-- ------------------------------------------------------------
-- Many-to-many affiliation between dealer locations and manufacturers/brands.
-- A dealer may be an authorized dealer for multiple brands (e.g. Malibu + Axis
-- + Centurion). The is_primary flag identifies the dealer's primary brand for
-- convenience denormalization. Use this table for any multi-brand dealer
-- queries; the primary_manufacturer_key FK on dim_dealer is a denormalized
-- shortcut for single-brand lookups.
-- Foreign keys:
--   dealer_key -> dim_dealer.dealer_key
--   manufacturer_key -> dim_manufacturer.manufacturer_key
CREATE TABLE bridge_dealer_manufacturer (
    dealer_key                                 INT  -- FK,
    manufacturer_key                           INT  -- FK,
    is_primary                                 BOOLEAN  -- True for the dealer's dominant brand,
    is_authorized                              BOOLEAN  -- Manufacturer-confirmed authorized dealer status,
    authorization_type                         VARCHAR(50)  -- CHECK (Layer 2 values): full | service_only | parts_only | pending | other. CORRECTED v1.7.0 — prior ERD had Full | Limited | Service-Only.,
    effective_date                             DATE,
    expiry_date                                DATE
);

-- ------------------------------------------------------------
-- bridge_listing_features
-- ------------------------------------------------------------
-- Multi-valued listing features extracted from scrape text (e.g. tower type,
-- ballast configuration, electronics). One listing → many feature rows. Used
-- for comparable listing matching in the Trade-In & Valuation Application.
-- Foreign keys:
--   boat_model_key -> dim_boat_model.boat_model_key
CREATE TABLE bridge_listing_features (
    listing_id                                 VARCHAR(200),
    boat_model_key                             INT  -- FK,
    feature_category                           VARCHAR(100)  -- Maps to listing_features.category (Layer 2). CHECK values: tower | ballast | electronics | upholstery | engine_upgrade | trailer | other. CORRECTED v1.7.0 — 'trailer' was missing.,
    feature_value                              VARCHAR(200)
);

-- ================================================================================
-- DATA MARTS
-- ================================================================================
-- ------------------------------------------------------------
-- mart_daily_snapshot
-- ------------------------------------------------------------
-- Grain keys  : manufacturer_key, boat_model_key, state, inventory_type, date_key
-- Source facts: fact_listing_snapshot, fact_estimated_sale
-- Time ranges : T7, T30, T90, YTD, L12M
-- Parameters  : time_range, inventory_type, make, model, state
-- STOCK columns are point-in-time (do NOT SUM across days — use latest row or
-- AVG). FLOW columns are daily event counts (safe to SUM across any window).
-- See schema.query_layer_notes for full rules.
-- Central analytics workhorse mart. One row per manufacturer / boat_model /
-- state / inventory_type / day. Every dashboard metric is a column on this
-- row. All parameter combinations (make, model, state, inventory_type, time
-- range) are resolved at query time via WHERE and GROUP BY — no permutations
-- are pre-stored. Refreshed nightly to keep trailing window metrics current
-- relative to the user's view date. Also refreshed on scrape completion when
-- new source data arrives.
-- Grain       : manufacturer_key / boat_model_key / state / inventory_type / date_key
-- Refresh     : nightly + scrape-triggered
CREATE TABLE mart_daily_snapshot (
    date_key                                   INT  -- FK → dim_date.date_key | Calendar date this row represents.,
    manufacturer_key                           INT  -- FK → dim_manufacturer.manufacturer_key,
    boat_model_key                             INT  -- FK → dim_boat_model.boat_model_key | NULL row included per manufacturer to support Make-only (all models) queries without a separate rollup pass.,
    state                                      CHAR(2)  -- State abbreviation. NULL row included to support all-states rollup.,
    inventory_type                             VARCHAR(10)  -- New | Used. Combined is resolved at query time by omitting the inventory_type filter — not stored as a third value to avoid double-counting.,
    active_listings                            INT  -- Count of listings with listing_status = Active as of this date. Do NOT SUM across days — use latest date in window for current count, or AVG for period average.,
    avg_list_price                             DECIMAL(10,2)  -- Average listed_price for active listings on this date. Do NOT SUM across days — use AVG(avg_list_price) weighted by active_listings when rolling up across days.,
    median_list_price                          DECIMAL(10,2)  -- Median listed_price for active listings on this date. Approximated at daily aggregation. Do NOT SUM across days.,
    avg_dom                                    DECIMAL(6,2)  -- Average days_on_market for active listings on this date. Do NOT SUM — use AVG(avg_dom) weighted by active_listings when rolling up.,
    dom_bucket_0_7                             INT  -- Active listings with DOM 0-7 days on this date. Do NOT SUM across days.,
    dom_bucket_8_15                            INT  -- Active listings with DOM 8-15 days on this date. Do NOT SUM across days.,
    dom_bucket_16_30                           INT  -- Active listings with DOM 16-30 days on this date. Do NOT SUM across days.,
    dom_bucket_31_60                           INT  -- Active listings with DOM 31-60 days on this date. Do NOT SUM across days.,
    dom_bucket_60_plus                         INT  -- Active listings with DOM 60+ days on this date. Do NOT SUM across days.,
    min_list_price                             DECIMAL(10,2)  -- Minimum listed_price among active listings on this date. Supports price band floor derivation.,
    max_list_price                             DECIMAL(10,2)  -- Maximum listed_price among active listings on this date. Supports price band ceiling derivation.,
    listing_count_band_under_60k               INT  -- Active listings priced under $60k on this date.,
    listing_count_band_60_80k                  INT  -- Active listings priced $60k-$80k on this date.,
    listing_count_band_80_100k                 INT  -- Active listings priced $80k-$100k on this date.,
    listing_count_band_100_120k                INT  -- Active listings priced $100k-$120k on this date.,
    listing_count_band_120_140k                INT  -- Active listings priced $120k-$140k on this date.,
    listing_count_band_over_140k               INT  -- Active listings priced over $140k on this date.,
    avg_dom_band_under_60k                     DECIMAL(6,2)  -- Avg DOM for under $60k active listings on this date.,
    avg_dom_band_60_80k                        DECIMAL(6,2)  -- Avg DOM for $60k-$80k active listings on this date.,
    avg_dom_band_80_100k                       DECIMAL(6,2)  -- Avg DOM for $80k-$100k active listings on this date.,
    avg_dom_band_100_120k                      DECIMAL(6,2)  -- Avg DOM for $100k-$120k active listings on this date.,
    avg_dom_band_120_140k                      DECIMAL(6,2)  -- Avg DOM for $120k-$140k active listings on this date.,
    avg_dom_band_over_140k                     DECIMAL(6,2)  -- Avg DOM for over $140k active listings on this date.,
    new_listings                               INT  -- Count of listings where is_new_listing = true on this date. Safe to SUM across any window. Drives Inventory Added (T30) KPI.,
    removed_listings                           INT  -- Count of listings where is_removed = true on this date. Proxy for boats sold. Safe to SUM across any window. Drives Boats Sold KPI.,
    price_reduced_listings                     INT  -- Count of listings where price_change_amount < 0 on this date. Safe to SUM — but deduplicate by listing_id across window to avoid counting the same listing multiple times for pct_listings_with_price_cut.,
    dom_status                                 VARCHAR(20)  -- Velocity classification for this row: Fast (<15d avg_dom) | Healthy (15-22d) | Slow (23-30d) | Very Slow (30d+). Pre-classified at mart refresh. Use latest date in window.,
    sell_through_rate                          DECIMAL(6,4)  -- removed_listings / active_listings for this date. Pre-computed for convenience. For window roll-up: SUM(removed_listings) / AVG(active_listings) across window.,
    days_supply                                DECIMAL(8,2)  -- active_listings / (removed_listings_t30 / 30.0). Requires a 30-day trailing window regardless of selected time range. Always computed against T30 removed_listings.,
    is_partial_scrape_day                      BOOLEAN  -- TRUE if this date falls within an active scrape window and data may be incomplete. Query layer should exclude or flag partial days for flow metrics.,
    last_scrape_date                           DATE  -- Date of the most recent scrape that contributed data to this row. Allows query layer to surface data freshness to the user.
);
CREATE INDEX idx_mart_daily_snapshot_PRIMARY_KEY_manufacturer_key_boat_model_key_s ON mart_daily_snapshot (PRIMARY KEY (manufacturer_key, boat_model_key, state, inventory_type, date_key));
CREATE INDEX idx_mart_daily_snapshot_INDEX_date_key_—_for_trailing_window_date_ran ON mart_daily_snapshot (INDEX (date_key) — for trailing window date range scans);
CREATE INDEX idx_mart_daily_snapshot_INDEX_manufacturer_key_date_key_—_for_make-le ON mart_daily_snapshot (INDEX (manufacturer_key, date_key) — for make-level all-models queries);
CREATE INDEX idx_mart_daily_snapshot_INDEX_state_date_key_—_for_regional_tab_all-m ON mart_daily_snapshot (INDEX (state, date_key) — for regional tab all-makes queries);

-- ------------------------------------------------------------
-- mart_inventory_summary
-- ------------------------------------------------------------
-- Grain keys  : manufacturer_key, boat_model_key, geo_key, week_key
-- Source facts: fact_listing_snapshot, fact_estimated_sale
-- Time ranges : monthly grain only — trailing windows via mart_daily_snapshot
-- Parameters  : time_range, inventory_type, make, model
-- Pre-aggregated active listing counts, inventory turnover, and days-on-market
-- distribution by make/model/region/week. Powers the Active Listings Monitor,
-- Days on Market Distribution chart, Total Inventory Trend line chart, and
-- Inventory & Velocity table on the Inventory tab. Grain expanded in v1.5.0 to
-- include boat_model_key, enabling Model filter on the Inventory tab. v1.8.0:
-- Trailing window metrics removed — all served by mart_daily_snapshot at query
-- time. This mart retains monthly-grain metrics only: those requiring
-- calendar-month alignment (MoM comparisons, momentum_status classification,
-- vs_market_pct). Refreshed on scrape-triggered schedule only.
-- Grain       : make / model / state / month (monthly pre-agg); use mart_daily_snapshot for sub-monthly windows
-- Refresh     : scrape-triggered only (not nightly)
CREATE TABLE mart_inventory_summary (
);

-- ------------------------------------------------------------
-- mart_regional_summary
-- ------------------------------------------------------------
-- Grain keys  : state, manufacturer_key, boat_model_key, month_key
-- Source facts: fact_listing_snapshot, fact_estimated_sale
-- Time ranges : monthly grain only — trailing windows via mart_daily_snapshot
-- Parameters  : time_range, inventory_type, make, model, state
-- NEW in v1.5.0. State-level market rollup supporting the Regional tab. One
-- row per state / make / model / month. Powers the four KPI boxes (Fastest
-- Market, Slowest Market, Top Growth State, Sales Trends), the State Market
-- Map choropleth, State Market Leaders top/bottom rankings, and the State
-- Market Overview detail table. Grain includes boat_model_key to support the
-- Model filter parameter added in v1.5.0. v1.8.0: Trailing window metrics
-- removed — all served by mart_daily_snapshot at query time. This mart retains
-- monthly-grain metrics only: those requiring calendar-month alignment (MoM
-- comparisons, momentum_status classification, vs_market_pct). Refreshed on
-- scrape-triggered schedule only.
-- Grain       : state / make / model / month
-- Refresh     : scrape-triggered only (not nightly)
CREATE TABLE mart_regional_summary (
);

-- ------------------------------------------------------------
-- mart_pricing_trends
-- ------------------------------------------------------------
-- Grain keys  : manufacturer_key, boat_model_key, geo_key, month_key
-- Source facts: fact_listing_snapshot
-- Time ranges : monthly grain only — trailing windows via mart_daily_snapshot
-- Parameters  : time_range, inventory_type, make, model
-- Pre-aggregated advertised price distributions, median prices, price
-- movement, and price-band breakdowns by make/model/region/month. Powers the
-- Pricing tab KPI boxes, Avg Days on Market by Price Tier chart, Listings by
-- Price Tier chart, and Model Price Efficiency table. Grain includes
-- boat_model_key to support Model filter added in v1.5.0. v1.8.0: Trailing
-- window metrics removed — all served by mart_daily_snapshot at query time.
-- This mart retains monthly-grain metrics only: those requiring calendar-month
-- alignment (MoM comparisons, momentum_status classification, vs_market_pct).
-- Refreshed on scrape-triggered schedule only.
-- Grain       : make / model / region / month
-- Refresh     : scrape-triggered only (not nightly)
CREATE TABLE mart_pricing_trends (
);

-- ------------------------------------------------------------
-- mart_time_on_market
-- ------------------------------------------------------------
-- Grain keys  : manufacturer_key, boat_model_key, geo_key, month_key
-- Source facts: fact_listing_snapshot
-- Time ranges : monthly grain only — trailing windows via mart_daily_snapshot
-- Parameters  : time_range, inventory_type, make, model
-- Average and percentile days-on-market by make/model/region/month with aging
-- distribution buckets. v1.8.0: Trailing window metrics removed — all served
-- by mart_daily_snapshot at query time. This mart retains monthly-grain
-- metrics only: those requiring calendar-month alignment (MoM comparisons,
-- momentum_status classification, vs_market_pct). Refreshed on scrape-
-- triggered schedule only.
-- Grain       : make / model / region / month
-- Refresh     : scrape-triggered only (not nightly)
CREATE TABLE mart_time_on_market (
);

-- ------------------------------------------------------------
-- mart_dealer_scorecard
-- ------------------------------------------------------------
-- Source facts: fact_listing_snapshot, fact_listing_engagement, fact_estimated_sale
-- Dealer-location and dealer-network performance metrics benchmarked against
-- network averages: inventory count, avg days-on-market, leads, impressions,
-- estimated sell-through. Supports both individual location view and rolled-up
-- dealer_network_key grouping. Dealers tab not yet implemented — mart retained
-- for Phase 1 readiness.
-- Grain       : dealer / month
CREATE TABLE mart_dealer_scorecard (
);

-- ------------------------------------------------------------
-- mart_estimated_velocity
-- ------------------------------------------------------------
-- Grain keys  : manufacturer_key, boat_model_key, geo_key, month_key
-- Source facts: fact_estimated_sale, fact_listing_snapshot
-- Time ranges : monthly grain only — trailing windows via mart_daily_snapshot
-- Parameters  : time_range, inventory_type, make, model
-- Estimated sell-through counts and pace by make/model/region/month. Powers
-- velocity rankings including Demand-Supply Ratio, Momentum, and Avg DOM
-- trend. v1.8.0: Trailing window metrics removed — all served by
-- mart_daily_snapshot at query time. This mart retains monthly-grain metrics
-- only: those requiring calendar-month alignment (MoM comparisons,
-- momentum_status classification, vs_market_pct). Refreshed on scrape-
-- triggered schedule only.
-- Grain       : make / model / region / month
-- Refresh     : scrape-triggered only (not nightly)
CREATE TABLE mart_estimated_velocity (
);

-- ------------------------------------------------------------
-- mart_member_usage
-- ------------------------------------------------------------
-- Source facts: fact_member_activity
-- Boat model usage patterns by lake and region. Surfaces which models are
-- actively ridden in specific areas.
-- Grain       : lake / model / month
-- Phase       : 2
CREATE TABLE mart_member_usage (
);

-- ================================================================================
-- RELATIONSHIPS  (informational — enforce via application / ETL)
-- ================================================================================
-- dim_dealer                               many-to-one                  dim_geography  via geo_key
-- dim_dealer                               many-to-zero-or-one          dim_dealer_network  via dealer_network_key
-- dim_dealer                               many-to-zero-or-one          dim_manufacturer  via primary_manufacturer_key  -- Denormalized primary brand only; full list via bridge_dealer_manufacturer
-- bridge_dealer_manufacturer               many-to-one                  dim_dealer  via dealer_key
-- bridge_dealer_manufacturer               many-to-one                  dim_manufacturer  via manufacturer_key
-- dim_member                               many-to-one                  dim_geography  via geo_key
-- dim_lake                                 many-to-one                  dim_geography  via geo_key
-- dim_boat_instance                        many-to-one                  dim_boat_model  via boat_model_key
-- dim_boat_model                           many-to-one                  dim_manufacturer  via manufacturer_key
-- dim_boat_instance                        many-to-zero-or-one          dim_dealer  via dealer_key
-- fact_listing_snapshot                    many-to-one                  dim_date  via date_key
-- fact_listing_snapshot                    many-to-one                  dim_boat_instance  via boat_key
-- fact_listing_snapshot                    many-to-one                  dim_boat_model  via boat_model_key
-- fact_listing_snapshot                    many-to-zero-or-one          dim_dealer  via dealer_key
-- fact_listing_snapshot                    many-to-one                  dim_geography  via geo_key
-- fact_listing_snapshot                    many-to-one                  dim_source  via source_key
-- fact_estimated_sale                      many-to-one                  dim_date  via date_key
-- fact_estimated_sale                      many-to-one                  dim_boat_instance  via boat_key
-- fact_estimated_sale                      many-to-one                  dim_boat_model  via boat_model_key
-- fact_estimated_sale                      many-to-zero-or-one          dim_dealer  via dealer_key
-- fact_estimated_sale                      many-to-one                  dim_geography  via geo_key
-- fact_estimated_sale                      many-to-one                  dim_source  via source_key
-- fact_listing_engagement                  many-to-one                  dim_date  via date_key
-- fact_listing_engagement                  many-to-one                  dim_boat_instance  via boat_key
-- fact_listing_engagement                  many-to-one                  dim_boat_model  via boat_model_key
-- fact_listing_engagement                  many-to-one                  dim_dealer  via dealer_key
-- fact_member_activity                     many-to-one                  dim_date  via date_key
-- fact_member_activity                     many-to-one                  dim_member  via member_key
-- fact_member_activity                     many-to-zero-or-one          dim_boat_instance  via boat_key
-- fact_member_activity                     many-to-one                  dim_boat_model  via boat_model_key
-- fact_member_activity                     many-to-zero-or-one          dim_dealer  via dealer_key
-- fact_member_activity                     many-to-zero-or-one          dim_lake  via lake_key
-- fact_marketplace_behavior                many-to-one                  dim_date  via date_key
-- fact_marketplace_behavior                many-to-zero-or-one          dim_member  via member_key
-- fact_marketplace_behavior                many-to-one                  dim_boat_model  via boat_model_key
-- fact_marketplace_behavior                many-to-one                  dim_geography  via geo_key
-- bridge_listing_features                  many-to-one                  dim_boat_model  via boat_model_key
-- mart_regional_summary                    many-to-one                  dim_geography  via state → dim_geography.state  -- Join on state CHAR(2) for full state name display in Regional tab table.
-- mart_regional_summary                    many-to-one                  dim_manufacturer  via manufacturer_key
-- mart_regional_summary                    many-to-one                  dim_boat_model  via boat_model_key
-- mart_daily_snapshot                      many-to-one                  dim_date  via date_key
-- mart_daily_snapshot                      many-to-one                  dim_manufacturer  via manufacturer_key
-- mart_daily_snapshot                      many-to-one                  dim_boat_model  via boat_model_key
-- mart_daily_snapshot                      many-to-one                  dim_geography  via state → dim_geography.state
-- dim_manufacturer                         many-to-one                  gear_brands  via l2_gear_brand_id  [layer2]  -- Downstream projection of gear_brands. Sync daily.
-- dim_boat_model                           many-to-one                  boats_models  via l2_boats_model_id  [layer2]  -- Downstream projection of boats_models. Sync daily.
-- dim_lake                                 many-to-one                  waters  via l2_waters_id  [layer2]  -- Downstream projection of waters. Sync daily.
-- dim_dealer_network                       many-to-one                  dealer_groups  via l2_dealer_group_id  [layer2]  -- Downstream projection of dealer_groups. Sync daily.
-- dim_dealer                               many-to-one                  dealers  via l2_dealer_id  [layer2]  -- Downstream projection of dealers. Sync daily.
-- dim_dealer                               many-to-zero-or-one          waters  via dealers.water_id → dim_lake.l2_waters_id  [layer2]  -- dealers.water_id links dealer location to nearest lake. Resolved via dim_lake in Data Lake.

-- ================================================================================
-- QUERY LAYER NOTES
-- ================================================================================
-- [description]
--   Rules the query layer must follow when reading from mart_daily_snapshot.
--   These are not enforced by the database — they must be implemented in the API
--   or BI layer.

-- [stock_vs_flow]
--   {'stock_metrics': {'columns': ['active_listings', 'avg_list_price',
--   'median_list_price', 'avg_dom', 'dom_bucket_0_7', 'dom_bucket_8_15',
--   'dom_bucket_16_30', 'dom_bucket_31_60', 'dom_bucket_60_plus'], 'rule': 'Do
--   NOT SUM across days. For current state: use MAX(date_key) row in the window.
--   For period average: AVG() across days in the window. For period-end
--   snapshot: use the single row where date_key = last day of window.',
--   'example': 'Active listings for Malibu 23 LSV FL New T30 = value on the most
--   recent date_key in the window, not the sum of 30 days of active_listing
--   counts.'}, 'flow_metrics': {'columns': ['new_listings', 'removed_listings'],
--   'rule': 'Safe to SUM across any window. These are daily counts of events
--   (listings added or removed that day).', 'example': 'Inventory Added T30 =
--   SUM(new_listings) WHERE date_key >= CURRENT_DATE - 30.'}}

-- [parameter_resolution]
--   {'make_filter': "WHERE manufacturer_key = X. When 'All Makes': omit WHERE
--   clause or no filter.", 'model_filter': "WHERE boat_model_key = Y. Only valid
--   when a specific Make is selected. When 'All Models': omit.",
--   'inventory_type_filter': "WHERE inventory_type IN ('New', 'Used',
--   'New','Used'). 'Combined' = no filter (all rows).", 'state_filter': "WHERE
--   state = 'FL'. 'All States': omit.", 'time_range': {'T7': 'WHERE date_key >=
--   CURRENT_DATE - 7', 'T30': 'WHERE date_key >= CURRENT_DATE - 30', 'T90':
--   'WHERE date_key >= CURRENT_DATE - 90', 'YTD': "WHERE date_key >=
--   DATE_TRUNC('year', CURRENT_DATE)", 'L12M': 'WHERE date_key >= CURRENT_DATE -
--   365'}}

-- [vs_market_pct]
--   Comparison % (user company vs market) cannot be derived from
--   mart_daily_snapshot alone in a single pass. Requires two aggregations: (1)
--   filtered to user's make/model, (2) unfiltered or filtered to all other
--   makes. Sourced from monthly mart pre-computed columns where available, or
--   computed as two subqueries against mart_daily_snapshot for trailing windows.

-- [all_states_rollup]
--   Aggregating 'All States' over a 30-day window on mart_daily_snapshot may
--   touch ~30 days × 50 states × N models rows. For stock metrics use AVG or
--   latest-date value per state then aggregate. Index on (manufacturer_key,
--   boat_model_key, date_key) is critical for performance.

-- [boats_sold_proxy]
--   removed_listings is the proxy for boats sold (listing removed after active
--   status = inferred sale). This mirrors fact_estimated_sale logic. For
--   precision, join to fact_estimated_sale filtered by confidence_score
--   threshold.

-- ================================================================================
-- REFRESH SCHEDULE
-- ================================================================================
-- description: Two independent refresh triggers. Nightly refresh keeps trailing window metrics current. Scrape-triggered refresh updates fact data when new source data arrives.
-- nightly_refresh: {'trigger': 'Nightly calendar job — runs regardless of scrape activity', 'time': 'Recommended: 2-4am local time, after any scrape windows complete', 'scope': ['mart_daily_snapshot'], 'reason': 'Trailing 30 days is relative to CURRENT_DATE (date of user view). Without nightly refresh, T30 on a Wednesday would include data from before the last scrape but the window endpoint would be stale. mart_daily_snapshot must be current-dated every night.', 'what_changes': "New row inserted for CURRENT_DATE for every active make/model/state/inventory_type combination. Prior rows are immutable once written — only today's row is added or updated."}
-- scrape_triggered_refresh: {'trigger': 'On completion of scrape ETL pipeline — 1-2x per week', 'sequence': ['1. Scrape completes — new records land in Layer 2 dealer_inventories', '2. Layer 2 → Data Lake dimension sync (gear_brands → dim_manufacturer, boats_models → dim_boat_model, dealers → dim_dealer, etc.)', '3. fact_listing_snapshot rows inserted for new/changed listings', '4. fact_estimated_sale rows inserted for listings inferred as sold (removed after active)', '5. mart_daily_snapshot rebuilt for the scrape date (backfill if scrape covers multiple days)', '6. Monthly marts recalculated: mart_pricing_trends, mart_regional_summary, mart_inventory_summary (monthly grain), mart_time_on_market, mart_estimated_velocity', '7. refresh_log row inserted recording scrape date, rows affected, mart refresh timestamps'], 'scope': ['fact_listing_snapshot', 'fact_estimated_sale', 'mart_daily_snapshot', 'mart_inventory_summary', 'mart_pricing_trends', 'mart_regional_summary', 'mart_time_on_market', 'mart_estimated_velocity']}
-- monthly_mart_refresh_note: Monthly marts (mart_pricing_trends, mart_regional_summary, etc.) refresh on scrape-triggered schedule only — not nightly. Their inputs are completed calendar months which do not change between scrapes. The current in-progress month row is updated on each scrape-triggered refresh and flagged is_partial_month = true.
-- staleness_expectations: {'mart_daily_snapshot_stock_metrics': 'Max 24 hours stale (nightly refresh)', 'mart_daily_snapshot_flow_metrics': 'Max 3-7 days stale between scrapes — flow metrics (new_listings, removed_listings) only change when new scrape data arrives', 'monthly_marts': 'Max 3-7 days stale between scrapes', 'dimensions': 'Max 3-7 days stale between scrapes'}

-- ================================================================================
-- END OF FILE
-- ================================================================================
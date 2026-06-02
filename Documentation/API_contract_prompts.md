Title: API Contract
# Goal
-- Specify an API contract for an API between the analytics DB and the analytics front-end
-- The analytics DB is specified in the most recent ERD json file
-- DB will run on a Postgres instance
-- Payloads returned by the API handlers will be in Prisma ORM objects

# Data 
-- A data mark object will be created out of the database, and look like this:
date_key        | 20260514
manufacturer_key| 42          (Malibu)
boat_model_key  | 187         (23 LSV)
state           | FL
inventory_type  | New
---
active_listings          | 22
new_listings_today       | 3
removed_listings_today   | 2
avg_list_price           | 162400
median_list_price        | 158000
avg_dom                  | 14
dom_bucket_0_7           | 8
dom_bucket_8_15          | 7
dom_bucket_16_30         | 5
dom_bucket_31_60         | 2
dom_bucket_60_plus       | 0

-- Based on the time frame parameter passed into the API call, the API handler will query the database using the time parameter values to acquire a set of the above records.  Then, the API handler will use a  query parameter registry approach, with a config file for registration of new query parameters.

-- Use these recommendations with this method:
Yes, use it — but with these guardrails:
* Config entries define SQL template fragments with named bind parameters only — no value interpolation ever
* A startup validator parses every config entry and checks it against the known schema
* The dispatch layer is thin and generic — its only job is: look up the config entry, bind the value, append to WHERE
* Parameter interactions that require JOIN changes or conditional logic go in code, not config — don't stretch the pattern beyond independent filter conditions
* Every config entry has a corresponding integration test

-- Just as the input registry maps a parameter name to a WHERE clause fragment, an output registry maps a field name to a transformation rule. Each registry entry describes:

* Source columns — which raw DB columns feed this output field
* Operation — sum, average, percent-of, ratio, etc.
* Dependencies — if a % calculation needs another computed field to already exist, the registry can declare that ordering

Split the output registry into two tiers:
* Tier 1 — Aggregations (fully config-driven): sum, avg, count, min, max applied to raw columns. These are mechanical and safe to put entirely in config.
* Tier 2 — Derived metrics (config-declared, code-assisted): percent calculations, ratios, market comparisons. Config declares the formula structure and input references; a small library of operation functions in code executes them. Adding a new derived metric means a new config entry pointing to an existing operation type — no new code unless it's a genuinely new operation type.

-- Provide a set of API signatures based on this information, to serve  all the metrics required by the enclosed PDF files representing the analytics UX.  Provide the API calls in a file in the best format for such contract documentation.  Document, all known parameters, types, required or optiona, return value for the API call, payload syntax and semantics for each call.

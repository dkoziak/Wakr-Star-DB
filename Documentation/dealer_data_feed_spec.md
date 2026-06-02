# Wakr Dealer Data Feed — Field Specification

**Document:** Dealer Edge Database Data Requirements  
**Version:** 1.0 · Based on Wakr Data Lake v1.4.0  
**Audience:** Authorized Wakr dealer partners submitting inventory and profile data  
**Date:** 2026-03-07

---

## Overview

As a Wakr dealer partner, you will submit data to a **Dealer Edge Database** — a lightweight local database that syncs with the Wakr Data Lake on a scheduled basis. You are responsible for keeping three categories of data current:

1. **Your Dealership Profile** — submitted once, updated when your details change
2. **Your Active Inventory Listings** — submitted daily (or on every listing change)
3. **Listing Feature Details** — optional but recommended; submitted alongside each listing

Wakr will handle all calculations (days on market, pricing trends, performance scores) from your raw data. You do **not** need to compute any analytics — just provide the source data accurately and on time.

---

## Section 1 — Dealership Profile

*Submit once during onboarding. Resubmit any time your details change.*

| Field | What It Is | Format | Required? | Example |
|---|---|---|---|---|
| **Dealer ID (Your System)** | Your internal dealer/store ID from your own DMS or POS system | Text (up to 100 characters) | Recommended | `DLR-TX-00412` |
| **Dealership Name** | Official legal business name of this location | Text (up to 200 characters) | ✅ Yes | `Lake Austin Marine` |
| **Street Address** | Physical address of this dealership location | Text (up to 300 characters) | ✅ Yes | `4821 Lake Shore Blvd` |
| **City** | City of this location | Text (up to 100 characters) | ✅ Yes | `Austin` |
| **State** | Two-letter US state abbreviation | 2-letter text | ✅ Yes | `TX` |
| **ZIP Code** | Five-digit ZIP code | Text (up to 10 characters) | ✅ Yes | `78732` |
| **Is Authorized Dealer** | Are you an officially authorized dealer for your brands? | Yes / No | ✅ Yes | `Yes` |
| **Wakr Partner Enrolled** | Are you enrolled in Wakr's Dealer Listings product? | Yes / No | ✅ Yes | `Yes` |
| **Network/Group Name** | If you are part of a dealer group or franchise chain, the group name | Text (up to 200 characters) | If applicable | `Hill Country Marine Group` |
| **Wakr Join Date** | The date you joined the Wakr dealer network | Date (YYYY-MM-DD) | ✅ Yes | `2026-01-15` |

### Brand Authorizations

*For each manufacturer brand you are authorized to sell, provide one row per brand.*

| Field | What It Is | Format | Required? | Example |
|---|---|---|---|---|
| **Brand Name** | Name of the manufacturer/brand | Text (up to 100 characters) | ✅ Yes | `Malibu` |
| **Is Primary Brand** | Is this your dominant/primary brand? (only one brand can be primary) | Yes / No | ✅ Yes | `Yes` |
| **Is Authorized** | Manufacturer-confirmed authorized dealer status | Yes / No | ✅ Yes | `Yes` |
| **Authorization Level** | Level of authorization from the manufacturer | One of: `Full` / `Limited` / `Service-Only` | ✅ Yes | `Full` |
| **Authorization Start Date** | Date your authorization for this brand began | Date (YYYY-MM-DD) | ✅ Yes | `2024-03-01` |
| **Authorization Expiry Date** | Date your authorization expires, if known | Date (YYYY-MM-DD) | If applicable | `2027-03-01` |

---

## Section 2 — Inventory Listings

*Submit daily, or immediately whenever a listing is added, updated, or removed.*

> **One row per boat listing.** If a listing changes (price drop, status change), resubmit the full row with the updated values. Do not delete old rows — Wakr tracks history.

### 2A — Boat Identification

| Field | What It Is | Format | Required? | Example |
|---|---|---|---|---|
| **Listing ID** | Your unique identifier for this listing in your own system | Text (up to 200 characters) | ✅ Yes | `INV-2025-00891` |
| **VIN** | Hull Identification Number (HIN), if the boat has one | Text (up to 50 characters) | If available | `MBU12345A626` |
| **Make** | Manufacturer brand name (must match your authorized brands) | Text (up to 100 characters) | ✅ Yes | `Malibu` |
| **Model** | Specific model name | Text (up to 200 characters) | ✅ Yes | `Wakesetter 24 MXZ` |
| **Model Year** | Four-digit model year | Whole number (4 digits) | ✅ Yes | `2025` |
| **New or Used** | Is this a new (never titled) or used boat? | One of: `New` / `Used` | ✅ Yes | `New` |
| **Manufacture Date** | Date the boat was built by the manufacturer, if known | Date (YYYY-MM-DD) | If available | `2024-08-12` |

### 2B — Boat Condition & Specs

*For used boats, all fields below are strongly encouraged. For new boats, provide what you know.*

| Field | What It Is | Format | Required? | Example |
|---|---|---|---|---|
| **Engine Hours** | Current engine hour reading on the meter | Whole number | For used boats | `312` |
| **Condition** | Overall physical condition of the boat | One of: `Excellent` / `Good` / `Fair` | For used boats | `Excellent` |
| **Color** | Primary exterior color | Text (up to 100 characters) | Recommended | `Midnight Black / Silver` |
| **Actual Engine HP** | True horsepower of the engine on this specific boat — only if different from the manufacturer's standard HP for this model/year | Whole number | If upgraded/different | `450` |
| **Has Tower** | Does this boat physically have a wakeboard/surf tower? | Yes / No | Recommended | `Yes` |
| **Actual Ballast (lbs)** | Total ballast capacity on this specific boat — only if different from factory standard | Whole number (pounds) | If modified | `3,200` |
| **Condition Notes** | Free-text description of any notable condition details, wear, or included extras | Text (up to 500 characters) | Optional | `Minor gelcoat scuff on port bow. Includes custom trailer.` |

### 2C — Listing & Pricing

| Field | What It Is | Format | Required? | Example |
|---|---|---|---|---|
| **Current Asking Price** | The price currently advertised for this boat | Decimal number (dollars, up to 2 decimal places) | ✅ Yes | `89,500.00` |
| **Original List Price** | The price when the listing was first posted — do not change this once set | Decimal number (dollars, up to 2 decimal places) | ✅ Yes | `94,000.00` |
| **Listing Status** | Current status of this listing | One of: `Active` / `Price Reduced` / `Removed` | ✅ Yes | `Price Reduced` |
| **Listing URL** | Web link to this listing on your website or listing platform | Web address (up to 500 characters) | ✅ Yes | `https://lakeaustinmarine.com/inv/INV-2025-00891` |
| **Date First Listed** | The date you first posted this boat for sale | Date (YYYY-MM-DD) | ✅ Yes | `2026-01-10` |
| **Date Removed** | The date the listing was taken down (sold, traded, or withdrawn) — leave blank if still active | Date (YYYY-MM-DD) | When removed | `2026-02-28` |

---

## Section 3 — Listing Features (Optional but Strongly Recommended)

*For each notable feature on a listing, submit one row. Multiple features per listing are expected.*

This data powers Wakr's **comparable listing matching** and **Trade-In & Valuation** tools. The more detail you provide, the more accurate Wakr's valuations will be for your inventory.

| Field | What It Is | Format | Required? | Example |
|---|---|---|---|---|
| **Listing ID** | Links this feature to a specific listing (must match a Listing ID from Section 2) | Text (must match your Section 2 Listing ID) | ✅ Yes | `INV-2025-00891` |
| **Feature Category** | The type of feature being described | One of: `tower` / `ballast` / `electronics` / `upholstery` / `engine_upgrade` / `trailer` / `other` | ✅ Yes | `electronics` |
| **Feature Value** | The specific detail about that feature | Text (up to 200 characters) | ✅ Yes | `Wet Sounds 8-speaker system with sub` |

### Common Feature Examples

| Category | Example Feature Values |
|---|---|
| `tower` | `Aerial HELIX Tower`, `Lund folding tower`, `No tower` |
| `ballast` | `Surf Gate Pro system`, `3,200 lb integrated ballast`, `Plug-and-play sacs` |
| `electronics` | `Garmin Echo chartplotter`, `Wet Sounds 6-speaker stereo`, `360° cameras` |
| `upholstery` | `Ultraleather premium seating`, `Yacht flooring`, `Boarding ladder` |
| `engine_upgrade` | `Indmar 6.2L Raptor 500 HP`, `Twin Ilmor upgrade` |
| `trailer` | `Venture galvanized double-axle trailer included` |

---

## Section 4 — What Wakr Calculates For You

You do **not** need to provide the following — Wakr computes these automatically from your submitted data:

| Calculated Field | How Wakr Derives It |
|---|---|
| Days on Market | Count of days from **Date First Listed** to today (or Date Removed) |
| Price Change Amount | Day-over-day difference in **Current Asking Price** |
| Listing Is New (first day) | Detected when Wakr sees a **Listing ID** for the first time |
| Sell-Through Rate | Units removed (sold) ÷ active inventory |
| Days Supply | Active listings ÷ (units sold per day) |
| Discount Pressure | (Original List Price − Current Price) ÷ Original List Price |
| DOM Status | Speed classification: Fast / Healthy / Slow / Very Slow |
| Aging Risk Level | Elevated / Moderate / Low — based on days on market |
| Demand-Supply Ratio | Boats sold ÷ active listings for your area |
| Performance vs. Market | Your metrics benchmarked against comparable dealers in your region |

---

## Submission Notes

### Data Formats Summary

| Format Label | What It Means | Examples |
|---|---|---|
| **Text** | Plain letters, numbers, spaces, standard punctuation | `Malibu`, `Lake Austin Marine` |
| **Date** | Calendar date in YYYY-MM-DD format | `2026-01-15`, `2025-08-31` |
| **Whole Number** | Integer, no decimals | `312`, `3200`, `2025` |
| **Decimal Number** | Up to 2 decimal places | `89,500.00`, `1.78` |
| **Yes / No** | Boolean flag | `Yes`, `No` |
| **Web Address** | Full URL starting with `http://` or `https://` | `https://yoursite.com/listing/123` |
| **Constrained Text** | Must be one of the listed options exactly as spelled | `Active`, `Fair`, `Full` |

### Submission Frequency

| Data Category | Recommended Frequency |
|---|---|
| Dealership Profile | Once at onboarding; resend when anything changes |
| Brand Authorizations | Once at onboarding; resend when anything changes |
| Inventory Listings | **Daily** minimum; real-time preferred for status/price changes |
| Listing Features | With each new listing; resend if features are added/changed |

### Important Rules

1. **Never reuse a Listing ID** for a different boat. Each physical boat listing should have its own persistent ID from the moment it's listed until it's sold.
2. **Always submit Original List Price once and never change it.** Wakr uses this to measure price reductions over time.
3. **Submit a Listing Status of `Removed` when a boat sells** rather than simply deleting the row. Wakr infers sales from removed listings — deletions without a `Removed` status break velocity calculations.
4. **VIN is optional** but strongly preferred for new boats. Wakr uses VIN to accurately deduplicate boats that appear across multiple listing sources.
5. **Do not submit PII** (buyer names, customer contact details, financing information, etc.). The edge database is for inventory and dealer profile data only.

---

## Questions?

Contact your Wakr partner integration team for technical onboarding support, field mapping assistance, or to discuss your DMS / data export format.

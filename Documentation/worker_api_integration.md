# Wakr Analytics API — Worker Integration Guide

## Overview

The Wakr Analytics API uses a static API key for machine-to-machine authentication.
The Cloudflare Worker must include the key on every request via a custom header.

## Authentication

Add the following header to every request to the API:

```
X-API-Key: <WAKR_ANALYTICS_API_KEY>
```

The key value must be stored as a Worker secret (never hardcoded).

## Setup

### 1. Store the secret in the Worker

```bash
wrangler secret put WAKR_ANALYTICS_API_KEY
# paste the key value when prompted
```

### 2. Add the header in fetch calls

```js
const response = await fetch(`${env.WAKR_API_BASE_URL}/api/v1/inventory/summary?time_range=trailing_30`, {
  headers: {
    "X-API-Key": env.WAKR_ANALYTICS_API_KEY,
    "Content-Type": "application/json",
  },
});
```

### 3. Set the base URL secret

```bash
wrangler secret put WAKR_API_BASE_URL
# value: https://analytics-api-test.wakr.co
```

## API Base URL

```
https://analytics-api-test.wakr.co
```

All endpoints are under `/api/v1/`. See the full contract at `wakr_api_contract.md`.

## Error responses

| Status | Code | Meaning |
|--------|------|---------|
| 401 | `UNAUTHORIZED` | Missing or invalid API key |
| 400 | `MISSING_PARAM` / `INVALID_PARAM` | Bad query parameters |
| 422 | `INSUFFICIENT_DATA` | Not enough data for the requested range |
| 500 | `INTERNAL` | Server error |

## Required query parameters

Every endpoint requires `time_range`. Valid values:

```
trailing_7 | trailing_30 | trailing_90 | last_month | last_quarter | ytd | l12m
```

## Notes

- The API key must be rotated by updating `ANALYTICS_API_KEY` in the server's `.env` and redeploying the API service, then updating the Worker secret.
- Do not expose the API key in client-side code or logs.

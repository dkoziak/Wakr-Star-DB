# IMPLEMENTATION_AWS.md
# Wakr Backend — AWS Test Environment Deployment Plan

**Prepared:** June 2026  
**Environment:** Test / Pre-production  
**Strategy:** Maximise AWS Free Tier; use smallest paid instances where free tier is unavailable.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Cost Estimate](#2-cost-estimate)
3. [Prerequisites](#3-prerequisites)
4. [Phase 1 — Network & IAM Foundation](#4-phase-1--network--iam-foundation)
5. [Phase 2 — RDS PostgreSQL (Free Tier)](#5-phase-2--rds-postgresql-free-tier)
6. [Phase 3 — Secrets (SSM Parameter Store)](#6-phase-3--secrets-ssm-parameter-store)
7. [Phase 4 — EC2: `wakr-api` (Star-DB FastAPI — Free Tier t2.micro)](#7-phase-4--ec2-wakr-api-star-db-fastapi--free-tier-t2micro)
8. [Phase 5 — EC2: `wakr-cms` (Directus + Meilisearch — t3.small)](#8-phase-5--ec2-wakr-cms-directus--meilisearch--t3small)
9. [Phase 6 — EC2: `wakr-etl` (Dagster ETL — t3.small)](#9-phase-6--ec2-wakr-etl-dagster-etl--t3small)
10. [Phase 7 — EC2: `wakr-scrapper` (Playwright Scraper — t3.medium)](#10-phase-7--ec2-wakr-scrapper-playwright-scraper--t3medium)
11. [Phase 8 — Daemon Configuration](#11-phase-8--daemon-configuration)
12. [Phase 9 — Directus Bootstrap & Extension Build](#12-phase-9--directus-bootstrap--extension-build)
13. [Phase 10 — Database Schema Initialisation](#13-phase-10--database-schema-initialisation)
14. [Phase 11 — Smoke Tests & Verification](#14-phase-11--smoke-tests--verification)
15. [Appendix A — Environment Variable Reference](#appendix-a--environment-variable-reference)
16. [Appendix B — Security & Rotation Notes](#appendix-b--security--rotation-notes)
17. [Appendix C — Instance Consolidation Option](#appendix-c--instance-consolidation-option)

---

## 1. Architecture Overview

> **Production note:** In the current deployment, Directus is **cloud-hosted** at `api.gowakr.com` — the `wakr-cms` EC2 instance is not provisioned. The scraper and ETL connect directly to the cloud Directus. If you are deploying a self-hosted Directus, follow Phase 5 and Phase 9; otherwise skip them.

### Current Production IPs

| Server | IP | Runs |
|--------|----|----|
| `wakr-api` | 18.194.202.20 | Star-DB FastAPI (port 8000) |
| `wakr-etl` | 3.120.235.122 | Dagster daemon + webserver (port 3000) |
| `wakr-scrapper` | 63.176.137.216 | Playwright scraper (Docker, daily timer 06:00 UTC) |

### Repos → Services Mapping

| Repo | Service | Tech | Port |
|------|---------|------|------|
| `wakeco-backend` | Directus CMS (self-hosted option) | Node.js 18, Directus 10 | 8055 |
| `wakr-directus-extensions` | Directus custom endpoints & hooks | Node.js (built into Directus) | — |
| `Wakr-Star-DB` | Market Intelligence API | Python 3.11, FastAPI / uvicorn | 8000 |
| `wakeco-backend/cms_etl` | ETL pipeline (Directus → Star-DB) | Python 3.12, Dagster 1.7 | 3000 (UI) |
| `wakr-scrapper` | Dealer website scraper | Python 3.11, Playwright / Chromium | — (batch) |

### Data Flow

```
Dealer Websites
      │
      ▼  (daily systemd timer)
┌─────────────────┐
│  wakr-scrapper  │  EC2 t3.medium
│  (Playwright)   │
└────────┬────────┘
         │ Directus REST API
         ▼
┌─────────────────┐       ┌──────────────────────┐
│  wakeco-backend │       │      Meilisearch       │
│  (Directus CMS) │──────►│  (boats-for-sale idx) │
│  EC2 t3.small   │       │  Docker on same host  │
└────────┬────────┘       └──────────────────────┘
         │ Directus REST API
         │ (daily 02:00 UTC — Dagster schedule)
         ▼
┌─────────────────┐
│   wakr-etl      │  EC2 t3.small
│   (Dagster)     │
└────────┬────────┘
         │ psycopg2
         ▼
┌──────────────────────────────────────────┐
│  RDS PostgreSQL db.t3.micro (FREE yr 1)  │
│  ├── directus_db   (Directus CMS data)   │
│  ├── wakr_stardb   (analytics warehouse) │
│  └── dagster_cms   (Dagster state)       │
└──────────────────────────────────────────┘
         ▲
         │ asyncpg (SQLAlchemy)
┌─────────────────┐
│   wakr-api      │  EC2 t2.micro (FREE yr 1)
│  (FastAPI API)  │
└─────────────────┘
         ▲
         │ OAuth2 JWT (Auth0)
  API Consumers
```

### EC2 Instance Summary

| Server Name | Instance | Free Tier? | Est. Cost | Runs |
|-------------|----------|-----------|-----------|------|
| `wakr-api` | t2.micro | ✅ Free yr 1 | $0 → ~$8/mo | Star-DB FastAPI |
| `wakr-cms` | t3.small | ❌ | ~$17/mo | Directus + Meilisearch |
| `wakr-etl` | t3.small | ❌ | ~$17/mo | Dagster daemon + webserver |
| `wakr-scrapper` | t3.medium | ❌ | ~$33/mo | Playwright scraper (Docker, daily timer) |
| RDS PostgreSQL | db.t3.micro | ✅ Free yr 1 | $0 → ~$15/mo | 3 databases |

**Total estimated cost:**
- Year 1: ~$67/month
- Year 2+: ~$90/month (after free tier expiry)

> See [Appendix C](#appendix-c--instance-consolidation-option) for a 2-server consolidated option at ~$50/month.

---

## 2. Cost Estimate

### Always Free (AWS Free Tier — no expiry)

| Service | Free Allowance | Usage |
|---------|---------------|-------|
| VPC | Always free | Networking |
| Security Groups | Always free | Firewall rules |
| IAM | Always free | Roles & policies |
| SSM Parameter Store (Standard) | Always free | All secrets/env vars |
| CloudWatch Logs | 5 GB ingestion/month | Service logs |
| CloudWatch Metrics | 10 custom metrics | Health monitoring |
| S3 | 5 GB storage, 20k GET, 2k PUT/month | Scraper checkpoints |
| ECR | 500 MB/month | Docker images |

### Free for 12 Months (from AWS account creation)

| Service | Instance / Tier | Monthly Cost |
|---------|----------------|-------------|
| EC2 `wakr-api` | t2.micro, 750 hrs/mo | **$0** (yr 1) |
| RDS PostgreSQL | db.t3.micro, 20 GB SSD | **$0** (yr 1) |

### Always Paid (smallest available)

| Service | Instance | On-Demand Price |
|---------|----------|----------------|
| EC2 `wakr-cms` | t3.small (2 vCPU, 2 GB) | ~$0.023/hr ≈ **$17/mo** |
| EC2 `wakr-etl` | t3.small (2 vCPU, 2 GB) | ~$0.023/hr ≈ **$17/mo** |
| EC2 `wakr-scrapper` | t3.medium (2 vCPU, 4 GB) | ~$0.046/hr ≈ **$33/mo** |

> **Cost tip:** The scraper is a batch job, not a persistent service. Stop/start the `wakr-scrapper` instance via a scheduled EventBridge rule (e.g., start at 05:50 UTC, stop at 10:00 UTC) to cut its cost by ~60%, saving ~$20/mo.

---

## 3. Prerequisites

### 3.1 AWS Account & CLI

```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# Configure with IAM user credentials (AdministratorAccess for setup)
aws configure
# Enter: Access Key ID, Secret Access Key, Region (e.g. us-east-1), output (json)
```

Choose a single AWS region and use it throughout. All examples below use `us-east-1`.

### 3.2 EC2 Key Pair

```bash
aws ec2 create-key-pair \
  --key-name wakr-test \
  --query 'KeyMaterial' \
  --output text > ~/.ssh/wakr-test.pem

chmod 400 ~/.ssh/wakr-test.pem
```

### 3.3 External Service Accounts Required Before Deployment

These are not AWS resources but are required at environment-variable configuration time:

| Service | Purpose | Where Used |
|---------|---------|-----------|
| **Auth0** | JWT issuer for Star-DB API | `wakr-api` |
| **OpenAI API** | LLM-based selector discovery | `wakr-scrapper` |
| **Google Maps API** | Dealer geocoding | `wakr-scrapper` |

Obtain API keys for each before Phase 3.

> **Security note from TECHNICAL_ASSESSMENT.md:** API keys and Directus credentials were previously hard-coded and are in git history. Rotate all credentials before deployment — Directus admin password, OpenAI key, and Google Maps key.

---

## 4. Phase 1 — Network & IAM Foundation

### 4.1 Use the Default VPC

For a test environment the default VPC is sufficient. Confirm it exists:

```bash
aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text
# Save this as VPC_ID
```

### 4.2 Security Groups

Create one security group per server. Replace `YOUR_ADMIN_IP/32` with your actual public IP (`curl ifconfig.me`).

#### SG: `wakr-rds-sg` (RDS)

```bash
RDS_SG=$(aws ec2 create-security-group \
  --group-name wakr-rds-sg \
  --description "Wakr RDS PostgreSQL" \
  --query 'GroupId' --output text)

# PostgreSQL access from EC2 servers only — rules added after creating EC2 SGs
echo "RDS_SG=$RDS_SG"
```

#### SG: `wakr-api-sg` (Star-DB FastAPI, t2.micro)

```bash
API_SG=$(aws ec2 create-security-group \
  --group-name wakr-api-sg \
  --description "Wakr Star-DB API" \
  --query 'GroupId' --output text)

# SSH (admin only)
aws ec2 authorize-security-group-ingress --group-id $API_SG \
  --protocol tcp --port 22 --cidr YOUR_ADMIN_IP/32

# FastAPI HTTP (internet — lock down to known IPs for test)
aws ec2 authorize-security-group-ingress --group-id $API_SG \
  --protocol tcp --port 8000 --cidr 0.0.0.0/0
```

#### SG: `wakr-cms-sg` (Directus + Meilisearch)

```bash
CMS_SG=$(aws ec2 create-security-group \
  --group-name wakr-cms-sg \
  --description "Wakr Directus CMS" \
  --query 'GroupId' --output text)

# SSH
aws ec2 authorize-security-group-ingress --group-id $CMS_SG \
  --protocol tcp --port 22 --cidr YOUR_ADMIN_IP/32

# Directus (internet — restrict to known IPs for test)
aws ec2 authorize-security-group-ingress --group-id $CMS_SG \
  --protocol tcp --port 8055 --cidr 0.0.0.0/0

# Meilisearch (internal only — ETL and scrapper reach it via private IP)
# No public rule. Access controlled at application level via private IP.
```

#### SG: `wakr-etl-sg` (Dagster)

```bash
ETL_SG=$(aws ec2 create-security-group \
  --group-name wakr-etl-sg \
  --description "Wakr Dagster ETL" \
  --query 'GroupId' --output text)

# SSH
aws ec2 authorize-security-group-ingress --group-id $ETL_SG \
  --protocol tcp --port 22 --cidr YOUR_ADMIN_IP/32

# Dagster webserver UI (admin only)
aws ec2 authorize-security-group-ingress --group-id $ETL_SG \
  --protocol tcp --port 3000 --cidr YOUR_ADMIN_IP/32
```

#### SG: `wakr-scrapper-sg`

```bash
SCRAPPER_SG=$(aws ec2 create-security-group \
  --group-name wakr-scrapper-sg \
  --description "Wakr Playwright Scraper" \
  --query 'GroupId' --output text)

# SSH only
aws ec2 authorize-security-group-ingress --group-id $SCRAPPER_SG \
  --protocol tcp --port 22 --cidr YOUR_ADMIN_IP/32
```

#### RDS ingress — allow all app servers

```bash
# Allow all EC2 servers to reach PostgreSQL on RDS
for SG in $API_SG $CMS_SG $ETL_SG $SCRAPPER_SG; do
  aws ec2 authorize-security-group-ingress --group-id $RDS_SG \
    --protocol tcp --port 5432 --source-group $SG
done
```

### 4.3 IAM Role for EC2 (SSM read access)

All EC2 instances will read secrets from SSM Parameter Store at startup.

```bash
# Create the trust policy
cat > /tmp/ec2-trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name wakr-ec2-role \
  --assume-role-policy-document file:///tmp/ec2-trust.json

# Attach SSM read policy
aws iam attach-role-policy \
  --role-name wakr-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess

# Attach CloudWatch agent policy for logs
aws iam attach-role-policy \
  --role-name wakr-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

# Create instance profile
aws iam create-instance-profile --instance-profile-name wakr-ec2-profile
aws iam add-role-to-instance-profile \
  --instance-profile-name wakr-ec2-profile \
  --role-name wakr-ec2-role
```

---

## 5. Phase 2 — RDS PostgreSQL (Free Tier)

### 5.1 Create the RDS Subnet Group

```bash
# Get default subnet IDs (use at least 2 AZs)
SUBNET_IDS=$(aws ec2 describe-subnets \
  --filters "Name=defaultForAz,Values=true" \
  --query 'Subnets[*].SubnetId' --output text | tr '\t' ',')

aws rds create-db-subnet-group \
  --db-subnet-group-name wakr-db-subnets \
  --db-subnet-group-description "Wakr RDS subnets" \
  --subnet-ids $(echo $SUBNET_IDS | tr ',' ' ')
```

### 5.2 Create the RDS Instance

```bash
aws rds create-db-instance \
  --db-instance-identifier wakr-postgres \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 16.3 \
  --master-username wakr_admin \
  --master-user-password "CHANGE_ME_STRONG_PASSWORD" \
  --allocated-storage 20 \
  --storage-type gp2 \
  --db-subnet-group-name wakr-db-subnets \
  --vpc-security-group-ids $RDS_SG \
  --no-publicly-accessible \
  --backup-retention-period 1 \
  --no-multi-az \
  --db-name directus_db \
  --tags Key=Project,Value=wakr Key=Env,Value=test
```

> This creates the RDS instance with `directus_db` as the default database. The `wakr_stardb` and `dagster_cms` databases are created separately in Phase 10.

Wait for the instance to be available (~5-10 minutes):

```bash
aws rds wait db-instance-available \
  --db-instance-identifier wakr-postgres

# Get the endpoint hostname (save this — needed for all .env files)
RDS_HOST=$(aws rds describe-db-instances \
  --db-instance-identifier wakr-postgres \
  --query 'DBInstances[0].Endpoint.Address' --output text)

echo "RDS_HOST=$RDS_HOST"
```

---

## 6. Phase 3 — Secrets (SSM Parameter Store)

All sensitive configuration is stored in SSM Parameter Store (Standard tier — **free**). EC2 instances read these at startup via the `wakr-ec2-role` IAM role. SecureString parameters use the default AWS-managed KMS key (no additional cost).

### 6.1 Store All Parameters

Run the following, replacing placeholder values with your real credentials:

```bash
# Helper function
put_param() {
  aws ssm put-parameter --name "$1" --value "$2" \
    --type SecureString --overwrite
}

# ── RDS ──────────────────────────────────────────────────────────
put_param "/wakr/test/DB_HOST"           "$RDS_HOST"
put_param "/wakr/test/DB_MASTER_USER"    "wakr_admin"
put_param "/wakr/test/DB_MASTER_PASS"    "CHANGE_ME_STRONG_PASSWORD"

# ── Directus ─────────────────────────────────────────────────────
put_param "/wakr/test/DIRECTUS_DB_USER"      "directus"
put_param "/wakr/test/DIRECTUS_DB_PASS"      "CHANGE_ME_DIRECTUS_PASS"
put_param "/wakr/test/DIRECTUS_ADMIN_EMAIL"  "admin@wakr.co"
put_param "/wakr/test/DIRECTUS_ADMIN_PASS"   "CHANGE_ME_ADMIN_PASS"
put_param "/wakr/test/DIRECTUS_SECRET"       "CHANGE_ME_RANDOM_32_CHAR_HEX"
put_param "/wakr/test/DIRECTUS_PUBLIC_URL"   "http://<wakr-cms-public-ip>:8055"

# ── Meilisearch ───────────────────────────────────────────────────
put_param "/wakr/test/MEILI_MASTER_KEY"      "CHANGE_ME_MEILI_MASTER_KEY"

# ── Star-DB API ───────────────────────────────────────────────────
put_param "/wakr/test/STARDB_DB_USER"        "stardb"
put_param "/wakr/test/STARDB_DB_PASS"        "CHANGE_ME_STARDB_PASS"
put_param "/wakr/test/TOKEN_ISSUER"          "https://your-tenant.us.auth0.com/"
put_param "/wakr/test/TOKEN_AUDIENCE"        "https://api.wakr.co"
put_param "/wakr/test/JWT_PUBLIC_KEY"        "-----BEGIN PUBLIC KEY-----\n..."

# ── Dagster / cms_etl ─────────────────────────────────────────────
put_param "/wakr/test/DAGSTER_DB_USER"       "dagster"
put_param "/wakr/test/DAGSTER_DB_PASS"       "CHANGE_ME_DAGSTER_PASS"
put_param "/wakr/test/DIRECTUS_ETL_EMAIL"    "etl-service@wakr.co"
put_param "/wakr/test/DIRECTUS_ETL_PASS"     "CHANGE_ME_ETL_PASS"

# ── Scrapper ──────────────────────────────────────────────────────
put_param "/wakr/test/OPENAI_API_KEY"        "sk-..."
put_param "/wakr/test/GOOGLE_API_KEY"        "AIza..."
put_param "/wakr/test/DIRECTUS_SCRAPPER_EMAIL" "scrapper@wakr.co"
put_param "/wakr/test/DIRECTUS_SCRAPPER_PASS"  "CHANGE_ME_SCRAPPER_PASS"
```

### 6.2 Startup Script Helper (reused by all servers)

Each EC2 instance uses a shared shell function to pull SSM parameters into its local `.env` files. Add this to any instance's user-data or bootstrap script:

```bash
fetch_ssm() {
  # Usage: fetch_ssm /wakr/test/PARAM_NAME
  aws ssm get-parameter \
    --name "$1" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text \
    --region us-east-1
}
```

---

## 7. Phase 4 — EC2: `wakr-api` (Star-DB FastAPI — Free Tier t2.micro)

### 7.1 Launch Instance

```bash
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \   # Amazon Linux 2023 us-east-1 (check latest)
  --instance-type t2.micro \
  --key-name wakr-test \
  --security-group-ids $API_SG \
  --iam-instance-profile Name=wakr-ec2-profile \
  --tag-specifications \
    'ResourceType=instance,Tags=[{Key=Name,Value=wakr-api},{Key=Project,Value=wakr}]' \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]'
```

### 7.2 Server Setup

SSH in, then run:

```bash
# System deps
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip git

# Create service user
sudo useradd --system --no-create-home --shell /usr/sbin/nologin wakr-api

# Deploy application
sudo mkdir -p /opt/wakr/Wakr-Star-DB
cd /opt/wakr/Wakr-Star-DB
sudo git clone https://github.com/YOUR_ORG/Wakr-Star-DB.git .

# Virtual environment
sudo python3.11 -m venv .venv
sudo .venv/bin/pip install -r src/requirements.txt
sudo chown -R wakr-api:wakr-api /opt/wakr/Wakr-Star-DB
```

### 7.3 Build the `.env` File from SSM

```bash
sudo tee /opt/wakr/Wakr-Star-DB/src/.env > /dev/null <<EOF
STARDB_URL=postgresql+asyncpg://$(fetch_ssm /wakr/test/STARDB_DB_USER):$(fetch_ssm /wakr/test/STARDB_DB_PASS)@$(fetch_ssm /wakr/test/DB_HOST):5432/wakr_stardb
DEBUG=false
TOKEN_ISSUER=$(fetch_ssm /wakr/test/TOKEN_ISSUER)
TOKEN_AUDIENCE=$(fetch_ssm /wakr/test/TOKEN_AUDIENCE)
JWT_PUBLIC_KEY=$(fetch_ssm /wakr/test/JWT_PUBLIC_KEY)
EOF

sudo chmod 600 /opt/wakr/Wakr-Star-DB/src/.env
sudo chown wakr-api:wakr-api /opt/wakr/Wakr-Star-DB/src/.env
```

### 7.4 systemd Service

```bash
sudo tee /etc/systemd/system/wakr-stardb-api.service > /dev/null <<'EOF'
[Unit]
Description=Wakr Star-DB Market Intelligence API
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=wakr-api
Group=wakr-api
WorkingDirectory=/opt/wakr/Wakr-Star-DB/src
ExecStart=/opt/wakr/Wakr-Star-DB/.venv/bin/uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --no-access-log
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=wakr-stardb-api
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now wakr-stardb-api
sudo systemctl status wakr-stardb-api
```

> **Note:** On t2.micro (1 GB RAM), set `--workers 2`. Increase to 4 workers only after schema is confirmed healthy.

---

## 8. Phase 5 — EC2: `wakr-cms` (Directus + Meilisearch — t3.small)

### 8.1 Launch Instance

```bash
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type t3.small \
  --key-name wakr-test \
  --security-group-ids $CMS_SG \
  --iam-instance-profile Name=wakr-ec2-profile \
  --tag-specifications \
    'ResourceType=instance,Tags=[{Key=Name,Value=wakr-cms},{Key=Project,Value=wakr}]' \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]'
```

### 8.2 Server Setup

```bash
# System deps
sudo dnf update -y
sudo dnf install -y nodejs npm git docker

# Node version — Directus requires Node 18
sudo npm install -g n
sudo n 18.17.1
hash -r

# Start Docker (for Meilisearch)
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Deploy Directus application
sudo mkdir -p /opt/wakr/directus
cd /opt/wakr/directus
sudo git clone https://github.com/YOUR_ORG/wakeco-backend.git .
sudo npm ci --omit=dev
sudo useradd --system --no-create-home --shell /usr/sbin/nologin directus
sudo chown -R directus:directus /opt/wakr/directus
```

### 8.3 Build All Directus Extensions

Each extension in `extensions/` needs to be built before Directus can load it. Run the build for each:

```bash
cd /opt/wakr/directus/extensions
for ext_dir in */; do
  if [ -f "$ext_dir/package.json" ]; then
    echo "Building extension: $ext_dir"
    (cd "$ext_dir" && npm install && npm run build 2>/dev/null || true)
  fi
done
```

> This runs `directus-extension build` (via `@directus/extensions-sdk`) in each extension directory, producing the `dist/index.js` that Directus loads. Extensions without a build script are skipped gracefully.

### 8.4 Directus `.env` File

```bash
CMS_HOST=$(fetch_ssm /wakr/test/DB_HOST)
DIR_DB_USER=$(fetch_ssm /wakr/test/DIRECTUS_DB_USER)
DIR_DB_PASS=$(fetch_ssm /wakr/test/DIRECTUS_DB_PASS)
DIR_SECRET=$(fetch_ssm /wakr/test/DIRECTUS_SECRET)
MEILI_KEY=$(fetch_ssm /wakr/test/MEILI_MASTER_KEY)

sudo tee /opt/wakr/directus/.env > /dev/null <<EOF
# Database
DB_CLIENT=pg
DB_HOST=$CMS_HOST
DB_PORT=5432
DB_DATABASE=directus_db
DB_USER=$DIR_DB_USER
DB_PASSWORD=$DIR_DB_PASS

# Security
SECRET=$DIR_SECRET

# Admin account (used only on bootstrap)
ADMIN_EMAIL=$(fetch_ssm /wakr/test/DIRECTUS_ADMIN_EMAIL)
ADMIN_PASSWORD=$(fetch_ssm /wakr/test/DIRECTUS_ADMIN_PASS)

# Public URL
PUBLIC_URL=$(fetch_ssm /wakr/test/DIRECTUS_PUBLIC_URL)

# Extensions
EXTENSIONS_PATH=./extensions
EXTENSIONS_AUTO_RELOAD=false

# Meilisearch (read by sync-meilisearch hook)
MEILISEARCH_HOST=http://localhost:7700
MEILISEARCH_MASTER_KEY=$MEILI_KEY

# Email (liquid templates)
EMAIL_TRANSPORT=sendmail
EMAIL_FROM=noreply@wakr.co

# Storage (local for test env)
STORAGE_LOCATIONS=local
STORAGE_LOCAL_ROOT=./uploads
EOF

sudo chmod 600 /opt/wakr/directus/.env
sudo chown directus:directus /opt/wakr/directus/.env
```

### 8.5 Meilisearch via Docker

```bash
MEILI_KEY=$(fetch_ssm /wakr/test/MEILI_MASTER_KEY)

# Pull and start Meilisearch
sudo docker run -d \
  --name meilisearch \
  --restart unless-stopped \
  -p 127.0.0.1:7700:7700 \
  -e MEILI_MASTER_KEY="$MEILI_KEY" \
  -v /opt/wakr/meilisearch-data:/meili_data \
  getmeili/meilisearch:v1.8
```

> Binding Meilisearch to `127.0.0.1:7700` means it is not exposed on the public network. Only processes on this host (Directus) can reach it.

### 8.6 Directus systemd Service

```bash
sudo tee /etc/systemd/system/directus.service > /dev/null <<'EOF'
[Unit]
Description=Wakr Directus CMS
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=exec
User=directus
Group=directus
WorkingDirectory=/opt/wakr/directus
ExecStart=/usr/local/bin/node node_modules/.bin/directus start
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=directus
Environment=NODE_ENV=production
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable directus
# Do NOT start yet — bootstrap must run first (see Phase 9)
```

---

## 9. Phase 6 — EC2: `wakr-etl` (Dagster ETL — t3.small)

### 9.1 Launch Instance

```bash
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type t3.small \
  --key-name wakr-test \
  --security-group-ids $ETL_SG \
  --iam-instance-profile Name=wakr-ec2-profile \
  --tag-specifications \
    'ResourceType=instance,Tags=[{Key=Name,Value=wakr-etl},{Key=Project,Value=wakr}]' \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]'
```

### 9.2 Server Setup

```bash
# System deps (Python 3.12 required by cms_etl)
sudo dnf update -y
sudo dnf install -y python3.12 python3.12-pip git postgresql15

# Create service user
sudo useradd --system --no-create-home --shell /usr/sbin/nologin dagster

# Deploy cms_etl
sudo mkdir -p /opt/wakr/cms_etl
cd /opt/wakr/cms_etl
sudo git clone https://github.com/YOUR_ORG/wakeco-backend.git /tmp/wakeco
sudo cp -r /tmp/wakeco/cms_etl/* .

# Virtual environment
sudo python3.12 -m venv .venv
sudo .venv/bin/pip install -e "."
sudo chown -R dagster:dagster /opt/wakr/cms_etl
```

### 9.3 Dagster `.env` File

```bash
DB_HOST=$(fetch_ssm /wakr/test/DB_HOST)
STARDB_USER=$(fetch_ssm /wakr/test/STARDB_DB_USER)
STARDB_PASS=$(fetch_ssm /wakr/test/STARDB_DB_PASS)
DAG_USER=$(fetch_ssm /wakr/test/DAGSTER_DB_USER)
DAG_PASS=$(fetch_ssm /wakr/test/DAGSTER_DB_PASS)
ETL_EMAIL=$(fetch_ssm /wakr/test/DIRECTUS_ETL_EMAIL)
ETL_PASS=$(fetch_ssm /wakr/test/DIRECTUS_ETL_PASS)
CMS_HOST=$(fetch_ssm /wakr/test/DIRECTUS_PUBLIC_URL)

sudo tee /opt/wakr/cms_etl/.env > /dev/null <<EOF
# Directus source
DIRECTUS_API_URL=$CMS_HOST/
DIRECTUS_EMAIL=$ETL_EMAIL
DIRECTUS_PASSWORD=$ETL_PASS
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories

# Star DB target
STARDB_URL=postgresql+psycopg2://$STARDB_USER:$STARDB_PASS@$DB_HOST:5432/wakr_stardb

# Dagster state DB
DAGSTER_POSTGRES_URL=postgresql://$DAG_USER:$DAG_PASS@$DB_HOST:5432/dagster_cms

# ETL tuning
BATCH_SIZE=500
CMS_SENSOR_INTERVAL_SECONDS=1800
EOF

sudo chmod 600 /opt/wakr/cms_etl/.env
sudo chown dagster:dagster /opt/wakr/cms_etl/.env

# DAGSTER_HOME must point to the cms_etl directory so dagster.yaml is found
echo 'DAGSTER_HOME=/opt/wakr/cms_etl' | sudo tee -a /opt/wakr/cms_etl/.env
```

---

## 10. Phase 7 — EC2: `wakr-scrapper` (Playwright Scraper — t3.medium)

### 10.1 Launch Instance

```bash
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type t3.medium \
  --key-name wakr-test \
  --security-group-ids $SCRAPPER_SG \
  --iam-instance-profile Name=wakr-ec2-profile \
  --tag-specifications \
    'ResourceType=instance,Tags=[{Key=Name,Value=wakr-scrapper},{Key=Project,Value=wakr}]' \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]'
```

### 10.2 Server Setup

The scraper is deployed as a Docker container. The Playwright base image (`mcr.microsoft.com/playwright/python:v1.52.0-noble`) bundles all Chromium system dependencies, avoiding complex manual installation.

```bash
# Install Docker
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Clone the scrapper repo
sudo mkdir -p /opt/wakr/scrapper
sudo git clone https://github.com/YOUR_ORG/wakr-scrapper.git /opt/wakr/scrapper
cd /opt/wakr/scrapper

# Build the Docker image
sudo docker build -t wakr-scraper:latest .
```

### 10.3 Scrapper `.env` File

```bash
DB_HOST=$(fetch_ssm /wakr/test/DB_HOST)

sudo tee /opt/wakr/scrapper/.env > /dev/null <<EOF
# OpenAI (LLM-based selector discovery)
OPENAI_API_KEY=$(fetch_ssm /wakr/test/OPENAI_API_KEY)

# Google Geocoding
GOOGLE_API_KEY=$(fetch_ssm /wakr/test/GOOGLE_API_KEY)

# Directus
DIRECTUS_API_URL=$(fetch_ssm /wakr/test/DIRECTUS_PUBLIC_URL)/
DIRECTUS_EMAIL=$(fetch_ssm /wakr/test/DIRECTUS_SCRAPPER_EMAIL)
DIRECTUS_PASSWORD=$(fetch_ssm /wakr/test/DIRECTUS_SCRAPPER_PASS)
DIRECTUS_INVENTORY_COLLECTION=dealership_inventories

# PostgreSQL (scrapper uses pg directly for history tables)
PGHOST=$DB_HOST
PGPORT=5432
PGUSER=$(fetch_ssm /wakr/test/DIRECTUS_DB_USER)
PGPASSWORD=$(fetch_ssm /wakr/test/DIRECTUS_DB_PASS)
PGDATABASE=directus_db

# Scraper settings (reduced concurrency for t3.medium)
HEADLESS=true
MAX_CONCURRENT_DEALERS=2
EOF

sudo chmod 600 /opt/wakr/scrapper/.env
```

> `MAX_CONCURRENT_DEALERS=2` keeps memory usage within the t3.medium's 4 GB. Each Chromium instance consumes ~400–800 MB. Increase to 4 only if memory headroom permits.

---

## 11. Phase 8 — Daemon Configuration

This phase establishes the two long-running daemon processes called out in the requirements:

1. **Dagster daemon** — runs the ETL schedule (Directus → Wakr-Star-DB), on `wakr-etl`
2. **Scraper timer** — runs the daily dealer scrape, on `wakr-scrapper`

### 11.1 Dagster Daemon (ETL) — on `wakr-etl`

The Dagster setup requires two systemd units that must both be running for scheduled jobs to execute. The **daemon** handles schedule ticks and sensors; the **webserver** provides the optional UI for manual triggering and run history.

#### `dagster-daemon.service`

This is the critical process. Without it, the `0 2 * * *` (02:00 UTC daily) ETL schedule will not fire.

```bash
sudo tee /etc/systemd/system/dagster-daemon.service > /dev/null <<'EOF'
[Unit]
Description=Dagster Daemon (schedule & sensor runner)
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=dagster
Group=dagster
WorkingDirectory=/opt/wakr/cms_etl
EnvironmentFile=/opt/wakr/cms_etl/.env
ExecStart=/opt/wakr/cms_etl/.venv/bin/dagster-daemon run
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dagster-daemon
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
```

#### `dagster-webserver.service`

Provides the Dagster UI at `http://<wakr-etl-ip>:3000` (admin-only via security group). Useful for inspecting run history and triggering manual backfills.

```bash
sudo tee /etc/systemd/system/dagster-webserver.service > /dev/null <<'EOF'
[Unit]
Description=Dagster Webserver UI
After=network-online.target dagster-daemon.service
Wants=network-online.target

[Service]
Type=exec
User=dagster
Group=dagster
WorkingDirectory=/opt/wakr/cms_etl
EnvironmentFile=/opt/wakr/cms_etl/.env
ExecStart=/opt/wakr/cms_etl/.venv/bin/dagster-webserver \
    -m cms_etl.definitions \
    -h 0.0.0.0 \
    -p 3000
Restart=on-failure
RestartSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dagster-webserver

[Install]
WantedBy=multi-user.target
EOF
```

#### Enable both daemons

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dagster-daemon
sudo systemctl enable --now dagster-webserver

# Verify
sudo systemctl status dagster-daemon
sudo systemctl status dagster-webserver
sudo journalctl -u dagster-daemon -f
```

---

### 11.2 Scraper Daemon (Daily Timer) — on `wakr-scrapper`

The scraper is a batch job, not a long-running server. It is modelled as a **systemd oneshot service** triggered by a **systemd timer** — the recommended pattern over cron for systemd-managed hosts.

The scraper's built-in `--daily` flag automatically partitions the dealer list by weekday (1/7 per day), keeping each run to a manageable duration.

#### `wakr-scrapper.service` (oneshot)

```bash
sudo tee /etc/systemd/system/wakr-scrapper.service > /dev/null <<'EOF'
[Unit]
Description=Wakr Daily Dealer Scrape Run
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
# Runtime can be long — 4-8 hours for a full day's dealer partition
TimeoutStartSec=28800
EnvironmentFile=/opt/wakr/scrapper/.env
ExecStart=/usr/bin/docker run --rm \
    --name wakr-scrape-run \
    --env-file /opt/wakr/scrapper/.env \
    --memory=3.5g \
    --cpus="1.8" \
    wakr-scraper:latest \
    --daily \
    --concurrency 2 \
    --verbose
StandardOutput=journal
StandardError=journal
SyslogIdentifier=wakr-scrapper

[Install]
WantedBy=multi-user.target
EOF
```

#### `wakr-scrapper.timer` (daily at 06:00 UTC)

The timer fires at 06:00 UTC — after the 02:00 UTC Dagster ETL run has completed, keeping the scrape results out of that day's ETL batch and instead feeding the *next* day's ETL.

```bash
sudo tee /etc/systemd/system/wakr-scrapper.timer > /dev/null <<'EOF'
[Unit]
Description=Daily Wakr dealer scrape timer
Requires=wakr-scrapper.service

[Timer]
# Fire daily at 06:00 UTC
OnCalendar=*-*-* 06:00:00 UTC
# Catch up if the machine was offline during the scheduled time
Persistent=true
# Add up to 10 minutes of random delay to reduce thundering herd
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
EOF
```

#### Enable the timer

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wakr-scrapper.timer

# Verify timer is active
systemctl list-timers wakr-scrapper.timer
# Next scheduled run and last run are shown in the output

# Test a manual run (runs immediately, does not affect the timer schedule)
sudo systemctl start wakr-scrapper.service
sudo journalctl -u wakr-scrapper -f
```

---

## 12. Phase 9 — Directus Bootstrap & Extension Build

Bootstrap must run **once** before starting the Directus service. It creates the admin user and applies Directus system migrations against `directus_db`.

### 12.1 Create the Directus DB User (via psql on `wakr-cms`)

First, connect to RDS and create the application-level user:

```bash
# On wakr-cms, using the master RDS credentials
PGPASSWORD=$(fetch_ssm /wakr/test/DB_MASTER_PASS) \
psql -h $RDS_HOST -U wakr_admin -d directus_db <<SQL
CREATE USER directus WITH PASSWORD '$(fetch_ssm /wakr/test/DIRECTUS_DB_PASS)';
GRANT ALL PRIVILEGES ON DATABASE directus_db TO directus;
ALTER DATABASE directus_db OWNER TO directus;
SQL
```

### 12.2 Run Bootstrap

```bash
cd /opt/wakr/directus
sudo -u directus node node_modules/.bin/directus bootstrap
```

Expected output: `Admin user created` and migration confirmations.

### 12.3 Create ETL and Scrapper Service Accounts in Directus

After bootstrap, start Directus temporarily to create the service accounts via the admin API, or do it through the admin UI at `http://<cms-ip>:8055/admin`:

1. Log in as admin
2. Create a **Role** named `etl-service` with full read access to all collections
3. Create a **Role** named `scrapper-service` with full CRUD on `dealership_inventories`, `boat_snapshots`, `boat_listing_changes`
4. Create **Users**: `etl-service@wakr.co` (etl-service role) and `scrapper@wakr.co` (scrapper-service role)
5. Set their passwords to match the values stored in SSM (`/wakr/test/DIRECTUS_ETL_PASS`, `/wakr/test/DIRECTUS_SCRAPPER_PASS`)

### 12.4 Start Directus

```bash
sudo systemctl start directus
sudo systemctl status directus
sudo journalctl -u directus -f
```

---

## 13. Phase 10 — Database Schema Initialisation

### 13.1 Create Application Database Users and Databases

Connect to RDS as `wakr_admin` and provision the remaining databases and users:

```bash
PGPASSWORD=$(fetch_ssm /wakr/test/DB_MASTER_PASS) \
psql -h $RDS_HOST -U wakr_admin -d postgres <<SQL
-- Star DB
CREATE USER stardb WITH PASSWORD '$(fetch_ssm /wakr/test/STARDB_DB_PASS)';
CREATE DATABASE wakr_stardb OWNER stardb;

-- Dagster state DB
CREATE USER dagster WITH PASSWORD '$(fetch_ssm /wakr/test/DAGSTER_DB_PASS)';
CREATE DATABASE dagster_cms OWNER dagster;
SQL
```

### 13.2 Initialise the Star DB Schema

The `init_stardb.sql` script in `Wakr-Star-DB/src/db/` creates all dimension and fact tables using `CREATE TABLE IF NOT EXISTS` — safe to re-run.

```bash
# Run from wakr-api or wakr-etl (both have network access to RDS)
PGPASSWORD=$(fetch_ssm /wakr/test/STARDB_DB_PASS) \
psql -h $RDS_HOST -U stardb -d wakr_stardb \
  -f /opt/wakr/Wakr-Star-DB/src/db/init_stardb.sql

echo "Star DB schema applied."
```

### 13.3 Initialise the Dagster State DB

```bash
# The init_dagster_db.sql creates the dagster_cms database if absent
# (already created above) — this script may be a no-op but run for completeness
PGPASSWORD=$(fetch_ssm /wakr/test/DAGSTER_DB_PASS) \
psql -h $RDS_HOST -U dagster -d dagster_cms \
  -f /opt/wakr/Wakr-Star-DB/src/db/init_dagster_db.sql

echo "Dagster state DB initialised."
```

Dagster will also auto-migrate its own schema tables on first daemon startup.

---

## 14. Phase 11 — Smoke Tests & Verification

### 14.1 Directus CMS (`wakr-cms`)

```bash
# Health check
curl -s http://<wakr-cms-ip>:8055/server/health | jq .status
# Expected: "ok"

# Extensions loaded (should list all custom endpoints)
curl -s http://<wakr-cms-ip>:8055/server/extensions \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.[].name'
```

### 14.2 Meilisearch

```bash
# From wakr-cms (internal only — not reachable from internet)
curl -s http://localhost:7700/health
# Expected: {"status":"available"}
```

### 14.3 Star-DB FastAPI (`wakr-api`)

```bash
# Docs available (DEBUG=false in prod, but /docs still served by FastAPI default)
curl -s http://<wakr-api-ip>:8000/docs -o /dev/null -w "%{http_code}"
# Expected: 200

# Auth check — should return 401 without token
curl -s http://<wakr-api-ip>:8000/api/v1/inventory/summary?time_range=trailing_30 \
  -w "\n%{http_code}"
# Expected: 401 {"error":{"code":"UNAUTHORIZED",...}}
```

### 14.4 Dagster ETL (`wakr-etl`)

```bash
# Webserver UI reachable (from admin IP only)
curl -s http://<wakr-etl-ip>:3000 -o /dev/null -w "%{http_code}"
# Expected: 200

# Daemon is running and has loaded the schedule
sudo journalctl -u dagster-daemon --since "5 minutes ago" | grep -i "schedule\|loaded"
# Expected: lines confirming schedule "directus_to_stardb_job" is loaded

# Trigger a manual ETL run to verify pipeline
source /opt/wakr/cms_etl/.venv/bin/activate
export DAGSTER_HOME=/opt/wakr/cms_etl
dagster job execute -m cms_etl.definitions -j directus_to_stardb_job
```

### 14.5 Scraper (`wakr-scrapper`)

```bash
# Verify the timer is registered
systemctl list-timers wakr-scrapper.timer

# Run a quick test: scrape 2 dealers only (does not affect the daily timer)
sudo docker run --rm \
  --env-file /opt/wakr/scrapper/.env \
  wakr-scraper:latest \
  --limit 2 \
  --concurrency 1 \
  --verbose
```

### 14.6 Full Pipeline Verification

After all services are running and at least one Dagster ETL run has completed:

```bash
# Get an Auth0 token
TOKEN=$(curl -s -X POST https://<your-tenant>.us.auth0.com/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "audience=https://api.wakr.co" | jq -r .access_token)

# Call a Star-DB endpoint
curl -s "http://<wakr-api-ip>:8000/api/v1/inventory/summary?time_range=trailing_30" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

A valid data response (not `NO_DATA` 404) confirms the full pipeline is working end-to-end.

---

## Appendix A — Environment Variable Reference

### `wakr-api` — `Wakr-Star-DB/src/.env`

| Variable | Example | Description |
|----------|---------|-------------|
| `STARDB_URL` | `postgresql+asyncpg://stardb:pass@rds-host:5432/wakr_stardb` | Async PG connection string |
| `DEBUG` | `false` | Set `true` only for local dev to bypass JWT |
| `TOKEN_ISSUER` | `https://wakr.us.auth0.com/` | Auth0 / IdP issuer URL |
| `TOKEN_AUDIENCE` | `https://api.wakr.co` | JWT audience claim |
| `JWT_PUBLIC_KEY` | `-----BEGIN PUBLIC KEY-----...` | RS256 public key PEM |

### `wakr-cms` — `wakeco-backend/.env`

| Variable | Example | Description |
|----------|---------|-------------|
| `DB_CLIENT` | `pg` | Directus DB driver |
| `DB_HOST` | `rds-host` | RDS endpoint |
| `DB_DATABASE` | `directus_db` | Directus database name |
| `DB_USER` / `DB_PASSWORD` | — | Directus DB credentials |
| `SECRET` | 32-char hex | Directus internal signing secret |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | — | Bootstrap admin credentials (only needed on first run) |
| `PUBLIC_URL` | `http://<cms-ip>:8055` | Public-facing URL |
| `EXTENSIONS_PATH` | `./extensions` | Path to custom extensions |
| `MEILISEARCH_HOST` | `http://localhost:7700` | Meilisearch URL (internal) |
| `MEILISEARCH_MASTER_KEY` | — | Meilisearch auth key |

### `wakr-etl` — `wakeco-backend/cms_etl/.env`

| Variable | Example | Description |
|----------|---------|-------------|
| `DIRECTUS_API_URL` | `http://<cms-ip>:8055/` | Directus base URL |
| `DIRECTUS_EMAIL` / `DIRECTUS_PASSWORD` | — | ETL service account |
| `STARDB_URL` | `postgresql+psycopg2://stardb:pass@rds-host:5432/wakr_stardb` | Star DB (sync driver) |
| `DAGSTER_POSTGRES_URL` | `postgresql://dagster:pass@rds-host:5432/dagster_cms` | Dagster state DB |
| `DAGSTER_HOME` | `/opt/wakr/cms_etl` | Directory containing `dagster.yaml` |
| `BATCH_SIZE` | `500` | Directus pagination page size |
| `CMS_SENSOR_INTERVAL_SECONDS` | `1800` | Sensor polling interval |

### `wakr-scrapper` — `wakr-scrapper/.env`

| Variable | Example | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | `sk-...` | OpenAI key (LLM selector discovery) |
| `GOOGLE_API_KEY` | `AIza...` | Google Maps geocoding |
| `DIRECTUS_API_URL` | `http://<cms-ip>:8055/` | Directus base URL |
| `DIRECTUS_EMAIL` / `DIRECTUS_PASSWORD` | — | Scrapper service account |
| `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` / `PGDATABASE` | — | Direct PG connection for history tables |
| `HEADLESS` | `true` | Run Chromium headless |
| `MAX_CONCURRENT_DEALERS` | `2` | Playwright concurrency (keep at 2 for t3.medium) |

---

## Appendix B — Security & Rotation Notes

The `TECHNICAL_ASSESSMENT.md` in `wakr-scrapper` documents that previous credentials were committed to git history. Before this deployment is considered live, complete all of the following:

1. **Rotate Directus admin password.** The original credential is in git history. Set a new password in SSM and Directus admin UI.
2. **Rotate OpenAI API key.** Log into OpenAI, revoke the old key, generate a new one, update SSM.
3. **Rotate Google Maps API key.** Revoke the compromised key in Google Cloud Console, generate a new restricted key (limit to geocoding API), update SSM.
4. **Consider cleaning git history** with BFG Repo-Cleaner if these repos will ever be made public or shared with contractors.
5. **Restrict Directus to known IPs** once the front-end client IP range is known. Currently the CMS port 8055 is open to `0.0.0.0/0` for test convenience.
6. **Do not run Star-DB API with `DEBUG=true`** on any internet-accessible instance. Debug mode accepts any Bearer token and bypasses all JWT validation.

---

## Appendix C — Instance Consolidation Option

If monthly cost is the primary constraint, the four EC2 instances can be collapsed into two:

| Server | Instance | Cost | Runs |
|--------|----------|------|------|
| `wakr-app` | t3.medium | ~$33/mo | Directus + Meilisearch + Star-DB API + Dagster |
| `wakr-scrapper` | t3.small | ~$17/mo | Playwright scraper |
| RDS | db.t3.micro | FREE yr1 | All 3 databases |

**Total: ~$50/month (yr 1) / ~$65/month (yr 2+)**

Trade-offs of consolidation:
- A memory spike during scraping could starve Directus or Dagster if co-located on the same host.
- Directus and the ETL daemon are always-on services; the scraper is a daily batch. Separating them is the safer architecture even for test.
- The consolidated option uses a t3.small for the scraper, which reduces concurrency to 1 (`MAX_CONCURRENT_DEALERS=1`) to stay within 2 GB RAM.

The 4-server layout described in the main plan is recommended for stability.

---

## Quick Reference — Service Restart Commands

```bash
# On wakr-api
sudo systemctl restart wakr-stardb-api
sudo journalctl -u wakr-stardb-api -f

# On wakr-cms
sudo systemctl restart directus
sudo docker restart meilisearch
sudo journalctl -u directus -f

# On wakr-etl
sudo systemctl restart dagster-daemon
sudo systemctl restart dagster-webserver
sudo journalctl -u dagster-daemon -f

# On wakr-scrapper
# Manual immediate run
sudo systemctl start wakr-scrapper.service
sudo journalctl -u wakr-scrapper -f
# Check next timer fire
systemctl list-timers wakr-scrapper.timer

# Rebuild scrapper Docker image after code update
# Note: /opt/wakr/scrapper is NOT a git repo on the instance.
# Deploy from local machine using git archive + SCP:
#   git archive --format=tar.gz HEAD -o /tmp/wakr-scrapper-latest.tar.gz
#   scp -i ~/.ssh/wakr-test.pem /tmp/wakr-scrapper-latest.tar.gz ec2-user@63.176.137.216:/tmp/
#   ssh -i ~/.ssh/wakr-test.pem ec2-user@63.176.137.216
#   sudo systemctl stop wakr-scrapper.timer wakr-scrapper.service
#   sudo cp /opt/wakr/scrapper/.env /tmp/scrapper.env.bak
#   sudo rm -rf /opt/wakr/scrapper && sudo mkdir -p /opt/wakr/scrapper
#   sudo tar -xzf /tmp/wakr-scrapper-latest.tar.gz -C /opt/wakr/scrapper
#   sudo cp /tmp/scrapper.env.bak /opt/wakr/scrapper/.env
sudo docker build -t wakr-scraper:latest /opt/wakr/scrapper
sudo systemctl start wakr-scrapper.timer
```

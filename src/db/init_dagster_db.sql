SELECT 'CREATE DATABASE dagster_cms'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dagster_cms')\gexec

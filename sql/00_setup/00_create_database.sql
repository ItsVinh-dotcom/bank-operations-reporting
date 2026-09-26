-- Run once as a superuser (psql):  psql -U postgres -f sql/00_setup/00_create_database.sql
-- Creates the data warehouse database for the fictional bank DLB.
SELECT 'CREATE DATABASE dlb_dwh ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dlb_dwh')\gexec

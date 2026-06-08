-- Migration 004: Role-based access control
-- Apply with: psql -U airflow -d nieruchomosci -f config/postgres/migrations/004_roles_and_permissions.sql

-- analyst_ro: read-only access for BI consumers and the Streamlit dashboard
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst_ro') THEN
        CREATE ROLE analyst_ro LOGIN PASSWORD 'analyst';
    END IF;
END $$;

-- admin_rw: full DML access for ETL pipeline operations
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'admin_rw') THEN
        CREATE ROLE admin_rw LOGIN PASSWORD 'admin';
    END IF;
END $$;

-- Database-level access
GRANT CONNECT ON DATABASE nieruchomosci TO analyst_ro, admin_rw;
GRANT USAGE ON SCHEMA public TO analyst_ro, admin_rw;

-- analyst_ro: SELECT only on all current and future tables/views
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst_ro;

-- admin_rw: full DML on all current and future tables and sequences
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO admin_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO admin_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO admin_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO admin_rw;

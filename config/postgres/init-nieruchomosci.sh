#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE nieruchomosci;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname nieruchomosci <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS postgis;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE nieruchomosci_test;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname nieruchomosci_test <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS postgis;
EOSQL

# Create application roles
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname nieruchomosci <<-EOSQL
    DO \$\$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst_ro') THEN
            CREATE ROLE analyst_ro LOGIN PASSWORD 'analyst';
        END IF;
    END \$\$;

    DO \$\$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'admin_rw') THEN
            CREATE ROLE admin_rw LOGIN PASSWORD 'admin';
        END IF;
    END \$\$;

    GRANT CONNECT ON DATABASE nieruchomosci TO analyst_ro, admin_rw;
    GRANT USAGE ON SCHEMA public TO analyst_ro, admin_rw;

    GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_ro;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst_ro;

    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO admin_rw;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO admin_rw;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO admin_rw;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO admin_rw;
EOSQL

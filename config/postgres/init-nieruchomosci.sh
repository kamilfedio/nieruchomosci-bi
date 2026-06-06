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

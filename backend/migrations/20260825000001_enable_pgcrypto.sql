-- Migration: 20260825000001_enable_pgcrypto
-- Purpose : Enable pgcrypto so gen_random_uuid() is available for every UUID
--           primary key in this and future migrations.
-- Idempotent: yes (IF NOT EXISTS)
-- Destructive: no

create extension if not exists pgcrypto;

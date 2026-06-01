-- Kayang Lakarin: stewardship metadata migration
-- Run once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query -> paste -> Run).
-- Non-destructive: adds two columns and updates rows. Safe to re-run (idempotent).

-- 1. Add columns with honest defaults (last wholesale review of the dataset).
ALTER TABLE outdoor_areas
  ADD COLUMN IF NOT EXISTS source text DEFAULT 'OpenStreetMap + editorial';
ALTER TABLE outdoor_areas
  ADD COLUMN IF NOT EXISTS last_reviewed date DEFAULT '2026-03-19';

-- 2. Backfill any NULLs left on pre-existing rows.
UPDATE outdoor_areas SET source = 'OpenStreetMap + editorial' WHERE source IS NULL;
UPDATE outdoor_areas SET last_reviewed = '2026-03-19' WHERE last_reviewed IS NULL;

-- 3. DENR monitoring sites (3).
UPDATE outdoor_areas
SET source = 'DENR monitoring'
WHERE name IN (
  'La Mesa Eco Park',
  'Arroceros Forest Park',
  'Las Pinas-Paranaque Wetland Park'
);

-- 4. Community-submitted spaces (5), reviewed when added.
UPDATE outdoor_areas
SET source = 'Community submission', last_reviewed = '2026-03-24'
WHERE name IN (
  'Sitio San Roque Tanimang Bayan',
  'Potrero MRF Eco-Garden & Playground',
  'Ugong Urban Vegetable Garden',
  'The Good Food Farm (Pamayanang Diego Silang)',
  'Buhay sa Gulay Urban Farm (Tondo)'
);

-- 5. Verify (optional): expect 95 OSM, 3 DENR, 5 Community.
-- SELECT source, count(*) FROM outdoor_areas GROUP BY source;

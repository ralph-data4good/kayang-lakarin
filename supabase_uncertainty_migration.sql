-- Kayang Lakarin: uncertainty metadata migration
-- Run once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query -> paste -> Run).
-- Non-destructive: only adds two columns and updates 8 rows. Safe to re-run (idempotent).

-- 1. Add columns with conservative, honest defaults.
--    Every site is "modeled"/"verified" unless explicitly upgraded below.
ALTER TABLE outdoor_areas
  ADD COLUMN IF NOT EXISTS aq_method text DEFAULT 'modeled';
ALTER TABLE outdoor_areas
  ADD COLUMN IF NOT EXISTS coord_confidence text DEFAULT 'verified';

-- 2. Ensure existing rows (added before the defaults) are not left NULL.
UPDATE outdoor_areas SET aq_method = 'modeled' WHERE aq_method IS NULL;
UPDATE outdoor_areas SET coord_confidence = 'verified' WHERE coord_confidence IS NULL;

-- 3. Air quality MEASURED from published DENR monitoring (3 sites).
UPDATE outdoor_areas
SET aq_method = 'measured'
WHERE name IN (
  'La Mesa Eco Park',
  'Arroceros Forest Park',
  'Las Pinas-Paranaque Wetland Park'
);

-- 4. APPROXIMATE locations: community gardens mapped to barangay/centroid level (5 sites).
UPDATE outdoor_areas
SET coord_confidence = 'approximate'
WHERE name IN (
  'Sitio San Roque Tanimang Bayan',
  'Potrero MRF Eco-Garden & Playground',
  'Ugong Urban Vegetable Garden',
  'The Good Food Farm (Pamayanang Diego Silang)',
  'Buhay sa Gulay Urban Farm (Tondo)'
);

-- 5. Verify (optional): should return 3 measured, 5 approximate.
-- SELECT aq_method, count(*) FROM outdoor_areas GROUP BY aq_method;
-- SELECT coord_confidence, count(*) FROM outdoor_areas GROUP BY coord_confidence;

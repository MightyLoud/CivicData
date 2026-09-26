-- Read-only CivicPatch jurisdiction snapshot for Representation Contract v1.
-- psql variable required: jurisdiction_ocdid
-- Example:
--   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 \
--     -v jurisdiction_ocdid='ocd-jurisdiction/country:us/state:co/place:akron/government' \
--     -Atf adapters/civicpatch/extract_snapshot.sql > civicpatch-snapshot.json
--
-- Run in a read-only repeatable-read transaction when snapshot consistency
-- across concurrent publishes matters.
--
-- This returns one JSONB document shaped for adapters/civicpatch/export_representation.py.
-- No writes, temporary tables, or schema changes are performed.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH target AS (
    SELECT j.jurisdiction_ocdid, j.data, j.updated_at
    FROM jurisdictions j
    WHERE j.jurisdiction_ocdid = :'jurisdiction_ocdid'
),
organization_rows AS (
    SELECT o.*
    FROM organizations o
    JOIN target t USING (jurisdiction_ocdid)
),
post_rows AS (
    SELECT p.*
    FROM posts p
    JOIN target t USING (jurisdiction_ocdid)
),
role_rows AS (
    SELECT
        r.id,
        r.label,
        r.status,
        r.is_unique,
        r.priority,
        r.created_at,
        COALESCE(
            (
                SELECT jsonb_agg(ra.label ORDER BY lower(ra.label), ra.label)
                FROM role_aliases ra
                WHERE ra.role_id = r.id
                  AND ra.status = 'active'
            ),
            '[]'::jsonb
        ) AS aliases
    FROM roles r
    WHERE r.id IN (SELECT DISTINCT role_id FROM post_rows)
),
person_rows AS (
    SELECT DISTINCT pe.*
    FROM people pe
    JOIN memberships m ON m.person_id = pe.id
    JOIN post_rows p ON p.id = m.post_id
),
membership_rows AS (
    SELECT m.*
    FROM memberships m
    JOIN post_rows p ON p.id = m.post_id
),
source_rows AS (
    SELECT s.*
    FROM source_records s
    JOIN target t USING (jurisdiction_ocdid)
)
SELECT jsonb_build_object(
    'jurisdiction',
    (
        SELECT jsonb_build_object(
            'jurisdiction_ocdid', t.jurisdiction_ocdid,
            'data', t.data,
            'updated_at', t.updated_at
        )
        FROM target t
    ),
    'organizations',
    COALESCE(
        (SELECT jsonb_agg(to_jsonb(o) ORDER BY o.sort_order, o.name, o.id) FROM organization_rows o),
        '[]'::jsonb
    ),
    'roles',
    COALESCE(
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.priority NULLS LAST, r.label, r.id) FROM role_rows r),
        '[]'::jsonb
    ),
    'posts',
    COALESCE(
        (SELECT jsonb_agg(to_jsonb(p) ORDER BY p.organization_id, p.role_id, p.division_ocdid, p.id) FROM post_rows p),
        '[]'::jsonb
    ),
    'people',
    COALESCE(
        (SELECT jsonb_agg(to_jsonb(pe) ORDER BY lower(pe.name), pe.id) FROM person_rows pe),
        '[]'::jsonb
    ),
    'memberships',
    COALESCE(
        (
            SELECT jsonb_agg(
                to_jsonb(m)
                ORDER BY m.organization_id, m.post_id, m.person_id, m.opened_at
            )
            FROM membership_rows m
        ),
        '[]'::jsonb
    ),
    'source_records',
    COALESCE(
        (
            SELECT jsonb_agg(
                to_jsonb(s)
                ORDER BY s.created_at, s.organization_id, s.person_id, s.id
            )
            FROM source_rows s
        ),
        '[]'::jsonb
    )
) AS civicpatch_snapshot;

COMMIT;

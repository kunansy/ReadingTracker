"""SQL shared by several revisions."""

REPEAT_NOTES_MATVIEW = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_repeat_notes AS
        WITH sample_notes AS (
            SELECT
                n.note_id,
                n.material_id,
                n.page,
                n.chapter,
                n.title,
                n.content,
                n.added_at,
                n.tags,
                COUNT(1) OVER () AS total_notes_count
            FROM notes n
            WHERE NOT n.is_deleted
        ),
        last_material_repeat AS (
            SELECT
                r.material_id,
                max(r.repeated_at) AS repeated_at,
                COUNT(1) AS repeats_count
            FROM repeats r
            GROUP BY r.material_id
        ),
        last_note_repeat_date AS (
            SELECT
                max(rh.repeated_at::date) as date,
                n.note_id
            FROM
                note_repeats_history rh
            FULL OUTER JOIN
                notes n ON n.note_id = rh.note_id
            WHERE
                n is null or not n.is_deleted
            GROUP BY n.note_id
        ), oldest_notes AS (
            SELECT
                DATE_TRUNC('month', lrd.date) as date,
                ARRAY_AGG(lrd.note_id) AS notes
            FROM
                last_note_repeat_date lrd
            GROUP BY
                date
            ORDER BY
                date NULLS FIRST, COUNT(1)
            LIMIT 1
        )
        SELECT
            n.note_id,
            m.material_id,
            m.title AS material_title,
            m.authors AS material_authors,
            m.material_type AS material_type,
            n.content,
            n.added_at,
            n.chapter,
            n.page,
            n.tags,
            m.pages AS material_pages,
            n.total_notes_count AS total_notes_count,
            0 AS min_repeat_freq,
            CASE
                -- in this case the note have no material
                WHEN m IS NULL THEN 'completed'
                WHEN s IS NULL THEN 'queue'
                WHEN s.completed_at IS NULL THEN 'reading'
                ELSE 'completed'
            END AS material_status,
            r.repeated_at,
            r.repeats_count
        FROM
            sample_notes n
        JOIN oldest_notes ON n.note_id = ANY(oldest_notes.notes)
        LEFT JOIN materials m ON n.material_id = m.material_id
        LEFT JOIN statuses s ON s.material_id = m.material_id
        LEFT JOIN last_material_repeat r ON r.material_id = s.material_id
    WITH NO DATA;
    """

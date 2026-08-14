-- AIR-0237: allow the web-admin publishing queue to represent the full
-- private-first upload lifecycle, including QA holds and public release.

ALTER TABLE public.publishing_requests
DROP CONSTRAINT IF EXISTS publishing_requests_status_check;

ALTER TABLE public.publishing_requests
ADD CONSTRAINT publishing_requests_status_check
CHECK (
    status IN (
        'pending',
        'approved',
        'to_be_published',
        'published',
        'release_requested',
        'public',
        'qa_hold',
        'failed',
        'rejected'
    )
);

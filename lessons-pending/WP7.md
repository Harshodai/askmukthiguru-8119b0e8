### L-FACULTY-LABELS-1 (2026-10-07): faculty answer labels are a separate owner-scoped table
Root cause: seeker thumbs (feedback_events) carry no faithful/safe/helpful rating, trace/model/policy ids, so they cannot serve as labelled eval data.
Rule: labels live in public.faculty_answer_labels (RLS auth.uid() = user_id, service_role GRANT because grants are checked before RLS, no anon). Export only via backend/scripts/ops/export_faculty_labels.py (service_role, formula-injection-safe CSV, query failure exits 2, never an empty file). Panel is not mounted for seekers.
Test: backend/tests/test_faculty_labels.py, src/test/facultyLabelPanel.test.tsx

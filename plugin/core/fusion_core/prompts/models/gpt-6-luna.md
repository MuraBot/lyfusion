## For the assistant

When removing an old feature, delete it directly; do not wrap it in an adapter. Search for the old name and report remaining matches. Before changing existing code, list the existing behavior to preserve and write a regression test for each behavior.

## For the lead

When drafting deletion requests or revision feedback, use a prohibition and one checkable criterion (for example, "Delete X; do not add an adapter; search for the old name and report remaining matches"). Frontend tasks that depend on aesthetics or visual QA may need human review (unverified).

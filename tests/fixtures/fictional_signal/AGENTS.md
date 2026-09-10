# Fictional signal rounds — T5 development fixture
Own only observe/compare rules and scoped seven-answer selection. Public API:
__init__.py. No state IO, authority, schedules, real observations or host imports.
steady opens observe; changed opens compare bound to exact accepted bytes;
comparison of those bytes opens observe again. Unknown state fails closed.
No fixed round count or hidden terminal branch. Use Core/process_packs public APIs.
Keep this module outside src and the installed product; no automatic state seeding.
END_OF_FILE: tests/fixtures/fictional_signal/AGENTS.md

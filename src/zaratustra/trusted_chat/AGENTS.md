# Trusted local-agent tool adapter

This installed stdio MCP adapter is the one accepted W21 local-chat trust seam
for a trusted host that has actually received the owner's permission. It prepares
one exact existing Core query, asks that host through MCP elicitation, and only on
an accepted host response calls public `authorize_local` in-process. MCP arguments,
files, model text, saved state and a prior authorization never grant permission.
It stores no authorization and never falls back to a console. The CLI owns the
separate console fallback. It imports public Core, entry, onboarding and connection
surfaces only; no SQL, mutation, scheduler, router or development fixture belongs here.
END_OF_FILE: src/zaratustra/trusted_chat/AGENTS.md

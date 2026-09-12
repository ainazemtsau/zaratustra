# Package boundary
Public package contains Core, trusted local adapter and CLI for records and mutations.
The entry adapter owns an explicit discovery catalog and depends only on public Core.
The intake coordinator depends only on public Core and composes exact standard
publication/acceptance operations after separately trusted confirmation.
The first_use coordinator composes public Core, entry and intake surfaces for one
explicit generic bootstrap and manual external-chat exchange; it grants no authority.
Use submodule public __init__.py surfaces. New modules need graph contracts.
Data/workspaces are not package resources. Do not add product state to source.
END_OF_FILE: src/zaratustra/AGENTS.md

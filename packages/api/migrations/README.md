# Kinetic Database Migrations

## Setup

`000_complete_schema.sql` is the canonical setup file. It creates the entire schema from scratch — extensions, functions, enums, all 21 tables, RLS policies, triggers, and indexes.

To set up a fresh database:

```sql
\i 000_complete_schema.sql
```

## Historical files

The following files are retained for reference but are fully superseded by `000_complete_schema.sql`:

- `001_create_users.sql` — original users table creation
- `002_add_disabled_at_to_users.sql` — column addition
- `20260323000003_create_retrieval_debug_logs.sql` — retrieval debug logs table
- `20260324000004_create_knowledge_base_tables.sql` — knowledge base tables

Do not run these individually — everything they contain is already in `000_complete_schema.sql`.

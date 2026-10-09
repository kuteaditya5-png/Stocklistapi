-- Run once in pgAdmin Query Tool against your chosen PostgreSQL database.
CREATE SCHEMA IF NOT EXISTS date_invite;
CREATE TABLE IF NOT EXISTS date_invite.responses (
 response_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 invitation_key TEXT NOT NULL UNIQUE,
 recipient_name VARCHAR(60) NOT NULL,
 selected_date DATE NOT NULL,
 selected_time TIME NOT NULL,
 timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Kolkata',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS date_invite.login_limits (
 key TEXT PRIMARY KEY,
 attempts INTEGER NOT NULL,
 window_start TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Run in Neon SQL Editor BEFORE deploying the updated code. Existing responses are preserved.
ALTER TABLE date_invite.responses ADD COLUMN IF NOT EXISTS date_idea TEXT CHECK (date_idea IN ('coffee','movie','sunset','dinner'));
-- Read responses (newest first):
SELECT response_id,recipient_name,selected_date,selected_time,timezone,date_idea,created_at FROM date_invite.responses ORDER BY created_at DESC;
-- If your runtime user is different from the schema owner, grant only necessary privileges:
-- GRANT USAGE ON SCHEMA date_invite TO your_runtime_user;
-- GRANT SELECT,INSERT ON date_invite.responses TO your_runtime_user;
-- GRANT SELECT,INSERT,UPDATE,DELETE ON date_invite.login_limits TO your_runtime_user;
-- GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA date_invite TO your_runtime_user;

-- Run in Neon SQL Editor before deploying the dashboard update.
-- Existing responses are preserved. Safe to run again.
CREATE SCHEMA IF NOT EXISTS date_invite;
CREATE TABLE IF NOT EXISTS date_invite.invitations (
 invitation_id TEXT PRIMARY KEY,
 recipient_name VARCHAR(60) NOT NULL CHECK (length(btrim(recipient_name))>0),
 token TEXT NOT NULL UNIQUE,
 active_slot INTEGER UNIQUE CHECK (active_slot BETWEEN 1 AND 10),
 response_key TEXT NOT NULL UNIQUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 revoked_at TIMESTAMPTZ,
 CHECK ((active_slot IS NOT NULL AND revoked_at IS NULL) OR (active_slot IS NULL AND revoked_at IS NOT NULL))
);
ALTER TABLE date_invite.responses ADD COLUMN IF NOT EXISTS date_idea TEXT CHECK (date_idea IN ('coffee','movie','sunset','dinner'));
-- If the runtime role differs from the owner:
-- GRANT USAGE ON SCHEMA date_invite TO your_runtime_user;
-- GRANT SELECT,INSERT,UPDATE ON date_invite.invitations TO your_runtime_user;

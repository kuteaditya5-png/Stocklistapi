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

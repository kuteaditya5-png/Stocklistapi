-- Run in Neon SQL Editor BEFORE deploying the updated code. Existing responses are preserved.
ALTER TABLE date_invite.responses ADD COLUMN IF NOT EXISTS date_idea TEXT CHECK (date_idea IN ('coffee','movie','sunset','dinner'));

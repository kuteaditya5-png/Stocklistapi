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
-- Read responses (newest first):
SELECT response_id,recipient_name,selected_date,selected_time,timezone,created_at FROM date_invite.responses ORDER BY created_at DESC;
-- If your runtime user is different from the schema owner, grant only necessary privileges:
-- GRANT USAGE ON SCHEMA date_invite TO your_runtime_user;
-- GRANT SELECT,INSERT ON date_invite.responses TO your_runtime_user;
-- GRANT SELECT,INSERT,UPDATE,DELETE ON date_invite.login_limits TO your_runtime_user;
-- GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA date_invite TO your_runtime_user;

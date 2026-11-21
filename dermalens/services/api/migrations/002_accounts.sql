-- Upgrade for databases created before account security was added (v0.2.0).
-- New databases get this from 001_init.sql. start.sh applies the same change
-- automatically (python -m app.schema_upgrade), so running this by hand is optional.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_logins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE;
-- Existing staff and admin accounts were created by an admin, so count them as verified.
UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL AND role <> 'patient';

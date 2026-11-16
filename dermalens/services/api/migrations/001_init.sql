-- DermaLens schema (PostgreSQL 16). Generated from app/models.py; do not edit by hand.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_settings (
	key VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE concerns (
	code VARCHAR(40) NOT NULL, 
	display_name TEXT NOT NULL, 
	model_label BOOLEAN NOT NULL, 
	PRIMARY KEY (code)
);

CREATE TABLE ingredient_families (
	code VARCHAR(40) NOT NULL, 
	display_name TEXT NOT NULL, 
	PRIMARY KEY (code)
);

CREATE TABLE ingredients (
	id VARCHAR(64) NOT NULL, 
	inci_name TEXT NOT NULL, 
	irritancy_level SMALLINT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	photosensitizing BOOLEAN NOT NULL, 
	pregnancy_avoid BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (irritancy_level BETWEEN 0 AND 3), 
	UNIQUE (inci_name)
);

CREATE TABLE model_versions (
	id VARCHAR(64) NOT NULL, 
	architecture TEXT NOT NULL, 
	artifact_sha256 VARCHAR(64) NOT NULL, 
	thresholds JSONB NOT NULL, 
	temperature JSONB NOT NULL, 
	eval_report_uri TEXT NOT NULL, 
	released_at TIMESTAMP WITH TIME ZONE, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE products (
	id VARCHAR(64) NOT NULL, 
	brand TEXT NOT NULL, 
	name TEXT NOT NULL, 
	category VARCHAR(20) NOT NULL, 
	suitable_skin_types JSONB NOT NULL, 
	spf SMALLINT, 
	pa_rating VARCHAR(8), 
	price_php NUMERIC(10, 2), 
	stocked_by_iconic BOOLEAN NOT NULL, 
	is_listed BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (category IN ('cleanser', 'toner', 'serum', 'treatment', 'moisturizer', 'sunscreen', 'exfoliant'))
);

CREATE TABLE red_flag_definitions (
	code VARCHAR(40) NOT NULL, 
	question_text TEXT NOT NULL, 
	route VARCHAR(20) NOT NULL, 
	rule_set_version TEXT NOT NULL, 
	PRIMARY KEY (code), 
	CHECK (route IN ('dermatologist', 'urgent_care'))
);

CREATE TABLE users (
	id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	password_hash TEXT NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	display_name TEXT, 
	created_by UUID, 
	disabled_at TIMESTAMP WITH TIME ZONE, 
	mfa_secret_enc BYTEA, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CHECK (role IN ('patient', 'clinic_staff', 'dermatologist', 'admin')), 
	UNIQUE (email), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE audit_log (
	id BIGSERIAL NOT NULL, 
	actor_id UUID, 
	action TEXT NOT NULL, 
	entity TEXT NOT NULL, 
	entity_id TEXT NOT NULL, 
	ip_hash VARCHAR(64), 
	detail JSONB, 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_log_entity ON audit_log (entity, entity_id);

CREATE TABLE consents (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	purpose VARCHAR(32) NOT NULL, 
	policy_version TEXT NOT NULL, 
	granted BOOLEAN NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (purpose IN ('service', 'image_storage', 'share_with_clinic', 'model_improvement')), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE contraindications (
	id UUID NOT NULL, 
	condition_code VARCHAR(32) NOT NULL, 
	family_code VARCHAR(40), 
	ingredient_id VARCHAR(64), 
	action VARCHAR(24) NOT NULL, 
	rule_set_version TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (action IN ('exclude', 'limit_wash_off', 'limit_low_irritancy')), 
	FOREIGN KEY(family_code) REFERENCES ingredient_families (code), 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id)
);

CREATE TABLE ingredient_concern_benefits (
	ingredient_id VARCHAR(64) NOT NULL, 
	concern_code VARCHAR(40) NOT NULL, 
	weight FLOAT NOT NULL, 
	evidence_note TEXT NOT NULL, 
	PRIMARY KEY (ingredient_id, concern_code), 
	CHECK (weight BETWEEN 0 AND 1), 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id), 
	FOREIGN KEY(concern_code) REFERENCES concerns (code)
);

CREATE TABLE ingredient_conflicts (
	id UUID NOT NULL, 
	family_a VARCHAR(40) NOT NULL, 
	family_b VARCHAR(40) NOT NULL, 
	scope VARCHAR(20) NOT NULL, 
	resolution VARCHAR(20) NOT NULL, 
	rationale TEXT NOT NULL, 
	rule_set_version TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (scope IN ('same_application', 'same_routine', 'same_day')), 
	CHECK (resolution IN ('block', 'split_am_pm', 'alternate_nights')), 
	FOREIGN KEY(family_a) REFERENCES ingredient_families (code), 
	FOREIGN KEY(family_b) REFERENCES ingredient_families (code)
);

CREATE TABLE ingredient_family_members (
	family_code VARCHAR(40) NOT NULL, 
	ingredient_id VARCHAR(64) NOT NULL, 
	PRIMARY KEY (family_code, ingredient_id), 
	FOREIGN KEY(family_code) REFERENCES ingredient_families (code), 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id)
);

CREATE TABLE ingredient_synonyms (
	synonym VARCHAR(120) NOT NULL, 
	ingredient_id VARCHAR(64) NOT NULL, 
	PRIMARY KEY (synonym), 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id)
);

CREATE TABLE intakes (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	questionnaire_version TEXT NOT NULL, 
	sleep_hours NUMERIC(3, 1), 
	daily_sun_exposure_min SMALLINT, 
	sunscreen_use VARCHAR(16), 
	smoker BOOLEAN, 
	stress_level SMALLINT, 
	water_glasses_per_day SMALLINT, 
	current_rx_topicals BOOLEAN NOT NULL, 
	on_isotretinoin BOOLEAN NOT NULL, 
	uses_actives_without_reaction BOOLEAN NOT NULL, 
	free_text_enc BYTEA, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (sunscreen_use IN ('never', 'sometimes', 'daily')), 
	CHECK (stress_level BETWEEN 1 AND 5), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE patient_profiles (
	user_id UUID NOT NULL, 
	full_name_enc BYTEA NOT NULL, 
	birth_year SMALLINT, 
	sex_at_birth VARCHAR(16), 
	self_fitzpatrick SMALLINT, 
	skin_type VARCHAR(16), 
	is_pregnant_or_breastfeeding BOOLEAN NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	CHECK (birth_year BETWEEN 1900 AND 2100), 
	CHECK (sex_at_birth IN ('female', 'male', 'intersex', 'prefer_not')), 
	CHECK (self_fitzpatrick BETWEEN 1 AND 6), 
	CHECK (skin_type IN ('dry', 'oily', 'combination', 'normal', 'sensitive')), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE product_fda_notifications (
	product_id VARCHAR(64) NOT NULL, 
	notification_no TEXT NOT NULL, 
	verified_on DATE NOT NULL, 
	verified_by UUID NOT NULL, 
	evidence_uri TEXT NOT NULL, 
	valid_until DATE, 
	PRIMARY KEY (product_id), 
	FOREIGN KEY(product_id) REFERENCES products (id), 
	FOREIGN KEY(verified_by) REFERENCES users (id)
);

CREATE TABLE product_ingredients (
	product_id VARCHAR(64) NOT NULL, 
	ingredient_id VARCHAR(64) NOT NULL, 
	position SMALLINT NOT NULL, 
	PRIMARY KEY (product_id, ingredient_id), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id)
);

CREATE INDEX ix_product_ingredients_ingredient ON product_ingredients (ingredient_id);

CREATE TABLE refresh_tokens (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	UNIQUE (token_hash)
);

CREATE TABLE rule_signoffs (
	id UUID NOT NULL, 
	triage_version TEXT NOT NULL, 
	rule_set_version TEXT NOT NULL, 
	signed_by UUID NOT NULL, 
	note TEXT, 
	signed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(signed_by) REFERENCES users (id)
);

CREATE TABLE user_allergens (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	ingredient_id VARCHAR(64), 
	family_code VARCHAR(40), 
	raw_text TEXT, 
	PRIMARY KEY (id), 
	CHECK (ingredient_id IS NOT NULL OR family_code IS NOT NULL OR raw_text IS NOT NULL), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id), 
	FOREIGN KEY(family_code) REFERENCES ingredient_families (code)
);

CREATE TABLE capture_sessions (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	intake_id UUID NOT NULL, 
	device_model TEXT, 
	app_version TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	quality_failures SMALLINT NOT NULL, 
	error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (status IN ('open', 'uploaded', 'processing', 'needs_retake', 'complete', 'failed')), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(intake_id) REFERENCES intakes (id)
);

CREATE INDEX ix_capture_sessions_user_created ON capture_sessions (user_id, created_at);

CREATE TABLE current_routine_items (
	id UUID NOT NULL, 
	intake_id UUID NOT NULL, 
	time_of_day VARCHAR(4), 
	product_id VARCHAR(64), 
	free_text_name TEXT, 
	reaction_reported BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (time_of_day IN ('am', 'pm', 'both')), 
	FOREIGN KEY(intake_id) REFERENCES intakes (id) ON DELETE CASCADE, 
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE TABLE intake_concerns (
	intake_id UUID NOT NULL, 
	concern_code VARCHAR(40) NOT NULL, 
	self_severity SMALLINT, 
	duration_weeks SMALLINT, 
	PRIMARY KEY (intake_id, concern_code), 
	CHECK (self_severity BETWEEN 1 AND 3), 
	FOREIGN KEY(intake_id) REFERENCES intakes (id) ON DELETE CASCADE, 
	FOREIGN KEY(concern_code) REFERENCES concerns (code)
);

CREATE TABLE intake_red_flags (
	intake_id UUID NOT NULL, 
	red_flag_code VARCHAR(40) NOT NULL, 
	answer BOOLEAN NOT NULL, 
	PRIMARY KEY (intake_id, red_flag_code), 
	FOREIGN KEY(intake_id) REFERENCES intakes (id) ON DELETE CASCADE, 
	FOREIGN KEY(red_flag_code) REFERENCES red_flag_definitions (code)
);

CREATE TABLE consultation_summaries (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	pdf_object_key TEXT NOT NULL, 
	data JSONB NOT NULL, 
	share_token_hash VARCHAR(64), 
	shared_with VARCHAR(20), 
	expires_at TIMESTAMP WITH TIME ZONE, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	staff_note TEXT, 
	follow_up_status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (shared_with IN ('iconic_clinic', 'patient_only')), 
	CHECK (follow_up_status IN ('new', 'contacted', 'booked', 'no_response', 'closed')), 
	FOREIGN KEY(session_id) REFERENCES capture_sessions (id), 
	UNIQUE (share_token_hash), 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE TABLE images (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	view VARCHAR(10) NOT NULL, 
	object_key TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	width_px INTEGER, 
	height_px INTEGER, 
	blur_score FLOAT, 
	brightness_mean FLOAT, 
	face_coverage FLOAT, 
	device_checks JSONB, 
	server_checks JSONB, 
	quality_pass BOOLEAN NOT NULL, 
	superseded BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (view IN ('front', 'left45', 'right45', 'closeup')), 
	FOREIGN KEY(session_id) REFERENCES capture_sessions (id) ON DELETE CASCADE
);

CREATE TABLE inferences (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	model_version_id VARCHAR(64) NOT NULL, 
	quality_pass BOOLEAN NOT NULL, 
	ood_score FLOAT NOT NULL, 
	ood_flag BOOLEAN NOT NULL, 
	refer_out_probability FLOAT NOT NULL, 
	raw JSONB NOT NULL, 
	latency_ms INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES capture_sessions (id), 
	FOREIGN KEY(model_version_id) REFERENCES model_versions (id)
);

CREATE TABLE derm_reviews (
	id UUID NOT NULL, 
	summary_id UUID NOT NULL, 
	reviewer_id UUID NOT NULL, 
	app_route VARCHAR(20) NOT NULL, 
	derm_route VARCHAR(20) NOT NULL, 
	concern_agreement JSONB NOT NULL, 
	note TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (summary_id, reviewer_id), 
	CHECK (derm_route IN ('urgent_care', 'dermatologist', 'iconic_clinic', 'self_care')), 
	FOREIGN KEY(summary_id) REFERENCES consultation_summaries (id), 
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
);

CREATE TABLE inference_labels (
	inference_id UUID NOT NULL, 
	concern_code VARCHAR(40) NOT NULL, 
	probability FLOAT NOT NULL, 
	present BOOLEAN NOT NULL, 
	grade VARCHAR(10) NOT NULL, 
	uncertain BOOLEAN NOT NULL, 
	PRIMARY KEY (inference_id, concern_code), 
	CHECK (probability BETWEEN 0 AND 1), 
	CHECK (grade IN ('none', 'mild', 'moderate', 'marked')), 
	FOREIGN KEY(inference_id) REFERENCES inferences (id) ON DELETE CASCADE, 
	FOREIGN KEY(concern_code) REFERENCES concerns (code)
);

CREATE TABLE triage_decisions (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	inference_id UUID, 
	route VARCHAR(20) NOT NULL, 
	reasons JSONB NOT NULL, 
	rule_set_version TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (route IN ('urgent_care', 'dermatologist', 'iconic_clinic', 'self_care')), 
	UNIQUE (session_id), 
	FOREIGN KEY(session_id) REFERENCES capture_sessions (id), 
	FOREIGN KEY(inference_id) REFERENCES inferences (id)
);

CREATE TABLE recommendations (
	id UUID NOT NULL, 
	triage_id UUID NOT NULL, 
	rule_set_version TEXT NOT NULL, 
	catalog_snapshot_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	input_hash VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	notes JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(triage_id) REFERENCES triage_decisions (id)
);

CREATE TABLE recommendation_items (
	recommendation_id UUID NOT NULL, 
	time_of_day VARCHAR(2) NOT NULL, 
	step_order SMALLINT NOT NULL, 
	slot VARCHAR(16) NOT NULL, 
	product_id VARCHAR(64) NOT NULL, 
	frequency VARCHAR(20) NOT NULL, 
	why TEXT NOT NULL, 
	patch_test BOOLEAN NOT NULL, 
	PRIMARY KEY (recommendation_id, time_of_day, step_order), 
	CHECK (time_of_day IN ('am', 'pm')), 
	CHECK (frequency IN ('daily', 'alternate_nights', '2x_week')), 
	FOREIGN KEY(recommendation_id) REFERENCES recommendations (id) ON DELETE CASCADE, 
	FOREIGN KEY(product_id) REFERENCES products (id)
);


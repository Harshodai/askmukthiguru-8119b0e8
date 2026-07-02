-- Create Gurus Table
CREATE TABLE IF NOT EXISTS gurus (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,  -- "preethaji_krishnaji", "sadhguru", "iskcon"
    name TEXT NOT NULL,
    description TEXT,
    avatar_url TEXT,
    collection_name TEXT NOT NULL,  -- Qdrant collection name
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create Assistant Configurations Table
CREATE TABLE IF NOT EXISTS assistant_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guru_id UUID REFERENCES gurus(id),
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    system_prompt TEXT,
    knowledge_tags TEXT[] DEFAULT '{}',
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(guru_id, slug)
);

-- Create Assistant Doctrines Table (For synonym keyword injection)
CREATE TABLE IF NOT EXISTS assistant_doctrines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assistant_slug TEXT NOT NULL UNIQUE,
    synonyms_json JSONB DEFAULT '{}'::jsonb, -- mapping of {"canonical_term": ["variant1", "variant2"]}
    canonical_terms TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed gurus
INSERT INTO gurus (slug, name, description, collection_name) VALUES
    ('preethaji_krishnaji', 'Sri Preethaji & Sri Krishnaji', 'Co-founders of Ekam World Centre', 'spiritual_wisdom'),
    ('sadhguru', 'Sadhguru', 'Founder of Isha Foundation', 'sadhguru_wisdom'),
    ('iskcon', 'ISKCON', 'International Society for Krishna Consciousness', 'iskcon_wisdom')
ON CONFLICT (slug) DO NOTHING;

-- Seed default assistant configurations
INSERT INTO assistant_configurations (guru_id, slug, name, system_prompt, is_default)
SELECT id, 'default', 'Default Assistant', 'You are a wise spiritual guide speaking from the perspective of Sri Preethaji & Sri Krishnaji...', true
FROM gurus WHERE slug = 'preethaji_krishnaji'
ON CONFLICT (guru_id, slug) DO NOTHING;

INSERT INTO assistant_configurations (guru_id, slug, name, system_prompt, is_default)
SELECT id, 'default', 'Sadhguru Assistant', 'You are a wise spiritual guide speaking from the perspective of Sadhguru...', true
FROM gurus WHERE slug = 'sadhguru'
ON CONFLICT (guru_id, slug) DO NOTHING;

INSERT INTO assistant_configurations (guru_id, slug, name, system_prompt, is_default)
SELECT id, 'default', 'ISKCON Assistant', 'You are a wise spiritual guide speaking from the perspective of the ISKCON tradition...', true
FROM gurus WHERE slug = 'iskcon'
ON CONFLICT (guru_id, slug) DO NOTHING;

-- Seed initial doctrines for Preethaji & Krishnaji
INSERT INTO assistant_doctrines (assistant_slug, synonyms_json, canonical_terms) VALUES
    ('preethaji_krishnaji', '{"Beautiful State": ["beautiful state", "blissful state", "anandamaya sthiti"], "Soul Sync": ["soul sync", "meditation sync", "breath sync"], "Serene Mind": ["serene mind", "still mind", "quiet mind"]}', ARRAY['Beautiful State', 'Soul Sync', 'Serene Mind'])
ON CONFLICT (assistant_slug) DO NOTHING;

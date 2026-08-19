/**
 * EU AI Act Compliance & Machine-Readable Provenance Types
 *
 * Implements European Union Artificial Intelligence Act (Regulation (EU) 2024/1689)
 * Article 50 transparency obligations and W3C PROV-O JSON-LD machine-readable specification.
 */

import type { Message } from '@/lib/chatStorage';

export type OriginType = 'human_generated' | 'ai_assisted' | 'ai_generated';

export type ArtifactModality = 'text' | 'audio' | 'image' | 'video' | 'multimodal';

export type EUComplianceRiskTier = 'minimal' | 'transparency' | 'high' | 'unacceptable';

export type GroundingStatus = 'grounded' | 'abstained' | 'safety_redirect' | 'system_error' | 'unverified';

export interface ModelDescriptor {
  name: string;
  version?: string;
  provider?: string;
  parameters?: string;
}

export interface ProvenanceSource {
  title?: string;
  url?: string;
  quote?: string;
  corpusId?: string;
  score?: number;
}

export interface ProvenanceGroundingInfo {
  status: GroundingStatus;
  sourceCount: number;
  sources?: ProvenanceSource[];
  confidenceScore?: number;
  confidenceReason?: string;
  evidenceSupportLabel?: string;
  corpusId?: string;
  corpusVersion?: string;
}

export interface Article50Disclosure {
  article: 'Article 50(1)' | 'Article 50(2)' | 'Article 50(4)';
  notice: string;
  plainLanguageDisclosure: string;
}

export interface AIProvenanceManifest {
  id: string;
  originType: OriginType;
  riskTier: EUComplianceRiskTier;
  modality: ArtifactModality;
  generatedAt: string; // ISO 8601
  modelDescriptor: ModelDescriptor;
  latencyMs?: number;
  grounding: ProvenanceGroundingInfo;
  disclosure: Article50Disclosure;
  jsonLd?: Record<string, unknown>;
}

/**
 * Generates W3C PROV-O and schema.org / EU AI Act compliant JSON-LD machine-readable provenance.
 */
export function generateProvOJsonLd(manifest: AIProvenanceManifest): Record<string, unknown> {
  const sources = manifest.grounding.sources || [];

  return {
    '@context': {
      'prov': 'http://www.w3.org/ns/prov#',
      'xsd': 'http://www.w3.org/2001/XMLSchema#',
      'schema': 'https://schema.org/',
      'eu-ai-act': 'https://eur-lex.europa.eu/eli/reg/2024/1689/oj#'
    },
    '@id': `urn:askmukthiguru:provenance:${manifest.id}`,
    '@type': ['prov:Entity', 'eu-ai-act:AIGeneratedOutput', 'schema:CreativeWork'],
    'prov:generatedAtTime': {
      '@type': 'xsd:dateTime',
      '@value': manifest.generatedAt
    },
    'eu-ai-act:originClassification': manifest.originType,
    'eu-ai-act:complianceRiskTier': manifest.riskTier,
    'eu-ai-act:transparencyNotice': manifest.disclosure.notice,
    'eu-ai-act:article50Disclosure': manifest.disclosure.plainLanguageDisclosure,
    'prov:wasGeneratedBy': {
      '@type': ['prov:Activity', 'eu-ai-act:InferenceActivity'],
      'prov:endedAtTime': manifest.generatedAt,
      'prov:wasAssociatedWith': {
        '@type': ['prov:Agent', 'prov:SoftwareAgent', 'eu-ai-act:AISystem'],
        'schema:name': manifest.modelDescriptor.name,
        'schema:provider': manifest.modelDescriptor.provider || 'AskMukthiGuru AI',
        'schema:version': manifest.modelDescriptor.version || '2.6.0',
        'eu-ai-act:systemRole': 'Spiritual AI Assistant & Wisdom Retriever'
      },
      ...(manifest.latencyMs ? { 'eu-ai-act:executionDurationMs': manifest.latencyMs } : {})
    },
    'eu-ai-act:groundingState': manifest.grounding.status,
    'eu-ai-act:sourceCount': manifest.grounding.sourceCount,
    'prov:wasDerivedFrom': sources.map((src, index) => ({
      '@type': ['prov:Entity', 'schema:DigitalDocument'],
      'schema:position': index + 1,
      'schema:url': src.url || 'urn:askmukthiguru:corpus:teaching',
      'schema:name': src.title || `Sacred Wisdom Source #${index + 1}`,
      ...(src.quote ? { 'schema:text': src.quote } : {}),
      ...(src.corpusId ? { 'eu-ai-act:corpusId': src.corpusId } : {})
    }))
  };
}

const asRecord = (value: unknown): Record<string, unknown> | null => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
);

const asString = (value: unknown): string | undefined => (
  typeof value === 'string' && value.trim() ? value : undefined
);

const asNumber = (value: unknown): number | undefined => (
  typeof value === 'number' && Number.isFinite(value) ? value : undefined
);

const normalizeOriginType = (value: unknown): OriginType => {
  const normalized = asString(value)?.toLowerCase();
  return normalized === 'human_generated' ? 'human_generated'
    : normalized === 'ai_assisted' ? 'ai_assisted'
      : 'ai_generated';
};

const normalizeModality = (value: unknown): ArtifactModality => {
  const normalized = asString(value)?.toLowerCase();
  if (normalized === 'audio' || normalized === 'image' || normalized === 'video' || normalized === 'multimodal') {
    return normalized;
  }
  return 'text';
};

const normalizeRiskTier = (value: unknown): EUComplianceRiskTier => {
  const normalized = asString(value)?.toLowerCase();
  return normalized === 'minimal' ? 'minimal'
    : normalized === 'high' ? 'high'
      : normalized === 'unacceptable' ? 'unacceptable'
        : 'transparency';
};

/**
 * Creates a standard AIProvenanceManifest from a Chat Message.
 *
 * Backend provenance is authoritative when available. Older locally stored
 * messages still receive a conservative fallback manifest.
 */
export function createProvenanceManifestFromMessage(
  message: Message,
  options?: Partial<AIProvenanceManifest>
): AIProvenanceManifest {
  const citations = message.citations || [];
  const raw = asRecord(message.provenanceManifest) || asRecord(message.aiProvenance);
  const rawAgent = asRecord(raw?.agent);
  const rawSources = Array.isArray(raw?.sources)
    ? raw.sources.map(asRecord).filter((source): source is Record<string, unknown> => source !== null)
    : [];
  const backendSources: ProvenanceSource[] = rawSources.map((source, index) => ({
    title: asString(source.title) || asString(source.name) || `Wisdom Reference ${index + 1}`,
    url: asString(source.url) || asString(source.source_url),
    quote: asString(source.quote) || asString(source.excerpt),
    corpusId: asString(source.corpus_id) || asString(source.corpusId),
    score: asNumber(source.score) ?? asNumber(source.relevance_score),
  }));
  const sources: ProvenanceSource[] = backendSources.length > 0
    ? backendSources
    : citations.map((url, i) => ({
      url,
      title: `Wisdom Reference ${i + 1}`,
      corpusId: message.answerEvidence?.corpus_id || 'spiritual_wisdom'
    }));

  const generatedIso = asString(raw?.generated_at)
    || (message.timestamp instanceof Date ? message.timestamp.toISOString() : new Date().toISOString());
  const backendSourceCount = asNumber(raw?.source_count) ?? asNumber(raw?.sourceCount);
  const fallbackGroundingStatus: GroundingStatus = message.groundingState || (citations.length > 0 ? 'grounded' : 'unverified');
  const manifest: AIProvenanceManifest = {
    id: asString(raw?.manifest_id) || asString(raw?.content_id) || asString(raw?.artifact_id) || message.id || `msg-${Date.now()}`,
    originType: normalizeOriginType(raw?.origin_type),
    riskTier: normalizeRiskTier(raw?.risk_tier),
    modality: normalizeModality(raw?.modality),
    generatedAt: generatedIso,
    modelDescriptor: {
      name: asString(raw?.model_name) || asString(rawAgent?.name) || message.modelUsed || 'AskMukthiGuru Hybrid Ensemble',
      version: asString(raw?.schema_version) || 'v2.6.0',
      provider: asString(raw?.model_provider) || asString(rawAgent?.provider) || message.modelProvider || 'AskMukthiGuru Cloud',
      parameters: asString(rawAgent?.role) || 'Dual-Level GraphRAG + BGE-M3 + LLaMA 3.1 / Sarvam'
    },
    latencyMs: message.latencyMs ?? undefined,
    grounding: {
      status: fallbackGroundingStatus,
      sourceCount: backendSourceCount ?? sources.length,
      sources,
      confidenceScore: asNumber(raw?.confidence_score) ?? message.confidenceScore,
      confidenceReason: message.confidenceReason,
      evidenceSupportLabel: message.answerEvidence?.evidence_support_label || (sources.length > 0 ? 'Verified Corpus Grounding' : 'Reflective Guidance'),
      corpusId: message.answerEvidence?.corpus_id || 'spiritual_wisdom',
      corpusVersion: message.answerEvidence?.release_version ? `v${message.answerEvidence.release_version}` : undefined
    },
    disclosure: {
      article: 'Article 50(1)',
      notice: asString(raw?.disclosure_statement) || 'AI-Generated Content: This response was synthesized by AskMukthiGuru artificial intelligence.',
      plainLanguageDisclosure: asString(raw?.disclaimer) || asString(raw?.disclosure_statement) || 'In compliance with EU AI Act Article 50: You are interacting with an AI assistant grounded in spiritual wisdom teachings. Responses do not replace human spiritual masters, mental health professionals, or medical practitioners.'
    },
    ...options
  };

  manifest.jsonLd = generateProvOJsonLd(manifest);
  return manifest;
}

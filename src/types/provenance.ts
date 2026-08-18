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

/**
 * Creates a standard AIProvenanceManifest from a Chat Message.
 */
export function createProvenanceManifestFromMessage(
  message: Message,
  options?: Partial<AIProvenanceManifest>
): AIProvenanceManifest {
  const citations = message.citations || [];
  const groundingStatus: GroundingStatus = message.groundingState || (citations.length > 0 ? 'grounded' : 'unverified');

  const sources: ProvenanceSource[] = citations.map((url, i) => ({
    url,
    title: `Wisdom Reference ${i + 1}`,
    corpusId: message.answerEvidence?.corpus_id || 'spiritual_wisdom'
  }));

  const generatedIso = message.timestamp instanceof Date
    ? message.timestamp.toISOString()
    : new Date().toISOString();

  const manifest: AIProvenanceManifest = {
    id: message.id || `msg-${Date.now()}`,
    originType: 'ai_generated',
    riskTier: 'transparency',
    modality: 'text',
    generatedAt: generatedIso,
    modelDescriptor: {
      name: 'AskMukthiGuru Hybrid Ensemble',
      version: 'v2.6.0',
      provider: 'AskMukthiGuru Cloud',
      parameters: 'Dual-Level GraphRAG + BGE-M3 + LLaMA 3.1 / Sarvam'
    },
    grounding: {
      status: groundingStatus,
      sourceCount: citations.length,
      sources,
      confidenceScore: message.confidenceScore,
      confidenceReason: message.confidenceReason,
      evidenceSupportLabel: message.answerEvidence?.evidence_support_label || (citations.length > 0 ? 'Verified Corpus Grounding' : 'Reflective Guidance'),
      corpusId: message.answerEvidence?.corpus_id || 'spiritual_wisdom',
      corpusVersion: message.answerEvidence?.release_version ? `v${message.answerEvidence.release_version}` : 'v2026.08'
    },
    disclosure: {
      article: 'Article 50(1)',
      notice: 'AI-Generated Content: This response was synthesized by AskMukthiGuru artificial intelligence.',
      plainLanguageDisclosure: 'In compliance with EU AI Act Article 50: You are interacting with an AI assistant grounded in spiritual wisdom teachings. Responses do not replace human spiritual masters, mental health professionals, or medical practitioners.'
    },
    ...options
  };

  manifest.jsonLd = generateProvOJsonLd(manifest);
  return manifest;
}

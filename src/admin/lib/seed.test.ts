import { describe, it, expect } from 'vitest';
import { generateSeed } from './seed';

describe('generateSeed', () => {
  it('generates a valid SeedData object with expected collections', () => {
    const seed = generateSeed();
    
    // Check if the object has the expected keys
    expect(seed).toHaveProperty('prompt_versions');
    expect(seed).toHaveProperty('sessions');
    expect(seed).toHaveProperty('queries');
    expect(seed).toHaveProperty('retrievals');
    expect(seed).toHaveProperty('responses');
    expect(seed).toHaveProperty('spans');
    expect(seed).toHaveProperty('triggers');
    expect(seed).toHaveProperty('feedback');
    expect(seed).toHaveProperty('safety_events');
    expect(seed).toHaveProperty('golden_questions');
    expect(seed).toHaveProperty('eval_runs');
    expect(seed).toHaveProperty('eval_results');
    expect(seed).toHaveProperty('ingestion_runs');
    expect(seed).toHaveProperty('app_logs');
    expect(seed).toHaveProperty('model_pricing');
    expect(seed).toHaveProperty('query_clusters');
    expect(seed).toHaveProperty('alert_rules');
    expect(seed).toHaveProperty('alert_events');
    expect(seed).toHaveProperty('annotations');
    expect(seed).toHaveProperty('admins');
    
    // Ensure arrays are actually populated
    expect(Array.isArray(seed.prompt_versions)).toBe(true);
    expect(seed.prompt_versions.length).toBeGreaterThan(0);
    
    // Ensure admins are populated
    expect(Array.isArray(seed.admins)).toBe(true);
    expect(seed.admins.length).toBeGreaterThan(0);
  });
  
  it('generates consistent data structures', () => {
    const seed = generateSeed();
    const firstPrompt = seed.prompt_versions[0];
    
    expect(firstPrompt).toHaveProperty('id');
    expect(firstPrompt).toHaveProperty('name');
    expect(firstPrompt).toHaveProperty('version');
    expect(firstPrompt).toHaveProperty('content');
    expect(firstPrompt).toHaveProperty('active');
  });
});

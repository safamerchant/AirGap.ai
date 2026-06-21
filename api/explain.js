// api/explain.js — AirGap.ai LLM explanation route
// Uses Groq (Llama 3) via Vercel AI SDK.
// Caches results by action type+verdict for 5 min to prevent quota exhaustion.

import { createGroq } from '@ai-sdk/groq';
import { generateText } from 'ai';

// ── Simple in-memory cache (per serverless instance, ~5 min TTL) ─────────────
const cache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function cacheKey(action, verdict) {
  return `${action?.type}:${action?.target}:${verdict}`;
}

function fromCache(key) {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > CACHE_TTL) { cache.delete(key); return null; }
  return entry.data;
}

function toCache(key, data) {
  cache.set(key, { data, ts: Date.now() });
}

// ── Handler ───────────────────────────────────────────────────────────────────
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST')   return res.status(405).json({ error: 'Method not allowed' });

  const { action, verdict, reason } = req.body || {};

  // Fallback used when Groq is unavailable
  const fallback = {
    explanation: reason || 'This action was flagged by the AirGap policy engine.',
    recommendations: [
      'Review your current policy rules for this action type.',
      'Adjust budget thresholds if this action is expected behaviour.',
      'Add trusted targets to your allow-list to reduce false positives.'
    ]
  };

  if (!process.env.GROQ_API_KEY) {
    console.warn('[explain] GROQ_API_KEY not set — using fallback');
    return res.status(200).json(fallback);
  }

  // Return cached result if we've seen this action type + verdict before
  const key = cacheKey(action, verdict);
  const cached = fromCache(key);
  if (cached) {
    console.log('[explain] cache hit:', key);
    return res.status(200).json(cached);
  }

  try {
    const groq = createGroq({ apiKey: process.env.GROQ_API_KEY });

    const { text } = await generateText({
      model: groq('llama-3.1-8b-instant'),
      maxTokens: 350,
      prompt: `You are AirGap.ai, an AI agent safety system.
An agent action was intercepted. Verdict: ${verdict || 'BLOCK'}.

Action:
- Type: ${action?.type || 'unknown'}
- Target: ${action?.target || 'unknown'}
- Payload: ${JSON.stringify(action?.payload || {}).slice(0, 200)}
- Token cost: ${action?.tokens || 0}
- Rule triggered: ${reason || 'policy violation'}

Reply ONLY with a raw JSON object, no markdown, no extra text:
{
  "explanation": "2-3 sentences: what the agent tried, why AirGap blocked it, what could have gone wrong.",
  "recommendations": [
    "Concrete policy rule or config change to prevent this",
    "Budget or threshold adjustment to make",
    "Allow-list or deny-list entry to add"
  ]
}`
    });

    const clean = text.replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(clean);
    toCache(key, parsed); // cache for next time
    return res.status(200).json(parsed);

  } catch (err) {
    console.error('[explain] error:', err?.message);
    return res.status(200).json(fallback);
  }
}

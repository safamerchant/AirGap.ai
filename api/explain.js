// api/explain.js
// AirGap.ai — LLM explanation route
// Called when an agent action is intercepted (BLOCK or APPROVE verdict).
// Returns a plain-English explanation + 3 prevention recommendations.
// Falls back silently to the rule reason if Gemini is unavailable.

import { google } from '@ai-sdk/google';
import { generateText } from 'ai';

export default async function handler(req, res) {
  // ── CORS ──────────────────────────────────────────────────────────────────
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST')   return res.status(405).json({ error: 'Method not allowed' });

  // ── Parse body ────────────────────────────────────────────────────────────
  const { action, verdict, reason } = req.body || {};

  // ── Fallback (used when Gemini is unavailable or key is missing) ──────────
  const fallback = {
    explanation: reason || 'This action was flagged by the AirGap policy engine.',
    recommendations: [
      'Review your current policy rules for this action type.',
      'Adjust budget thresholds if this action is expected behaviour.',
      'Add trusted targets to your allow-list to reduce false positives.'
    ]
  };

  // If no API key is set, return fallback immediately (no crash, no error shown to user)
  if (!process.env.GOOGLE_GENERATIVE_AI_API_KEY) {
    console.warn('[explain] GOOGLE_GENERATIVE_AI_API_KEY not set — using fallback');
    return res.status(200).json(fallback);
  }

  // ── Call Gemini via Vercel AI SDK ─────────────────────────────────────────
  try {
    const { text } = await generateText({
      model: google('gemini-2.0-flash'),
      maxTokens: 350,
      prompt: `You are AirGap.ai, an autonomous AI agent safety system acting as a circuit breaker.
An agent action was intercepted and the verdict was: ${verdict || 'BLOCK'}.

Action details:
- Type: ${action?.type || 'unknown'}
- Target: ${action?.target || 'unknown'}
- Payload: ${JSON.stringify(action?.payload || {}).slice(0, 300)}
- Estimated token cost: ${action?.tokens || 0}
- Policy rule triggered: ${reason || 'policy violation'}

Reply ONLY with a raw JSON object — no markdown code fences, no text before or after the object:
{
  "explanation": "2-3 sentences in plain English. Describe what the agent tried to do, why AirGap blocked or flagged it, and what could have gone wrong if it wasn't caught.",
  "recommendations": [
    "One concrete policy rule or config change to prevent this in future",
    "One budget or threshold adjustment to consider",
    "One allow-list or deny-list entry to add"
  ]
}`
    });

    // Strip any accidental markdown fences and parse
    const clean = text.replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(clean);
    return res.status(200).json(parsed);

  } catch (err) {
    // Any error (network, parse, quota) → silent fallback, demo never breaks
    console.error('[explain] error:', err?.message);
    return res.status(200).json(fallback);
  }
}

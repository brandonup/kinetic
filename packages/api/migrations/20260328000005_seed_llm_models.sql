-- Seed: LLM model library
-- Source: llm_models.csv
-- context_window omitted — patch separately once values are confirmed.

INSERT INTO public.llm_models (provider, model_id, display_name, category, enabled)
VALUES
  -- Anthropic — generation
  ('anthropic', 'claude-opus-4-6',    'Claude Opus 4.6',    'generation', true),
  ('anthropic', 'claude-sonnet-4-6',  'Claude Sonnet 4.6',  'generation', true),
  ('anthropic', 'claude-sonnet-4-5',  'Claude Sonnet 4.5',  'generation', true),
  ('anthropic', 'claude-haiku-4-5',   'Claude Haiku 4.5',   'generation', true),
  ('anthropic', 'claude-opus-4-5',    'Claude Opus 4.5',    'generation', true),
  ('anthropic', 'claude-opus-4-1',    'Claude Opus 4.1',    'generation', true),
  ('anthropic', 'claude-sonnet-4-0',  'Claude Sonnet 4.0',  'generation', true),
  ('anthropic', 'claude-opus-4-0',    'Claude Opus 4.0',    'generation', true),
  -- Google — generation
  ('google', 'gemini-3.1-pro-preview',        'Gemini 3.1 Pro Preview',        'generation', true),
  ('google', 'gemini-3.1-flash-lite-preview', 'Gemini 3.1 Flash Lite Preview', 'generation', true),
  ('google', 'gemini-3-flash-preview',        'Gemini 3 Flash Preview',        'generation', true),
  ('google', 'gemini-2.5-pro',                'Gemini 2.5 Pro',                'generation', true),
  ('google', 'gemini-2.5-flash',              'Gemini 2.5 Flash',              'generation', true),
  ('google', 'gemini-2.5-flash-lite',         'Gemini 2.5 Flash Lite',         'generation', true),
  -- OpenAI — generation
  ('openai', 'gpt-5.4-pro',           'GPT-5.4 Pro',           'generation', true),
  ('openai', 'gpt-5.4',               'GPT-5.4',               'generation', true),
  ('openai', 'gpt-5.4-mini',          'GPT-5.4 Mini',          'generation', true),
  ('openai', 'gpt-5.4-nano',          'GPT-5.4 Nano',          'generation', true),
  ('openai', 'gpt-5.2-pro',           'GPT-5.2 Pro',           'generation', true),
  ('openai', 'gpt-5.2',               'GPT-5.2',               'generation', true),
  ('openai', 'gpt-5.1',               'GPT-5.1',               'generation', true),
  ('openai', 'gpt-5-pro',             'GPT-5 Pro',             'generation', true),
  ('openai', 'gpt-5',                 'GPT-5',                 'generation', true),
  ('openai', 'gpt-5-mini',            'GPT-5 Mini',            'generation', true),
  ('openai', 'gpt-5-nano',            'GPT-5 Nano',            'generation', true),
  ('openai', 'gpt-4.1',               'GPT-4.1',               'generation', true),
  ('openai', 'gpt-4.1-mini',          'GPT-4.1 Mini',          'generation', true),
  ('openai', 'gpt-4.1-nano',          'GPT-4.1 Nano',          'generation', true),
  ('openai', 'gpt-4o',                'GPT-4o',                'generation', true),
  ('openai', 'gpt-4o-mini',           'GPT-4o Mini',           'generation', true),
  ('openai', 'o4-mini',               'o4 Mini',               'generation', true),
  ('openai', 'o4-mini-2025-04-16',    'o4 Mini (2025-04-16)',  'generation', true),
  ('openai', 'o3-pro',                'o3 Pro',                'generation', true),
  ('openai', 'o3',                    'o3',                    'generation', true),
  ('openai', 'o3-2025-04-16',         'o3 (2025-04-16)',       'generation', true),
  ('openai', 'o3-mini',               'o3 Mini',               'generation', true),
  ('openai', 'o3-mini-2025-01-31',    'o3 Mini (2025-01-31)',  'generation', true),
  ('openai', 'o1-pro',                'o1 Pro',                'generation', true),
  ('openai', 'o1-pro-2025-03-19',     'o1 Pro (2025-03-19)',   'generation', true),
  ('openai', 'o1',                    'o1',                    'generation', true),
  ('openai', 'o1-2024-12-17',         'o1 (2024-12-17)',       'generation', true),
  -- Groq — generation
  ('groq', 'groq/compound',                                 'Compound',               'generation', true),
  ('groq', 'groq/compound-mini',                            'Compound Mini',          'generation', true),
  ('groq', 'llama-3.1-8b-instant',                          'Llama 3.1 8B Instant',   'generation', true),
  ('groq', 'llama-3.3-70b-versatile',                       'Llama 3.3 70B Versatile','generation', true),
  ('groq', 'meta-llama/llama-4-scout-17b-16e-instruct',     'Llama 4 Scout 17B',      'generation', true),
  ('groq', 'openai/gpt-oss-120b',                           'GPT OSS 120B',           'generation', true),
  ('groq', 'openai/gpt-oss-20b',                            'GPT OSS 20B',            'generation', true),
  ('groq', 'qwen/qwen3-32b',                                'Qwen3 32B',              'generation', true),
  -- OpenAI — embedding
  ('openai', 'text-embedding-3-large', 'Text Embedding 3 Large', 'embedding', true),
  ('openai', 'text-embedding-3-small', 'Text Embedding 3 Small', 'embedding', true),
  ('openai', 'text-embedding-ada-002', 'Text Embedding Ada 002', 'embedding', true),
  -- Cohere — reranking
  ('cohere', 'rerank-english-v3.0',      'Rerank English v3.0',      'reranking', true),
  ('cohere', 'rerank-multilingual-v3.0', 'Rerank Multilingual v3.0', 'reranking', true)
ON CONFLICT (model_id) DO NOTHING;

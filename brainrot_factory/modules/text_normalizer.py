"""
Text Normalizer — Pre-TTS text cleanup using Gemini via OpenRouter.

Handles:
1. Remove ASCII emoticons (:)), :>, xD, ...)
2. Expand Vietnamese teen abbreviations (t→tôi, a→anh, e→em, r→rồi, bvs→băng vệ sinh, ...)
3. Return clean, speakable Vietnamese text for TTS
"""

import os
import re

from loguru import logger

# ---------------------------------------------------------------------------
# Step 1: Regex — remove emoticons (fast, no API needed)
# ---------------------------------------------------------------------------

_EMOTICON_RE = re.compile(
    r'(?<!\w)'                       # not preceded by word char
    r'(?:'
    r'[:;=8][\-o\*\']?[\)\]\(\[dDpP/\:\}\{@\|\\]'  # standard :) ;) :D etc
    r'|[\)\]\(\[dDpP/\:\}\{@\|\\][\-o\*\']?[:;=8]'  # reversed )):
    r'|<3|</3|>\.<|>_<|:v|=\)+'      # misc
    r'|x[dD]+'                        # xD, xDD
    r'|(?::\)+){2,}'                  # :))) repeated
    r'|\)+:{1}'                       # )):
    r'|:{1}\)+(?!\w)'                 # :))
    r')'
    r'(?!\w)',
    re.IGNORECASE,
)

_MULTI_PAREN_RE = re.compile(r'(?<!\w)\)+(?!\w)')   # standalone ))) leftover


def _strip_emoticons(text: str) -> str:
    text = _EMOTICON_RE.sub('', text)
    text = _MULTI_PAREN_RE.sub('', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


# ---------------------------------------------------------------------------
# Step 2: Regex — expand common Vietnamese teen abbreviations
# ---------------------------------------------------------------------------

# Order matters: longer/more-specific first to avoid partial replacement
_ABBREV_MAP = [
    # Pronouns (context-sensitive — single letter surrounded by spaces)
    (r'\bt\b', 'tôi'),
    (r'\bmk\b', 'mình'),
    (r'\bm\b', 'mình'),
    (r'\ba\b', 'anh'),
    (r'\be\b', 'em'),
    (r'\bc\b', 'chị'),
    (r'\bmn\b', 'mọi người'),
    (r'\bbn\b', 'bạn'),
    # Common words
    (r'\btrc\b', 'trước'),
    (r'\bsau\b', 'sau'),         # already full word, skip
    (r'\br\b', 'rồi'),
    (r'\bk\b', 'không'),
    (r'\bko\b', 'không'),
    (r'\bkg\b', 'không'),
    (r'\bđc\b', 'được'),
    (r'\bdc\b', 'được'),
    (r'\bvs\b', 'với'),
    (r'\bntn\b', 'như thế nào'),
    (r'\bnt\b', 'nhắn tin'),
    (r'\bib\b', 'nhắn tin'),
    (r'\bck\b', 'chồng'),
    (r'\bvk\b', 'vợ'),
    (r'\bbf\b', 'bạn trai'),
    (r'\bgf\b', 'bạn gái'),
    (r'\bbtw\b', 'nhân tiện'),
    # Products / internet slang
    (r'\bbvs\b', 'băng vệ sinh'),
    (r'\bomg\b', 'ôi trời'),
    (r'\bwtf\b', 'ôi trời'),
    (r'\blol\b', 'haha'),
    (r'\bhmu\b', 'liên hệ mình'),
]

_ABBREV_RE = [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in _ABBREV_MAP]


def _expand_abbreviations(text: str) -> str:
    for pattern, replacement in _ABBREV_RE:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Step 3: OpenRouter LLM — expand remaining abbreviations (optional)
# ---------------------------------------------------------------------------

_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
_MODELS = [
    # Large, multilingual — best for Vietnamese (try these first)
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "openai/gpt-oss-120b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "google/gemma-3-12b-it:free",
]

_SYSTEM_PROMPT = """Bạn là công cụ chuẩn hoá văn bản tiếng Việt trước khi đưa vào TTS (text-to-speech).

Nhiệm vụ:
1. Mở rộng các từ viết tắt teen Việt thành dạng đầy đủ để TTS đọc đúng.
   Ví dụ: t → tôi, a → anh, e → em, c → chị, m → mình, mk → mình, mn → mọi người,
   r → rồi, k/ko/kg → không, đc → được, vs → với, trc → trước, sau → sau,
   bvs → băng vệ sinh, ib → inbox, dm → nhắn tin, ntn → như thế nào,
   vl → vãi, ck → chồng, vk/vợ → vợ, bf → bạn trai, gf → bạn gái,
   hmu → liên hệ mình, lol → cười, omg → ôi trời, wtf → ôi trời,
   shipper → người giao hàng (giữ nguyên nếu phổ biến),
   shop → shop (giữ nguyên), app → ứng dụng.
2. Xóa hoặc thay thế các ký tự emoticon ASCII còn sót (:), :D, xD, ...).
3. GIỮ NGUYÊN từ ngữ, ý nghĩa, cảm xúc — chỉ làm sạch và mở rộng viết tắt.
4. Trả về DUY NHẤT văn bản đã chuẩn hoá, không giải thích, không thêm gì khác."""


def _normalize_batch_with_ai(texts: list[str]) -> list[str]:
    """
    Batch normalize multiple texts in a single API call.
    Tries each model in _MODELS until one succeeds (handles rate limits).
    """
    if not _OPENROUTER_KEY:
        logger.warning("OPENROUTER_API_KEY not set — skipping AI normalization")
        return texts

    from openai import OpenAI
    client = OpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    user_prompt = f"Chuẩn hoá các dòng sau (giữ nguyên thứ tự và số thứ tự):\n{numbered}"
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    for model in _MODELS:
        try:
            response = client.chat.completions.create(
                model=model, messages=messages, max_tokens=1024, temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()
            results = []
            for line in raw.splitlines():
                cleaned = re.sub(r'^\d+\.\s*', '', line.strip())
                if cleaned:
                    results.append(cleaned)
            if len(results) == len(texts):
                logger.info(f"Text normalized via {model}")
                return results
            else:
                logger.warning(f"{model}: returned {len(results)}/{len(texts)} lines — trying next model")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                logger.debug(f"{model} rate-limited, trying next...")
            else:
                logger.warning(f"{model} failed: {e}")

    logger.warning("All models failed — using original texts")
    return texts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize(text: str, use_ai: bool = True) -> str:
    """
    Full normalization:
    1. Strip emoticons (regex)
    2. Expand abbreviations (regex — fast, reliable)
    3. AI polish for remaining edge cases (optional, skipped if rate-limited)
    """
    text = _strip_emoticons(text)
    text = _expand_abbreviations(text)
    if use_ai:
        [text] = _normalize_batch_with_ai([text])
    return text.strip()


def normalize_batch(texts: list[str], use_ai: bool = True) -> list[str]:
    """
    Normalize a list of texts efficiently.
    1. Strip emoticons (regex, per item)
    2. Expand abbreviations (regex, per item)
    3. AI polish for all items in ONE API call (skipped gracefully if rate-limited)
    """
    texts = [_expand_abbreviations(_strip_emoticons(t)) for t in texts]
    if use_ai:
        texts = _normalize_batch_with_ai(texts)
    return [t.strip() for t in texts]

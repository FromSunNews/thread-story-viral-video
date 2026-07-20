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
    # --- TTS pronunciation fixes (multi-word phrases, must come first) ---
    (r'\bDm\b', 'Định mệnh'),          # sentence-start Dm = expletive/fate (uppercase D)

    # --- Longer/more-specific patterns first ---
    (r'\bkphai\b', 'không phải'),
    (r'\bkbh\b', 'không bao giờ'),
    (r'\bkbao\b', 'không bao giờ'),
    (r'\bnhma\b', 'nhưng mà'),
    (r'\bnmk\b', 'nhưng mà'),
    (r'\bnma\b', 'nhưng mà'),
    (r'\bnm\b', 'nhưng mà'),
    (r'\bntd\b', 'nói thật đó'),
    (r'\bntn\b', 'như thế nào'),
    (r'\bmqh\b', 'mối quan hệ'),
    (r'\bctct\b', 'và các thứ khác'),
    (r'\bctg\b', 'và những thứ'),
    (r'\bvvv\b', 'và vân vân'),
    (r'\bkhum\b', 'không'),
    (r'\bbgio\b', 'bây giờ'),
    (r'\bbgio\b', 'bây giờ'),
    (r'\bhmu\b', 'liên hệ mình'),
    (r'\bidk\b', 'không biết'),
    (r'\bngl\b', 'nói thật là'),
    (r'\bnvl\b', 'nghe vãi'),
    (r'\bbtw\b', 'nhân tiện'),
    (r'\bpov\b', 'góc nhìn của'),
    (r'\bimo\b', 'theo mình'),
    (r'\bvcl\b', 'vãi'),
    (r'\bvkl\b', 'vãi'),
    (r'\bomg\b', 'ôi trời'),
    (r'\bwtf\b', 'ôi trời'),
    (r'\blol\b', 'haha'),
    (r'\blmao\b', ''),
    (r'\bbvs\b', 'băng vệ sinh'),

    # --- Pronouns ---
    (r'\bmng\b', 'mọi người'),
    (r'\bmn\b', 'mọi người'),
    (r'\bmk\b', 'mình'),
    (r'\bbn\b', 'bạn'),
    (r'\bng\b', 'người'),
    (r'\bae\b', 'anh em'),

    # --- Negation / core words (longer first) ---
    (r'\bkông\b', 'không'),
    (r'\bkhg\b', 'không'),
    (r'\bkp\b', 'không phải'),
    (r'\bkg\b', 'không'),
    (r'\bkh\b', 'không'),
    (r'\bko\b', 'không'),
    (r'\bkc\b', 'không có'),
    (r'\bkco\b', 'không có'),
    (r'\bkb\b', 'không biết'),
    (r'\bkq\b', 'kết quả'),

    # --- Common short verbs / words ---
    (r'\bđc\b', 'được'),
    (r'\bdc\b', 'được'),
    (r'\bdk\b', 'được'),
    (r'\btrc\b', 'trước'),
    (r'\bvs\b', 'với'),
    (r'\bnma\b', 'nhưng mà'),
    (r'\brr\b', 'rồi rồi'),
    (r'\bnr\b', 'nhà rồi'),
    (r'\bbt\b', 'bình thường'),
    (r'\bbth\b', 'bình thường'),
    (r'\bbthuong\b', 'bình thường'),
    (r'\bhqua\b', 'hôm qua'),
    (r'\bhna\b', 'hôm nay'),
    (r'\bms\b', 'mới'),
    (r'\bmh\b', 'mình'),
    (r'\bvay\b', 'vậy'),
    (r'\bna\b', 'nha'),
    (r'\biz\b', 'vậy'),
    (r'\bxog\b', 'xong'),
    (r'\btx\b', 'thường xuyên'),
    (r'\bntin\b', 'nhắn tin'),
    (r'\bnt\b', 'nhắn tin'),
    (r'\bib\b', 'nhắn tin'),
    (r'\bdm\b', 'Định mệnh'),
    (r'\bdjt\b', 'địt'),
    (r'\bfr\b', 'thật ra'),
    (r'\bty\b', 'cảm ơn'),
    (r'\bthank\b', 'cảm ơn'),
    (r'\bck\b', 'chuyển khoản'),
    (r'\bvk\b', 'vợ'),
    (r'\bbf\b', 'bạn trai'),
    (r'\bgf\b', 'bạn gái'),
    (r'\blz\b', 'lười'),
    (r'\bvl\b', 'vãi'),
    (r'\bvc\b', 'vãi'),
    (r'\bttoan\b', 'thanh toán'),

    # --- School / class ---
    (r'\blp(\d)\b', r'lớp \1'),    # lp1→lớp 1, lp2→lớp 2
    (r'\blp\b', 'lớp'),
    (r'\bcp\b', 'cấp'),

    # --- Compound abbreviations common in teen chat ---
    (r'\bsao\b', 'sao'),           # already full
    (r'\bsr\b', 'xin lỗi'),
    (r'\bsorry\b', 'xin lỗi'),
    (r'\btrl\b', 'trả lời'),
    (r'\brep\b', 'trả lời'),
    (r'\breply\b', 'trả lời'),
    (r'\bnc\b', 'nước'),
    (r'\bcmt\b', 'bình luận'),
    (r'\bcmt\b', 'bình luận'),
    (r'\blike\b', 'thích'),
    (r'\bshare\b', 'chia sẻ'),
    (r'\bpost\b', 'bài viết'),
    (r'\bstory\b', 'tin'),
    (r'\bfollow\b', 'theo dõi'),
    (r'\bunfollow\b', 'bỏ theo dõi'),
    (r'\bblock\b', 'chặn'),

    # --- Abbreviated compound words ---
    (r'\bcgai\b', 'con gái'),
    (r'\bctrai\b', 'con trai'),
    (r'\bcno\b', 'chúng nó'),
    (r'\bcai\b', 'con ai'),
    (r'\bbff\b', 'bạn thân'),
    (r'\bfam\b', 'gia đình'),
    (r'\bnyc\b', 'người yêu cũ'),
    (r'\bthg\b', 'thằng'),
    (r'\btrg\b', 'trường'),
    (r'\bwc\b', 'nhà vệ sinh'),
    (r'\bô\b', 'ông'),

    # --- Single-letter pronouns (last — most ambiguous) ---
    (r'\bt\b', 'tôi'),
    (r'\bmk\b', 'mình'),
    (r'\bm\b', 'mình'),
    (r'\ba\b', 'anh'),
    (r'\be\b', 'em'),
    (r'\bc\b', 'chị'),
    (r'\bb\b', 'bạn'),
    (r'\bu\b', 'ừ'),
    (r'\buh\b', 'ừ'),

    # --- Single letters that are words ---
    (r'\br\b', 'rồi'),
    (r'\bro\b', 'rồi'),
    (r'\bv\b', 'vậy'),
    (r'\bh\b', 'giờ'),
    (r'\bhn\b', 'hôm nay'),
    (r'\bbh\b', 'bây giờ'),
    (r'\bgio\b', 'giờ'),
    (r'\bk\b', 'không'),
    (r'\bcn\b', 'còn'),
    (r'\bcg\b', 'cũng'),
    (r'\bcx\b', 'cũng'),
    (r'\bth\b', 'thôi'),
    (r'\bổ\b', 'ổng'),
    (r'\bí\b', 'ấy'),
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
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "google/gemma-3-4b-it:free",
    "microsoft/phi-4:free",
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

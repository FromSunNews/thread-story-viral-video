"""
Emotion Classifier — Community Reaction Classifier for Vietnamese Comments

Given a comment text, returns the top-k emotions representing how the
Vietnamese online community (cộng đồng mạng) would REACT to that comment.

e.g. "mẹ bắt học từ 0h đến 7h sáng" → [dong_tinh, la_len_giai_toa, xuc_dong]
e.g. "tôi bị gay" → [joke_gay, mac_cuoi, kho_tin]

Three layers:
  Layer 1: Regex / pattern matching (fast, high-precision for clear cases)
  Layer 2: Keyword scoring (weighted vote per emotion)
  Layer 3: LLM via OpenRouter (best accuracy, used when layers 1+2 tie/unclear)
"""

import os
import re
import random
from pathlib import Path
from loguru import logger


# ---------------------------------------------------------------------------
# All valid emotions (must match folder names in assets/memes_emotions/)
# ---------------------------------------------------------------------------

EMOTIONS: list[str] = [
    # Hài / Comedy
    "mac_cuoi", "joke_gay", "joke_do_mixi", "chem_gio", "lo_lang",
    "ngo_ngan", "dap_lai", "lua_dao",

    # Shock / Bất ngờ
    "ngac_nhien", "kho_tin", "khong_tin", "soc_nang", "plot_twist",

    # Tiêu cực
    "tuc_gian", "that_vong", "ghe_tom", "buon_dau_long", "so_hai",
    "hoi_han", "ghen_ty", "co_don", "bi_phan_bon", "noi_oan",
    "bat_luc", "bi_that_bai", "roi_loan", "mat_binh_tinh",
    "qua_quat", "kich_dong", "tuyet_vong", "oan_uc", "noi_kho",
    "yeu_duoi", "cang_thang", "bi_hieu_lam",

    # Tích cực
    "nguong_mo", "tu_hao", "am_long", "phan_khich", "cool_ngau",
    "W_moment", "ho_hoi", "dung_cam", "lam_chu", "manh_me",
    "hy_vong", "xuc_dong",

    # Tư duy / Phân tích
    "thong_minh", "khuyen_bao", "dong_tinh", "ngo_ra", "tinh_te",
    "L_take",

    # Xã hội / Social
    "hong_hot", "la_len_giai_toa", "kho_hieu", "awkward",
    "xau_ho", "flex", "thuong_xot", "benh_vuc",
    "crush_ngo_ngan", "thach_thuc",

    # Internet / Gen Z
    "down_bad", "delulu", "npc", "sigma", "rizz",
    "len_mat", "tiet_lo", "noi_ngoa",

    # Thái độ
    "gia_vo", "binh_than", "khong_quan_tam", "bao_thu",
    "giu_binh_tinh", "nham_mat", "buong_bo",

    # Quan hệ / Memory
    "nho_nhung", "qua_khu", "tim_hieu", "lien_quan",

    # Misc
    "lo_xa", "thoai_mai",
]

EMOTIONS_SET = set(EMOTIONS)


# ---------------------------------------------------------------------------
# Layer 1: Hard patterns (regex) — highest priority
# ---------------------------------------------------------------------------

# List of (pattern, emotion, weight) — first match wins for that emotion
_HARD_PATTERNS: list[tuple] = [
    # joke_gay — explicit gay content
    (r'\b(gay|đồng tính|thích con trai|lgbt|truyện gay|bị gay|là gay|anh con trai)\b', "joke_gay", 3),
    (r'\b(thằng|con trai).{0,30}(yêu|thích|địt|đụ).{0,30}(thằng|con trai)\b', "joke_gay", 3),

    # joke_do_mixi — absurd illogical action
    (r'nên (tôi|t|mình|mk).{0,50}(trong lớp|tại chỗ|ngay đó|luôn)', "joke_do_mixi", 2),
    (r'(ngồi|đứng|nằm).{0,20}(ỉa|tè|khóc|cười).{0,20}(lớp|trường|chỗ làm)', "joke_do_mixi", 3),

    # la_len_giai_toa — all caps or repeated punctuation = venting
    (r'[A-ZÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝ]{6,}', "la_len_giai_toa", 2),
    (r'[!]{3,}', "la_len_giai_toa", 2),
    (r'(ấm ức|bức xúc|uất ức|tức điên|giải toả)', "la_len_giai_toa", 2),

    # soc_nang — heavy shock
    (r'(không thể tin|không thể ngờ|sốc toàn tập|choáng váng|đứng hình|trời đất ơi)', "soc_nang", 2),

    # down_bad — simp/hopeless romantic
    (r'(crush|người yêu).{0,40}(không biết|không hay|không thích lại|thích mình không)', "down_bad", 2),
    (r'(nhìn mình là thích mình|nó cười với tao là)', "delulu", 2),

    # plot_twist
    (r'(nhưng mà|nhưng|kết quả là|thì ra|hoá ra|ai ngờ).{0,60}(không ai ngờ|bất ngờ|lại là)', "plot_twist", 2),

    # lua_dao — scam
    (r'(bị lừa|lừa đảo|mất tiền|scam|lấy mất|giả mạo)', "lua_dao", 3),

    # tiet_lo — exposing/revealing
    (r'(tiết lộ|lộ ra|bí mật|expose|reveal|thật ra là)', "tiet_lo", 2),

    # flex — real impressive numbers
    (r'(\d+)\s*(đề|bài tập|câu|km|km/h|triệu|tỷ|kg|tiếng đồng hồ|giờ liên tục)', "flex", 1),

    # thong_minh — smart/galaxy brain
    (r'(làm \d+ đề|giải \d+|học \d+ tiếng|\d+ đề toán)', "thong_minh", 2),
]

_HARD_RE = [(re.compile(pat, re.IGNORECASE | re.UNICODE), emo, w) for pat, emo, w in _HARD_PATTERNS]


# ---------------------------------------------------------------------------
# Layer 2: Keyword scoring map
# ---------------------------------------------------------------------------

# Format: emotion → list of (keyword/phrase, weight)
_KEYWORD_MAP: dict[str, list[tuple[str, float]]] = {

    # ── Hài ──────────────────────────────────────────────────────────────
    "mac_cuoi": [
        ("haha", 2), ("hihi", 2), ("hehe", 2), ("lol", 2), ("lmao", 2),
        ("buồn cười", 3), ("mắc cười", 3), ("cười không nhịn", 3),
        ("vãi", 2), ("vl", 1), ("ngộ vl", 2), (":))", 1), ("xD", 2),
        ("funny", 1), ("hài vl", 3), ("cười xỉu", 3),
    ],
    "joke_gay": [
        ("gay", 3), ("đồng tính", 3), ("lgbt", 2), ("truyện gay", 3),
        ("bị gay", 3), ("là gay", 3), ("thích con trai", 2),
        ("anh con trai khác", 2), ("mình thẳng", 2),
    ],
    "joke_do_mixi": [
        ("ngồi ỉa trong", 3), ("nên tôi", 1), ("nên mình", 1),
        ("vì vậy tôi", 1), ("thế là tôi", 1), ("kết quả", 1),
        ("phi logic", 2), ("vô lý mà hợp lý", 2), ("absurd", 2),
    ],
    "chem_gio": [
        ("chém gió", 3), ("bốc phét", 3), ("nói phét", 3), ("fake", 2),
        ("ai tin", 1), ("bịa", 2), ("tưởng tượng", 1), ("ảo tưởng", 2),
    ],
    "lo_lang": [
        ("drama", 2), ("overdramatic", 2), ("diễn", 2), ("lố", 2),
        ("thái quá", 2), ("cringe", 3), ("ngượng", 1),
    ],
    "ngo_ngan": [
        ("ngố", 3), ("ngốc", 2), ("cute", 1), ("đáng yêu", 1),
        ("vô tư", 1), ("hồn nhiên", 2), ("không biết gì", 1),
    ],
    "dap_lai": [
        ("sai rồi", 2), ("thật ra", 1), ("thực tế là", 2),
        ("clapback", 2), ("phản bác", 2), ("comeback", 2), ("đáp lại", 2),
    ],
    "lua_dao": [
        ("bị lừa", 3), ("lừa đảo", 3), ("scam", 3), ("mất tiền", 2),
        ("lấy mất", 2), ("giả mạo", 2), ("không nhận được", 1),
    ],

    # ── Shock ────────────────────────────────────────────────────────────
    "ngac_nhien": [
        ("bất ngờ", 2), ("không ngờ", 2), ("ngạc nhiên", 2), ("ủa", 1),
        ("sao vậy", 1), ("ồ", 1), ("wow", 2), ("omg", 2), ("ôi trời", 1),
    ],
    "kho_tin": [
        ("thật không", 2), ("thật hả", 2), ("khó tin", 3), ("ơ kìa", 2),
        ("không thể tin", 3), ("có thật không", 3), ("sao được", 2),
        ("thật sự à", 2),
    ],
    "khong_tin": [
        ("bịa", 3), ("không tin", 2), ("fake", 2), ("vô lý", 2),
        ("impossible", 2), ("chắc bịa", 3), ("không có thật", 3),
        ("ai tin cái này", 3),
    ],
    "soc_nang": [
        ("sốc", 2), ("choáng", 2), ("đứng hình", 2), ("trời đất", 2),
        ("sốc toàn tập", 3), ("không thể ngờ", 2), ("choáng váng", 3),
        ("bàng hoàng", 3),
    ],
    "plot_twist": [
        ("hoá ra", 3), ("thì ra", 3), ("ai ngờ", 2), ("không ai ngờ", 3),
        ("nhưng mà thật ra", 2), ("kết quả bất ngờ", 3), ("twist", 2),
        ("thật ra", 2), ("mà không biết", 3), ("từ lâu mà", 3),
        ("đã thích từ lâu", 3), ("ai ngờ lại", 3),
    ],

    # ── Tiêu cực ─────────────────────────────────────────────────────────
    "tuc_gian": [
        ("tức", 2), ("điên", 2), ("ghét", 2), ("ức chế", 3),
        ("thật sự tức", 3), ("bực mình", 2), ("rage", 2), ("tức chết",3),
        ("tức điên", 3), ("muốn đập", 2),
    ],
    "that_vong": [
        ("thất vọng", 3), ("tưởng tốt hơn", 2), ("mong là", 1),
        ("hy vọng mà", 1), ("disappointed", 2), ("buồn kiểu", 2),
        ("tiếc quá", 1),
    ],
    "ghe_tom": [
        ("ghê", 2), ("kinh", 2), ("tởm", 3), ("ghê tởm", 3), ("eww", 3),
        ("kinh quá", 3), ("disgusting", 2), ("bẩn", 1), ("ô nhiễm", 1),
    ],
    "buon_dau_long": [
        ("buồn", 2), ("đau lòng", 3), ("khóc", 2), ("tội nghiệp", 2),
        ("thương quá", 2), ("sad", 2), ("heartbroken", 2), ("đau", 1),
        ("nước mắt", 2), ("rớt nước mắt", 3),
    ],
    "so_hai": [
        ("sợ", 2), ("rùng mình", 2), ("sởn gai ốc", 3), ("kinh dị", 2),
        ("ám ảnh", 2), ("đừng nói nữa", 2), ("scared", 2), ("horror", 2),
    ],
    "hoi_han": [
        ("hối hận", 3), ("tiếc", 2), ("giá mà", 3), ("ước gì", 2),
        ("nếu lúc đó", 2), ("sai rồi mới biết", 2), ("regret", 2),
    ],
    "ghen_ty": [
        ("ghen tị", 3), ("ghen", 2), ("sao người ta", 2), ("jealous", 2),
        ("sao nó được", 2), ("tại sao không phải mình", 2), ("envy", 2),
    ],
    "co_don": [
        ("cô đơn", 3), ("một mình", 2), ("không ai", 2), ("lonely", 2),
        ("không có bạn", 2), ("ngồi một mình", 2), ("alone", 2),
    ],
    "bi_phan_bon": [
        ("phản bội", 3), ("bán đứng", 3), ("tưởng tin tưởng", 2),
        ("backstab", 2), ("bạn cũ", 1), ("người thân hại", 2),
    ],
    "noi_oan": [
        ("oan", 3), ("không có làm", 2), ("bị đổ tội", 3),
        ("sao đổ tội", 2), ("tôi không có", 2), ("oan uổng", 3),
    ],
    "bat_luc": [
        ("bất lực", 3), ("biết làm gì", 2), ("không biết phải làm sao", 3),
        ("chịu rồi", 2), ("bó tay", 3), ("helpless", 2), ("thua rồi", 2),
    ],
    "bi_that_bai": [
        ("thất bại", 3), ("thua", 2), ("không được", 1), ("fail", 2),
        ("hỏng rồi", 2), ("trượt", 2), ("rớt", 2), ("L", 1),
    ],
    "roi_loan": [
        ("rối loạn", 3), ("hỗn loạn", 2), ("chaos", 2), ("loạn xạ", 2),
        ("không kiểm soát", 2), ("mọi thứ vỡ vụn", 2),
    ],
    "mat_binh_tinh": [
        ("mất bình tĩnh", 3), ("điên lên", 2), ("không kiềm được", 2),
        ("bùng", 2), ("nổi khùng", 2), ("snap", 2), ("explode", 2),
    ],
    "qua_quat": [
        ("quá quắt", 3), ("thái độ", 2), ("không thể chấp nhận", 3),
        ("vô đạo đức", 2), ("outrageous", 2), ("unacceptable", 2),
    ],
    "kich_dong": [
        ("kích động", 3), ("triggered", 2), ("dễ tức", 2),
        ("nhạy cảm", 1), ("nhảy vào", 1), ("công kích", 2),
    ],
    "tuyet_vong": [
        ("tuyệt vọng", 3), ("hết hi vọng", 3), ("không còn gì", 2),
        ("buông xuôi", 2), ("vô vọng", 3), ("hopeless", 2),
    ],
    "oan_uc": [
        ("ấm ức", 3), ("uất ức", 3), ("không giải thích được", 2),
        ("nghẹn lòng", 2), ("nuốt không trôi", 2),
    ],
    "noi_kho": [
        ("kể khổ", 2), ("khổ lắm", 2), ("cực lắm", 2), ("vất vả", 2),
        ("chịu đựng", 1), ("gian khổ", 2), ("mệt mỏi", 1),
    ],
    "yeu_duoi": [
        ("yếu đuối", 3), ("không đủ mạnh", 2), ("sụp đổ", 2),
        ("break down", 2), ("không chịu được nữa", 3), ("vulnerable", 2),
    ],
    "cang_thang": [
        ("căng thẳng", 3), ("stress", 2), ("áp lực", 2), ("lo lắng", 1),
        ("anxiety", 2), ("deadline", 1), ("ngộp", 2),
    ],
    "bi_hieu_lam": [
        ("bị hiểu lầm", 3), ("không phải ý đó", 3), ("hiểu sai rồi", 2),
        ("ý tôi là", 1), ("misunderstood", 2), ("không có nghĩa vậy", 2),
    ],

    # ── Tích cực ─────────────────────────────────────────────────────────
    "nguong_mo": [
        ("ngưỡng mộ", 3), ("nể", 2), ("respect", 2), ("giỏi quá", 2),
        ("tuyệt vời", 2), ("phi thường", 3), ("đỉnh", 2), ("xịn", 1),
    ],
    "tu_hao": [
        ("tự hào", 3), ("proud", 2), ("thành tích", 1), ("giỏi ghê", 2),
        ("con nhà người ta", 2), ("gương sáng", 2),
    ],
    "am_long": [
        ("ấm lòng", 3), ("ấm áp", 2), ("heartwarming", 2), ("dễ thương", 1),
        ("cảm động", 2), ("tốt bụng", 2), ("tử tế", 2),
    ],
    "phan_khich": [
        ("phấn khích", 3), ("hype", 2), ("excited", 2), ("xịn sò", 2),
        ("quá đỉnh", 2), ("YESSS", 3), ("không thể chờ", 2), ("đỉnh của đỉnh", 3),
    ],
    "cool_ngau": [
        ("ngầu", 2), ("cool", 2), ("badass", 2), ("liều", 1),
        ("không ngại", 1), ("chất", 2), ("xịn ngầu", 3),
    ],
    "W_moment": [
        ("win", 2), ("thắng", 1), ("đỉnh", 1), ("W", 1),
        ("chiến thắng", 2), ("làm được", 1), ("xong rồi", 1),
    ],
    "ho_hoi": [
        ("háo hởi", 2), ("háo hức", 2), ("eager", 2), ("không thể chờ", 2),
        ("mong quá", 2), ("sắp rồi", 1), ("counting down", 2),
    ],
    "dung_cam": [
        ("dũng cảm", 3), ("can đảm", 2), ("dám", 2), ("brave", 2),
        ("không sợ", 1), ("đối mặt", 1), ("vượt qua", 1),
    ],
    "lam_chu": [
        ("làm chủ", 2), ("boss", 2), ("chủ động", 1), ("kiểm soát", 1),
        ("in control", 2), ("leader", 1),
    ],
    "manh_me": [
        ("mạnh mẽ", 3), ("strong", 2), ("kiên định", 2), ("không gục ngã", 2),
        ("đứng dậy", 1), ("vượt khó", 2),
    ],
    "hy_vong": [
        ("hy vọng", 3), ("mong", 1), ("biết đâu", 1), ("lần này", 1),
        ("hopeful", 2), ("maybe", 1), ("có thể được", 1),
    ],
    "xuc_dong": [
        ("xúc động", 3), ("cảm động", 3), ("nghẹn ngào", 3),
        ("rớt nước mắt", 3), ("muốn khóc", 2), ("touching", 2),
        ("chạm lòng", 3), ("thấm", 2),
    ],

    # ── Tư duy ───────────────────────────────────────────────────────────
    "thong_minh": [
        ("thông minh", 2), ("tài giỏi", 2), ("genius", 2), ("galaxy brain", 2),
        ("đỉnh cao trí tuệ", 3), ("không phải người thường", 2),
        ("pro", 1), ("xuất sắc", 2),
    ],
    "khuyen_bao": [
        ("nên", 1), ("hãy", 1), ("đừng", 1), ("khuyên", 2),
        ("theo mình", 2), ("mình nghĩ bạn nên", 3), ("lời khuyên", 2),
        ("tốt nhất là", 2),
    ],
    "dong_tinh": [
        ("tôi cũng", 2), ("tao cũng", 2), ("y chang", 3), ("giống tao", 3),
        ("relatable", 3), ("đúng quá", 2), ("đồng ý", 2), ("tôi cũng vậy", 3),
        ("nghe quen", 2), ("tôi đây", 2),
        # học đêm / bị ép → community đồng cảm
        ("bắt học", 2), ("ép học", 2), ("học từ", 1), ("học đến", 1),
        ("học suốt", 2), ("thức đêm", 2), ("0h", 2), ("1h sáng", 2),
        ("2h sáng", 2), ("3h sáng", 2), ("bị mẹ", 1), ("bị ba", 1),
    ],
    "ngo_ra": [
        ("ra là", 2), ("à ra thế", 3), ("hiểu rồi", 2), ("aha", 2),
        ("eureka", 2), ("mới hiểu", 2), ("thì ra vậy", 3),
    ],
    "tinh_te": [
        ("tinh tế", 3), ("sâu sắc", 2), ("nhận xét hay", 2),
        ("insight", 2), ("nhìn ra", 1), ("để ý", 1), ("subtle", 2),
    ],
    "L_take": [
        ("sai hoàn toàn", 3), ("take tệ", 3), ("bad take", 3),
        ("ý kiến tệ", 3), ("nhầm rồi", 2), ("quan điểm sai", 3),
        ("phát biểu sai", 3), ("nói sai", 2),
    ],

    # ── Xã hội ───────────────────────────────────────────────────────────
    "hong_hot": [
        ("tiếp đi", 2), ("kể tiếp", 2), ("phần 2 đâu", 3),
        ("tò mò", 2), ("cần biết thêm", 2), ("drama", 1), ("hóng", 2),
        ("bắp rang đã sẵn sàng", 3),
    ],
    "la_len_giai_toa": [
        ("ấm ức", 3), ("bức xúc", 3), ("giải toả", 2), ("xả stress", 2),
        ("la hét", 2), ("muốn hét", 2), ("venting", 2), ("la to", 2),
    ],
    "kho_hieu": [
        ("không hiểu", 2), ("sao vậy", 2), ("???", 2), ("hả", 1),
        ("ý là sao", 2), ("giải thích đi", 2), ("confused", 2), ("huh", 2),
    ],
    "awkward": [
        ("awkward", 3), ("kỳ cục", 2), ("im lặng", 1), ("ngại", 2),
        ("khó xử", 2), ("embarrassing", 2), ("tình huống kỳ lạ", 2),
    ],
    "xau_ho": [
        ("xấu hổ", 3), ("ngượng", 2), ("muốn độn thổ", 3),
        ("đừng nhắc", 2), ("không dám nhìn", 2), ("shame", 2),
    ],
    "flex": [
        ("flex", 2), ("khoe", 2), ("tự hào vì", 1), ("đạt được", 1),
        ("làm được", 1), ("thành tích của tôi", 2), ("nhìn tao nè", 2),
    ],
    "thuong_xot": [
        ("tội nghiệp", 3), ("thương quá", 3), ("đáng thương", 3),
        ("khổ quá", 2), ("tội", 2), ("sympathy", 2), ("poor thing", 2),
    ],
    "benh_vuc": [
        ("bênh", 2), ("không phải lỗi của", 2), ("để tôi nói", 2),
        ("defend", 2), ("bảo vệ", 2), ("đứng về phía", 2),
    ],
    "crush_ngo_ngan": [
        ("crush", 2), ("thích ai đó", 1), ("người thích", 1),
        ("tỏ tình", 2), ("nói chuyện với crush", 2), ("nhìn trộm", 2),
        ("tim đập loạn", 2),
    ],
    "thach_thuc": [
        ("dám không", 2), ("thử xem", 1), ("challenge", 2),
        ("thách thức", 2), ("ai dám", 2), ("làm được không", 1),
    ],

    # ── Internet / Gen Z ─────────────────────────────────────────────────
    "down_bad": [
        ("down bad", 3), ("simp", 2), ("không được đáp lại", 2),
        ("thích mà không được", 3), ("một chiều", 2), ("unrequited", 2),
    ],
    "delulu": [
        ("delulu", 3), ("ảo tưởng", 3), ("tự sướng", 2),
        ("chắc thích mình", 2), ("nó nhìn mình là thích", 3),
        ("sống trong ảo tưởng", 3),
    ],
    "npc": [
        ("npc", 3), ("follow trend", 2), ("sheep", 2),
        ("không có não", 2), ("robot", 1), ("không suy nghĩ", 2),
    ],
    "sigma": [
        ("sigma", 2), ("lone wolf", 2), ("không cần ai", 2),
        ("tự làm", 1), ("độc lập", 1), ("alpha", 2),
    ],
    "rizz": [
        ("rizz", 3), ("có duyên", 2), ("smooth", 2), ("thả thính", 2),
        ("charm", 2), ("thành công tán", 2),
    ],
    "len_mat": [
        ("lên mặt", 3), ("tự cao", 2), ("kiêu", 2), ("coi thường", 2),
        ("arrogant", 2), ("ta đây", 2), ("giỏi hơn", 1),
    ],
    "tiet_lo": [
        ("tiết lộ", 2), ("lộ ra", 2), ("expose", 2), ("reveal", 2),
        ("thật ra", 1), ("bí mật", 1), ("bị lộ", 2),
    ],
    "noi_ngoa": [
        ("nghe nói", 2), ("người ta nói", 2), ("gossip", 2),
        ("đồn", 2), ("truyền tai", 2), ("tin đồn", 2), ("bàn tán", 2),
    ],

    # ── Thái độ ──────────────────────────────────────────────────────────
    "gia_vo": [
        ("giả vờ", 3), ("giả bộ", 3), ("pretend", 2), ("act", 1),
        ("tôi ổn mà", 1), ("bình thường thôi", 1), ("giả dối", 2),
    ],
    "binh_than": [
        ("bình thản", 3), ("không quan tâm", 2), ("kệ", 2),
        ("unbothered", 2), ("không sao", 1), ("whatever", 2),
    ],
    "khong_quan_tam": [
        ("kệ", 2), ("không care", 3), ("không liên quan", 2),
        ("tôi không cần biết", 2), ("zero fucks", 3), ("don't care", 2),
    ],
    "bao_thu": [
        ("bảo thủ", 3), ("không chịu nghe", 2), ("cứng đầu", 2),
        ("stubborn", 2), ("không thay đổi", 2), ("giữ ý kiến", 1),
    ],
    "giu_binh_tinh": [
        ("bình tĩnh", 2), ("calm down", 2), ("hít thở", 2),
        ("giữ bình tĩnh", 3), ("đừng tức", 1), ("relax", 2),
    ],
    "nham_mat": [
        ("nhắm mắt", 2), ("cố tình không thấy", 3), ("ignore", 2),
        ("bỏ qua", 1), ("không nhìn", 1), ("làm ngơ", 2),
    ],
    "buong_bo": [
        ("buông bỏ", 3), ("thôi kệ", 2), ("let go", 2),
        ("không giữ nữa", 2), ("từ bỏ", 1), ("move on", 2), ("bỏ qua đi", 1),
    ],

    # ── Quan hệ / Memory ─────────────────────────────────────────────────
    "nho_nhung": [
        ("nhớ", 1), ("nhớ nhung", 3), ("nostalgia", 2), ("ngày xưa", 2),
        ("hồi đó", 2), ("miss", 2), ("nhớ lại", 2), ("quá khứ", 1),
    ],
    "qua_khu": [
        ("quá khứ", 2), ("ngày xưa", 2), ("hồi nhỏ", 2),
        ("khi còn", 2), ("flashback", 2), ("trước đây", 1),
    ],
    "tim_hieu": [
        ("tìm hiểu", 2), ("đang thích", 2), ("giai đoạn tìm hiểu", 3),
        ("nhắn tin nhiều", 1), ("hay gặp", 1), ("đang để ý", 2),
    ],
    "lien_quan": [
        ("liên quan đến tôi", 3), ("vụ này là về tôi", 3),
        ("tag tôi vào", 2), ("đang nói về tôi", 2), ("tôi biết vụ này", 2),
    ],

    # ── Misc ─────────────────────────────────────────────────────────────
    "lo_xa": [
        ("lo xa", 2), ("overthinking", 2), ("lo lắng", 1),
        ("sợ tương lai", 2), ("what if", 1), ("lo quá", 1),
    ],
    "thoai_mai": [
        ("thoải mái", 3), ("chill", 2), ("thư giãn", 1),
        ("relax", 1), ("bình thường thôi", 1), ("easy", 1),
    ],
}


# ---------------------------------------------------------------------------
# Layer 3: LLM classifier
# ---------------------------------------------------------------------------

_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
_LLM_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "google/gemma-3-4b-it:free",
    "deepseek/deepseek-chat-v3-0324:free",
]

_SYSTEM_PROMPT = f"""Bạn là AI phân tích phản ứng cộng đồng mạng Việt Nam cho video viral.

Nhiệm vụ: Cho một comment, hãy chọn 1-3 emotions thể hiện cách CỘNG ĐỒNG MẠNG sẽ PHẢN ỨNG với comment đó.
(KHÔNG phải cảm xúc của người viết — mà là phản ứng của người ĐỌC/XEM)

Ví dụ:
- "mẹ bắt học từ 0h đến 7h sáng" → người đọc: đồng cảm, xúc động, tức giận hộ
- "tôi bị gay" → người đọc: cười, ngạc nhiên
- "học đến 2h sáng vẫn bị chửi" → người đọc: bức xúc, thương, đồng cảm

Danh sách emotions hợp lệ:
{', '.join(EMOTIONS)}

Trả về JSON array với 1-3 emotions, ví dụ: ["dong_tinh", "xuc_dong", "la_len_giai_toa"]
CHỈ trả về JSON array, không giải thích gì thêm."""


def _classify_llm(text: str) -> list[str] | None:
    """Try LLM classification. Returns list of emotions or None on failure."""
    if not _OPENROUTER_KEY:
        return None

    import json as _json
    try:
        from openai import OpenAI
        client = OpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")
    except ImportError:
        return None

    for model in _LLM_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f'Comment: "{text}"'},
                ],
                max_tokens=64,
                temperature=0.2,
            )
            raw = response.choices[0].message.content.strip()

            # Extract JSON array from response
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if not match:
                continue
            emotions = _json.loads(match.group())
            emotions = [e.strip() for e in emotions if isinstance(e, str)]
            valid = [e for e in emotions if e in EMOTIONS_SET]
            if valid:
                logger.debug(f"LLM ({model}) classified: {valid}")
                return valid[:3]
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                logger.debug(f"LLM {model} rate-limited")
            else:
                logger.debug(f"LLM {model} failed: {e}")

    return None


# ---------------------------------------------------------------------------
# Layer 1+2: Regex + keyword scoring
# ---------------------------------------------------------------------------

def _classify_rules(text: str, top_k: int = 3) -> list[str]:
    """Rule-based classification (Layer 1 patterns + Layer 2 keywords)."""
    scores: dict[str, float] = {}

    # Layer 1: hard patterns
    for pattern, emotion, weight in _HARD_RE:
        if pattern.search(text):
            scores[emotion] = scores.get(emotion, 0) + weight

    # Layer 2: keyword scoring
    text_lower = text.lower()
    for emotion, kw_list in _KEYWORD_MAP.items():
        for kw, w in kw_list:
            if kw.lower() in text_lower:
                scores[emotion] = scores.get(emotion, 0) + w

    if not scores:
        return []

    sorted_emotions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [e for e, _ in sorted_emotions[:top_k]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(text: str, top_k: int = 3, use_llm: bool = True) -> list[str]:
    """
    Classify a comment into community reaction emotions.

    Args:
        text: Raw Vietnamese comment text
        top_k: Max number of emotions to return (1-3 recommended)
        use_llm: Whether to try LLM if rule-based confidence is low

    Returns:
        List of emotion strings (from EMOTIONS), most fitting first.
        Empty list if no emotions matched.
    """
    # Always run rules first (fast)
    rule_results = _classify_rules(text, top_k=top_k)

    # If rules give strong signal (2+ emotions with high scores), skip LLM
    if len(rule_results) >= 2 and not use_llm:
        return rule_results

    # Try LLM for better accuracy
    if use_llm:
        llm_results = _classify_llm(text)
        if llm_results:
            # Merge: LLM takes priority, add any high-scoring rule results not in LLM
            merged = list(llm_results)
            for e in rule_results:
                if e not in merged and len(merged) < top_k:
                    merged.append(e)
            return merged[:top_k]

    return rule_results


def classify_batch(texts: list[str], top_k: int = 3, use_llm: bool = True) -> list[list[str]]:
    """Classify multiple texts. Returns list of emotion lists."""
    return [classify(t, top_k=top_k, use_llm=use_llm) for t in texts]


def pick_memes(
    emotions: list[str],
    used_paths: set[str],
    assets_dir: Path,
    max_per_emotion: int = 1,
) -> list[dict]:
    """
    For each emotion, pick one meme file from assets/memes_emotions/{emotion}/.
    No duplicates — skips files already in used_paths.

    Returns list of {"path": str, "emotion": str, "type": "video"|"image"}
    """
    video_exts = {".mp4", ".mov", ".webm"}
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    results = []

    for emotion in emotions:
        folder = assets_dir / "memes_emotions" / emotion
        if not folder.exists():
            continue

        candidates = []
        for f in folder.iterdir():
            if f.is_file() and str(f) not in used_paths:
                ext = f.suffix.lower()
                if ext in video_exts:
                    candidates.append({"path": str(f), "emotion": emotion, "type": "video"})
                elif ext in image_exts:
                    candidates.append({"path": str(f), "emotion": emotion, "type": "image"})

        if not candidates:
            continue

        chosen = random.sample(candidates, min(max_per_emotion, len(candidates)))
        for item in chosen:
            used_paths.add(item["path"])
            results.append(item)

    return results

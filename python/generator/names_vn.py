"""Vietnamese name generator following real surname frequency (approximate public estimates)."""
from __future__ import annotations

import numpy as np

SURNAMES = {
    "Nguyễn": 38.4, "Trần": 11.0, "Lê": 9.5, "Phạm": 7.1, "Hoàng": 4.0, "Huỳnh": 2.0, "Phan": 4.5,
    "Vũ": 2.5, "Võ": 1.5, "Đặng": 2.1, "Bùi": 2.0, "Đỗ": 1.4, "Hồ": 1.3, "Ngô": 1.3, "Dương": 1.0,
    "Lý": 0.5, "Đinh": 0.7, "Trương": 0.8, "Mai": 0.5, "Lâm": 0.4, "Tô": 0.3, "Hà": 0.5, "Cao": 0.4,
    "Lưu": 0.4, "Tạ": 0.3, "Chu": 0.2, "Châu": 0.3, "Kiều": 0.1, "Quách": 0.1, "Thái": 0.2,
}
MIDDLE_M = {"Văn": 30, "Minh": 12, "Đức": 9, "Quốc": 7, "Hoàng": 6, "Thanh": 6, "Hữu": 6, "Công": 5,
            "Anh": 4, "Tuấn": 3, "Xuân": 3, "Gia": 3, "Duy": 3, "Ngọc": 2, "Trọng": 2, "Thành": 2}
MIDDLE_F = {"Thị": 35, "Ngọc": 10, "Thu": 7, "Thanh": 7, "Minh": 6, "Phương": 5, "Kim": 5, "Hồng": 5,
            "Thùy": 4, "Bảo": 3, "Mai": 3, "Khánh": 3, "Diệu": 2, "Hải": 2, "Quỳnh": 2}
GIVEN_M = ["Anh", "Bảo", "Bình", "Cường", "Dũng", "Duy", "Đạt", "Hải", "Hiếu", "Hoàng", "Hùng", "Huy",
           "Khang", "Khánh", "Khoa", "Kiên", "Long", "Lộc", "Minh", "Nam", "Nghĩa", "Nhân", "Phong", "Phúc",
           "Quân", "Quang", "Sơn", "Tài", "Thắng", "Thành", "Thiện", "Tiến", "Toàn", "Trung", "Tú", "Tuấn",
           "Tùng", "Việt", "Vinh", "Vũ"]
GIVEN_F = ["An", "Anh", "Châu", "Chi", "Diệp", "Dung", "Giang", "Hà", "Hân", "Hạnh", "Hằng", "Hiền",
           "Hoa", "Hương", "Huyền", "Lan", "Liên", "Linh", "Loan", "Ly", "Mai", "My", "Nga", "Ngân", "Ngọc",
           "Nhi", "Nhung", "Oanh", "Phương", "Quyên", "Tâm", "Thảo", "Thơ", "Thủy", "Trang", "Trâm", "Uyên",
           "Vân", "Vy", "Yến"]

SME_PREFIX = ["Công ty TNHH", "Công ty TNHH", "Công ty Cổ phần", "Công ty TNHH MTV", "Doanh nghiệp tư nhân"]
SME_WORD1 = ["Thương mại", "Dịch vụ", "Sản xuất", "Xây dựng", "Vận tải", "Đầu tư", "Kỹ thuật", "Thực phẩm",
             "Nông sản", "Điện tử", "Nội thất", "Bao bì", "Du lịch", "Logistics", "Dược phẩm"]
SME_WORD2 = ["Phú An", "Minh Khang", "Hưng Thịnh", "Tân Phát", "Đại Lộc", "Thành Công", "Việt Tiến",
             "An Bình", "Kim Ngân", "Hòa Phát Lợi", "Sao Mai", "Trường Sơn", "Bảo Châu", "Nam Việt",
             "Thiên Ân", "Đông Á Lâm", "Gia Hưng", "Phúc Long Hải", "Hồng Hà Xanh", "Tín Nghĩa"]


def _pick(rng: np.random.Generator, d: dict[str, float], n: int) -> np.ndarray:
    keys = np.array(list(d.keys()))
    p = np.array(list(d.values()), dtype=float)
    return rng.choice(keys, size=n, p=p / p.sum())


def person_names(rng: np.random.Generator, genders: np.ndarray) -> np.ndarray:
    n = len(genders)
    sur = _pick(rng, SURNAMES, n)
    mid_m, mid_f = _pick(rng, MIDDLE_M, n), _pick(rng, MIDDLE_F, n)
    giv_m, giv_f = rng.choice(GIVEN_M, n), rng.choice(GIVEN_F, n)
    male = genders == "M"
    mid = np.where(male, mid_m, mid_f)
    giv = np.where(male, giv_m, giv_f)
    # avoid "Anh Anh" style duplicates
    giv = np.where(mid == giv, np.where(male, "Hưng", "Hoa"), giv)
    return np.char.add(np.char.add(np.char.add(np.char.add(sur, " "), mid), " "), giv)


def sme_names(rng: np.random.Generator, n: int) -> np.ndarray:
    a, b, c = rng.choice(SME_PREFIX, n), rng.choice(SME_WORD1, n), rng.choice(SME_WORD2, n)
    names = np.char.add(np.char.add(np.char.add(np.char.add(a, " "), b), " "), c)
    # make names unique by adding an ordinal where needed
    seen: dict[str, int] = {}
    out = []
    for nm in names:
        k = seen.get(nm, 0)
        seen[nm] = k + 1
        out.append(nm if k == 0 else f"{nm} {k + 1}")
    return np.array(out)

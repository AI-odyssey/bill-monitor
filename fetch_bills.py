"""
국회 의안정보시스템 법안 수집 스크립트
- 날짜 범위 지정 또는 최근 N일 수집
- 키워드 필터링 후 결과 출력
"""

import requests
import re
import json
import argparse
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

BASE = "http://likms.assembly.go.kr/bill"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/bi/bill/state/mooringBillPage.do",
}

# ── 섹터별 키워드 ──────────────────────────────────────────
SECTOR_KEYWORDS = {
    "해운": ["해운", "선박", "해양수산", "항만"],
    "에너지_수소": ["수소", "청정수소", "수전해", "수소법", "CHPS"],
    "에너지_재생": ["재생에너지", "태양광", "풍력", "RPS"],
    "포장재_재활용": ["포장재", "EPR", "재활용", "멸균팩"],
    "반도체_AI": ["반도체", "인공지능", "AI", "첨단산업"],
    "방산": ["방위산업", "방산", "무기"],
    "의료_헬스": ["의료", "보건", "제약", "바이오"],
}


def parse_bill_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    bills = []
    for row in soup.select("table tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        bill_no    = cols[0].get_text(strip=True)
        propose_dt = cols[3].get_text(strip=True)

        link_tag = cols[1].find("a")
        if link_tag:
            for ico in link_tag.find_all("i"):
                ico.decompose()
            full_name = link_tag.get_text(strip=True)
            bill_id   = link_tag.get("data-bill-id", "")
        else:
            full_name = ""
            bill_id   = ""

        # 대표발의자 추출
        proposer_match = re.search(r'\(([^)]*의원[^)]*)\)', full_name)
        proposer = ""
        if proposer_match:
            raw = proposer_match.group(1)
            name_match = re.match(r'([가-힣]+)의원', raw)
            proposer = name_match.group(1) if name_match else raw

        bill_name = re.sub(r'\([^)]*의원[^)]*\)', '', full_name).strip()

        if bill_no and bill_name:
            bills.append({
                "bill_no":    bill_no,
                "bill_name":  bill_name,
                "proposer":   proposer,
                "propose_dt": propose_dt,
                "link":       f"{BASE}/bi/billDetailPage.do?billId={bill_id}" if bill_id else "",
            })
    return bills


def fetch_bills(date_from: str, date_to: str, page_size: int = 100) -> list[dict]:
    """날짜 범위로 법안 수집 (date_from/date_to: YYYY-MM-DD)"""
    params = {
        "stateId":       "mooring",
        "billKind":      "법률안",
        "page":          "1",
        "listOrd":       "billNo",
        "ordCd":         "DESC",
        "pageSize":      str(page_size),
        "proposeDtFrom": date_from,
        "proposeDtTo":   date_to,
    }
    res = requests.post(
        f"{BASE}/bi/bill/state/searchBillStatePaging.do",
        data=params, headers=HEADERS, timeout=15,
    )
    res.raise_for_status()
    bills = parse_bill_list(res.text)
    print(f"[수집] {date_from} ~ {date_to}: {len(bills)}건")
    return bills


def filter_bills(bills: list[dict],
                 keywords: list[str] = None,
                 proposer: str = None,
                 sectors: list[str] = None) -> list[dict]:
    """키워드 / 발의자 / 섹터 필터"""
    results = []
    for b in bills:
        # 발의자 필터
        if proposer and proposer not in b["proposer"]:
            continue
        # 키워드 직접 필터
        if keywords:
            if not any(kw in b["bill_name"] for kw in keywords):
                continue
        # 섹터 필터
        if sectors:
            matched = False
            for sector in sectors:
                kws = SECTOR_KEYWORDS.get(sector, [])
                if any(kw in b["bill_name"] for kw in kws):
                    b["sector"] = sector
                    matched = True
                    break
            if not matched:
                continue
        results.append(b)
    return results


def print_results(bills: list[dict]):
    if not bills:
        print("  → 결과 없음")
        return
    for b in bills:
        sector = f"[{b.get('sector', '')}] " if b.get("sector") else ""
        print(f"  {b['bill_no']} | {b['propose_dt']} | {b['proposer']} | {sector}{b['bill_name']}")
        if b["link"]:
            print(f"    {b['link']}")


# ── CLI ───────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="국회 법안 수집")
    parser.add_argument("--from",  dest="date_from", default=None, help="시작일 YYYY-MM-DD")
    parser.add_argument("--to",    dest="date_to",   default=None, help="종료일 YYYY-MM-DD")
    parser.add_argument("--days",  type=int, default=1,            help="최근 N일 (기본 1)")
    parser.add_argument("--keyword", nargs="*",                    help="법안명 키워드")
    parser.add_argument("--proposer",                              help="대표발의 의원 이름")
    parser.add_argument("--sector", nargs="*",
                        choices=list(SECTOR_KEYWORDS.keys()),      help="섹터 필터")
    parser.add_argument("--json",  action="store_true",            help="JSON 출력")
    args = parser.parse_args()

    if args.date_from and args.date_to:
        date_from, date_to = args.date_from, args.date_to
    else:
        date_to   = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    bills = fetch_bills(date_from, date_to)
    filtered = filter_bills(bills,
                            keywords=args.keyword,
                            proposer=args.proposer,
                            sectors=args.sector)

    print(f"\n[필터 결과] {len(filtered)}건")
    if args.json:
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
    else:
        print_results(filtered)

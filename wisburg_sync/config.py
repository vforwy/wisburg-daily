from dataclasses import dataclass


BASE_URL = "https://api-omen.wisburg.com"
PAGE_SIZE = 100
OVERLAP_HOURS = 48
BACKFILL_DAYS = 7
MAX_PAGES = 80


@dataclass(frozen=True)
class Source:
    name: str
    enabled: bool
    # always: 列表没有正文，必须拉详情
    # try: 先试详情，404 则保留列表
    # mikko: 列表即全文，有配图或正文像被截断时再拉详情
    # never: 只用列表
    detail: str


SOURCES = (
    Source("feed", False, "never"),
    Source("market-daily", True, "try"),
    Source("mikko-logs", True, "mikko"),
    Source("reports", True, "always"),
    Source("company-reports", True, "always"),
    Source("earningscalls", True, "always"),
    Source("am-reports", True, "always"),
    Source("archives", True, "always"),
    Source("articles", True, "always"),
)

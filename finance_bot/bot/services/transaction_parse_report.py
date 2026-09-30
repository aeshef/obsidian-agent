"""Line provenance and partial recovery for a financial import draft."""
from dataclasses import dataclass, field
import requests
from shared.agent.platform_config import platform_int


@dataclass
class ParseReport:
    transactions: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    total_lines: int = 0


async def parse_report(parse_chunk, text, telegram_id=None, on_progress=None):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = ParseReport(total_lines=len(lines))
    size = max(1, platform_int("finance_import", "chunk_lines", default=10))
    async def parse_rows(rows, start):
        try:
            txns = await parse_chunk("\n".join(rows), telegram_id=telegram_id)
            if len(rows) > 1 and len(txns) != len(rows):
                raise ValueError("line_count_mismatch")
            if not txns or any(not isinstance(t, dict) for t in txns):
                raise ValueError("invalid_rows")
            for offset, txn in enumerate(txns):
                txn = dict(txn)
                txn["_source_line"] = start + min(offset, len(rows)-1) + 1
                txn["_source_text"] = rows[min(offset, len(rows)-1)]
                result.transactions.append(txn)
        except requests.RequestException:
            # Provider outage is not bad user input; do not multiply network retries.
            for offset, line in enumerate(rows):
                result.issues.append({"line": start+offset+1, "text": line, "reason": "service_unavailable"})
        except (ValueError, TypeError, KeyError):
            if len(rows) > 1:
                for offset, line in enumerate(rows):
                    await parse_rows([line], start+offset)
            else:
                result.issues.append({"line": start+1, "text": rows[0], "reason": "unrecognized"})
    for start in range(0, len(lines), size):
        if on_progress:
            await on_progress(start//size+1, (len(lines)+size-1)//size)
        await parse_rows(lines[start:start+size], start)
    return result

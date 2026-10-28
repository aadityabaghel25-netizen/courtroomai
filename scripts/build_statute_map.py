"""
Build data/statutes/ipc_bns_map.csv from the official correspondence table
"Correspondence Table and Comparison Summary of the Bharatiya Nyaya Sanhita, 2023
(BNS) to the Indian Penal Code, 1860 (IPC)", CAPT Bhopal (Central Academy for
Police Training, MHA), hosted at:
  https://www.keralaprisons.gov.in/userfiles/act-and-rules/comparison_summary_BNS_to_IPC.pdf

Nothing here comes from a model: every row is parsed from the PDF and records
the page it came from. IPC sections that map to several BNS provisions are
joined into one row ("2(36), 2(37), 2(38)").

If data/statutes/ik_crossref.csv exists (scripts/fetch_acts.py), it is used as a
second, independent source:
- each IPC->BNS row records whether Indian Kanoon's editorial note agrees
  (column ik_agrees: yes / no / n/a);
- CrPC->BNSS and Indian Evidence Act->BSA rows are added from those notes, with the
  source labelled as Indian Kanoon's editorial cross-reference (not part of the Act).

Usage: python scripts/build_statute_map.py path/to/comparison_summary_BNS_to_IPC.pdf
"""

import csv
import re
import sys
from collections import OrderedDict
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://www.keralaprisons.gov.in/userfiles/act-and-rules/comparison_summary_BNS_to_IPC.pdf"
SOURCE = "CAPT Bhopal BNS-IPC correspondence table"

_IPC_SEC = re.compile(r"\b(\d{1,3}[A-Z]{0,2})\b")


def norm_bns(cell: str) -> str:
    cell = re.sub(r"\s+", "", cell or "")
    return cell.replace("/", ", ")


def rows_from_pdf(path: Path):
    """Yield (page, bns, subject, ipc) with continuation lines merged into the previous row."""
    cur = None
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for raw in table:
                    cells = [(c or "").strip() for c in raw]
                    if len(cells) == 6:  # first page has an extra empty leading column
                        cells = cells[1:5]
                    elif len(cells) >= 4:
                        cells = cells[:4]
                    else:
                        continue
                    bns, subject, ipc = cells[0], cells[1], cells[2]
                    if bns.startswith("BNS") or bns in ("Sections/", "Subsecti", "ons"):
                        continue
                    if re.match(r"^\d", bns):
                        if cur:
                            yield cur
                        cur = {"page": pno, "bns": bns, "subject": subject, "ipc": ipc}
                    elif cur is not None:
                        # continuation of a row split across lines or pages
                        if subject:
                            cur["subject"] += " " + subject
                        if ipc:
                            cur["ipc"] += " " + ipc
    if cur:
        yield cur


def main() -> int:
    pdf_path = Path(sys.argv[1])
    by_ipc: "OrderedDict[str, dict]" = OrderedDict()
    new_only = 0
    total = 0
    for r in rows_from_pdf(pdf_path):
        total += 1
        ipc_cell = re.sub(r"\s+", " ", r["ipc"]).strip()
        if not ipc_cell or ipc_cell.lower().startswith("new"):
            new_only += 1
            continue
        secs = [s for s in _IPC_SEC.findall(ipc_cell.replace("Clause", ""))]
        for sec in secs:
            entry = by_ipc.setdefault(sec, {"bns": [], "titles": [], "pages": []})
            b = norm_bns(r["bns"])
            if b not in entry["bns"]:
                entry["bns"].append(b)
                entry["titles"].append(re.sub(r"\s+", " ", r["subject"]).strip().rstrip("."))
                entry["pages"].append(str(r["page"]))
    xref_path = ROOT / "data" / "statutes" / "ik_crossref.csv"
    ik = list(csv.DictReader(open(xref_path, encoding="utf-8"))) if xref_path.exists() else []
    ik_ipc = {}  # IPC section -> set of BNS base section numbers that Indian Kanoon links to it
    for r in ik:
        if r["old_act"] == "IPC":
            for old in re.findall(r"\d{1,3}[A-Z]{0,2}", r["old_section"]):
                ik_ipc.setdefault(old, set()).add(r["new_section"])

    out = ROOT / "data" / "statutes" / "ipc_bns_map.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    agree = disagree = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["old_act", "old_section", "new_act", "new_section", "title", "source", "ik_agrees"])
        for sec, e in by_ipc.items():
            pages = ", ".join(sorted(set(e["pages"]), key=int))
            bases = {re.match(r"\d+", b).group(0) for b in e["bns"] if re.match(r"\d+", b)}
            if not ik or sec not in ik_ipc:
                flag = "n/a"
            elif bases & ik_ipc[sec]:
                flag, agree = "yes", agree + 1
            else:
                flag, disagree = "no", disagree + 1
            w.writerow(["IPC", sec, "BNS", ", ".join(e["bns"]), "; ".join(e["titles"])[:200],
                        f"{SOURCE}, p. {pages} ({SOURCE_URL})", flag])
        extra = {"CrPC": 0, "IEA": 0}
        seen = set()
        for r in ik:
            if r["old_act"] not in extra:
                continue
            for old in re.findall(r"\d{1,3}[A-Z]{0,2}", r["old_section"]):
                key = (r["old_act"], old)
                if key in seen:
                    continue
                seen.add(key)
                same = [x["new_section"] for x in ik if x["old_act"] == r["old_act"] and old in re.findall(r"\d{1,3}[A-Z]{0,2}", x["old_section"])]
                new_act = "BNSS" if r["old_act"] == "CrPC" else "BSA"
                w.writerow([r["old_act"], old, new_act, ", ".join(dict.fromkeys(same)), r["new_heading"][:200],
                            "Indian Kanoon editorial cross-reference in the Act text (not part of the Act)", "n/a"])
                extra[r["old_act"]] += 1
    print(f"OK: {total} table rows parsed, {new_only} BNS-only (new) rows skipped, "
          f"{len(by_ipc)} IPC sections written to {out.relative_to(ROOT)}")
    if ik:
        print(f"Cross-check with Indian Kanoon: {agree} agree, {disagree} disagree, "
              f"{len(by_ipc) - agree - disagree} not covered by its notes")
        print(f"Added from Indian Kanoon notes: {extra['CrPC']} CrPC->BNSS rows, {extra['IEA']} Evidence Act->BSA rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

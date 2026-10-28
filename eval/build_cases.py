"""
Build eval/cases.jsonl: synthetic FIRs (fictional people, no real personal data).

Labels and their limits (stated in the README too):
- relevant_case_ids: every corpus judgment fetched under the same Indian Kanoon
  query category. These are TOPIC labels, not hand-judged relevance.
- audit_draft: one REAL citation (a corpus judgment, cited by its Indian Kanoon
  title) and one FAKE citation (fictional parties, future reporter year), with
  "fake": true on the fake one. Expected: real -> resolved in corpus;
  fake -> never "verified".
- split: 9 dev / 17 test by a hash of the case ID; thresholds are tuned on dev only.

Usage: python eval/build_cases.py
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

# (case_id, category, FIR text). All names and places are fictional.
FIRS = [
    ("E01", "murder IPC 302", "FIR No. 201/2022, P.S. Rampur Example. On 12.06.2022 at about 7 pm the deceased Harish (fictional) was attacked with a sickle by the accused Bhola Ram (fictional) over a boundary dispute in the field. Two villagers saw the attack. Harish died on the way to hospital. The sickle was recovered from the accused's house. Sections 302 and 34 IPC."),
    ("E02", "murder IPC 302", "FIR No. 77/2021, P.S. Sample Ganj. The complainant Sita (fictional) reported that her husband Mahesh (fictional) was found dead in their courtyard on 03.04.2021 with head injuries. Neighbours heard a quarrel between Mahesh and his brother Naresh (fictional) the previous night. Naresh was absconding. Section 302 IPC."),
    ("E03", "murder IPC 302", "FIR No. 15/2023, P.S. Example Nagar. On 20.01.2023 the accused persons Raju and Kallu (fictional) assaulted Dinesh (fictional) with lathis at a wedding after an argument. Dinesh died of his injuries two days later. The only eyewitness is the deceased's cousin. Sections 302, 323 and 34 IPC."),
    ("E04", "dowry harassment IPC 498A", "FIR No. 310/2021, P.S. Example Colony. The complainant Meena (fictional) married Arun (fictional) on 15.05.2019. She alleges that her husband and father-in-law demanded Rs. 3,00,000 and beat her when the demand was not met. She was sent back to her parents' house on 10.09.2021. Sections 498A and 406 IPC."),
    ("E05", "dowry harassment IPC 498A", "FIR No. 98/2022, P.S. Model Example. The complainant Pooja (fictional) states that her in-laws taunted her for bringing insufficient dowry and that her sister-in-law, who lives in another city, also harassed her on phone calls. She left the matrimonial home on 01.02.2022. Sections 498A and 34 IPC."),
    ("E06", "dowry harassment IPC 498A", "FIR No. 451/2020, P.S. Sampleabad. The complainant's daughter Kavita (fictional) died of burns at her matrimonial home on 22.11.2020, three years after marriage. The complainant says the husband had demanded a motorcycle shortly before her death. Sections 498A and 304B IPC."),
    ("E07", "rape IPC 376", "FIR No. 66/2022, P.S. Example Pur. The prosecutrix (name withheld, fictional case) states that on 08.08.2022 the accused Sonu (fictional), a neighbour, forcibly took her to a farmhouse and sexually assaulted her. She told her mother the same evening. The medical examination was done on 09.08.2022. Section 376 IPC."),
    ("E08", "rape IPC 376", "FIR No. 120/2021, P.S. Sample Town. The prosecutrix (fictional case) alleges that the accused Vikas (fictional) established physical relations with her on a false promise of marriage between 2019 and 2021 and then married someone else. Section 376 IPC."),
    ("E09", "rape IPC 376", "FIR No. 34/2023, P.S. Example Kheda. A minor girl (fictional case) was assaulted by the accused, a relative, on 14.02.2023. The FIR was lodged 10 days later because the family feared social stigma. There is no eyewitness. Section 376 IPC."),
    ("E10", "cheating IPC 420", "FIR No. 501/2022, P.S. Example Market. The accused Suresh Gupta (fictional) took Rs. 8,00,000 from the complainant Ajay (fictional) promising to sell him a plot of land. Later the complainant found the plot was already sold to someone else. Sections 420 and 406 IPC."),
    ("E11", "cheating IPC 420", "FIR No. 73/2023, P.S. Sample Chowk. The complainant company alleges that the accused Ravi Traders (fictional) placed orders worth Rs. 25,00,000 on credit and then stopped payment, claiming losses. The complainant says the accused never intended to pay. Section 420 IPC."),
    ("E12", "cheating IPC 420", "FIR No. 222/2021, P.S. Example Road. The accused Neha (fictional) collected money from 40 persons promising government jobs and issued fake appointment letters. She was arrested on 30.07.2021. Sections 420, 467 and 468 IPC."),
    ("E13", "anticipatory bail", "FIR No. 88/2023, P.S. Example Vihar. The applicant Rohit (fictional), a college lecturer, apprehends arrest in a complaint alleging that he misappropriated Rs. 2,00,000 from a society fund. He states he has joined the inquiry and produced the accounts. Sections 406 and 420 IPC."),
    ("E14", "anticipatory bail", "FIR No. 19/2022, P.S. Sample Nagar. The applicants, the parents-in-law of the complainant (fictional), seek protection from arrest in a dowry case. They state they live separately in another town and are aged 70 and 66. Sections 498A and 406 IPC."),
    ("E15", "anticipatory bail", "FIR No. 140/2021, P.S. Example Gaon. The applicant Mukesh (fictional) is named in an FIR under the SC/ST (Prevention of Atrocities) Act for alleged caste abuse during a land dispute. He claims the complaint is false and seeks anticipatory bail."),
    ("E16", "bail conditions criminal", "FIR No. 55/2020, P.S. Example Lines. The accused Gopal (fictional) has been in custody for 18 months for possession of a commercial quantity of a narcotic substance. The trial has not begun. He seeks regular bail. NDPS Act Sections 21 and 29."),
    ("E17", "bail conditions criminal", "FIR No. 301/2022, P.S. Sampleganj. The accused Imran (fictional) was granted bail with a condition to deposit Rs. 10,00,000. He says he cannot pay and remains in jail. He seeks modification of the bail condition. Section 420 IPC."),
    ("E18", "FIR quashing", "FIR No. 400/2021, P.S. Example Park. The petitioners seek quashing of an FIR alleging cheating in a business transaction. They say the dispute is purely civil, about the quality of goods supplied, and a civil suit is already pending. Sections 406 and 420 IPC."),
    ("E19", "FIR quashing", "FIR No. 12/2022, P.S. Sample Bazar. The husband and wife (fictional) have settled their matrimonial dispute and the wife has filed an affidavit saying she does not wish to continue the case. The husband seeks quashing of the FIR. Sections 498A and 406 IPC."),
    ("E20", "FIR quashing", "FIR No. 205/2023, P.S. Example Cantt. The petitioner, a public servant (fictional), seeks quashing of a trap case alleging he demanded a bribe, stating that the complainant had a grudge against him. Prevention of Corruption Act Section 7."),
    ("E21", "defamation IPC 499", "Complaint Case No. 15/2022 before the Magistrate, Example City. The complainant Dr. Anand (fictional) alleges that the accused published a newspaper article calling him corrupt without any basis on 05.05.2022. Sections 499 and 500 IPC."),
    ("E22", "defamation IPC 499", "Complaint Case No. 44/2021, Sample Court. The complainant company (fictional) alleges that its former director posted on social media that the company cheats customers. The accused says the statement was made in good faith. Section 500 IPC."),
    ("E23", "corporate fraud companies act", "Complaint by the Serious Fraud Investigation Office (fictional matter) alleging that the directors of Example Infra Ltd (fictional) diverted loan funds to shell companies between 2017 and 2019. One director seeks bail. Section 447 Companies Act, 2013."),
    ("E24", "corporate fraud companies act", "FIR No. 66/2020, Economic Offences Wing, Example. The complainant, a minority shareholder (fictional), alleges that the managing director forged board resolutions to allot shares to himself. Sections 420, 467 and 468 IPC and Section 447 Companies Act."),
    ("E25", "SEBI insider trading", "Show-cause notice (fictional matter): the noticee, a senior employee of Example Pharma Ltd (fictional), traded in the company's shares two days before the announcement of a drug approval in 2021. SEBI alleges insider trading under the PIT Regulations."),
    ("E26", "SEBI insider trading", "Show-cause notice (fictional matter): the noticee's spouse bought shares of Sample Tech Ltd (fictional) a week before a merger was announced in 2020. The noticee was on the company's board. SEBI alleges communication of unpublished price sensitive information."),
]

FAKES = [
    ("Imaginary Kumar v. State of Nowhere", "(2031) 4 SCC 777"),
    ("Fictitious Rao v. Union of Utopia", "(2032) 9 SCC 101"),
    ("Phantom Lal v. State of Neverland", "AIR 2033 SC 4040"),
]


def main():
    by_cat = {}
    for f in RAW.glob("[0-9]*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        by_cat.setdefault(d["_meta"]["query_category"], []).append((str(d["tid"]), d["title"]))
    # Deterministic split by case ID hash: the 9 lowest hashes are dev, the rest test.
    dev_ids = set(sorted((c[0] for c in FIRS), key=lambda c: hashlib.sha1(c.encode()).hexdigest())[:9])
    out = []
    for i, (cid, cat, fir) in enumerate(FIRS):
        rel = sorted(by_cat.get(cat, []))
        if not rel:
            print(f"FAIL: no corpus judgments for category {cat!r}")
            return 1
        real_id, real_title = rel[i % len(rel)]
        real_name = real_title.rsplit(" on ", 1)[0].rstrip(" ,.")
        fake_name, fake_cite = FAKES[i % len(FAKES)]
        draft = (f"The applicant relies on {real_name}, which is relevant to the issues in this case. "
                 f"The applicant also relies on {fake_name}, {fake_cite}, where it was held that the FIR must be quashed in such cases.")
        split = "dev" if cid in dev_ids else "test"
        out.append({"id": cid, "split": split, "category": cat, "fir": f"SYNTHETIC EVAL FIR (fictional). {fir}",
                    "relevant_case_ids": [r[0] for r in rel],
                    "audit_draft": draft,
                    "audit_citations": [{"case_name": real_name, "case_id": real_id, "fake": False},
                                        {"case_name": fake_name, "citation": fake_cite, "fake": True}]})
    dest = ROOT / "eval" / "cases.jsonl"
    dest.write_text("\n".join(json.dumps(o) for o in out) + "\n", encoding="utf-8")
    print(f"OK: {len(out)} cases ({sum(o['split'] == 'dev' for o in out)} dev, {sum(o['split'] == 'test' for o in out)} test) -> {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

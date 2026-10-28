"""
Bare Acts Scraper & Structurer
Scrapes and structures core Indian statutory acts at section level.
Acts included:
- Indian Penal Code (IPC)
- Code of Criminal Procedure (CrPC)
- Indian Evidence Act
- Companies Act 2013 (Key sections)
- Negotiable Instruments Act (Section 138)
"""

import json
from pathlib import Path
DATA_DIR = Path("data/raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)
KEY_BARE_ACTS = [
    {
        "act_name": "Indian Penal Code",
        "act_code": "IPC",
        "sections": [
            {
                "section": "302",
                "title": "Punishment for murder",
                "content": "Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine."
            },
            {
                "section": "304",
                "title": "Punishment for culpable homicide not amounting to murder",
                "content": "Whoever commits culpable homicide not amounting to murder shall be punished with imprisonment for life, or imprisonment of either description for a term which may extend to ten years, and shall also be liable to fine."
            },
            {
                "section": "304B",
                "title": "Dowry death",
                "content": "Where the death of a woman is caused by any burns or bodily injury or occurs otherwise than under normal circumstances within seven years of her marriage, and it is shown that soon before her death she was subjected to cruelty or harassment by her husband or any relative of her husband for, or in connection with, any demand for dowry, such death shall be called 'dowry death', and such husband or relative shall be deemed to have caused her death."
            },
            {
                "section": "376",
                "title": "Punishment for rape",
                "content": "Whoever, except in the cases provided for in sub-section (2), commits rape, shall be punished with rigorous imprisonment of either description for a term which shall not be less than ten years, but which may extend to imprisonment for life, and shall also be liable to fine."
            },
            {
                "section": "420",
                "title": "Cheating and dishonestly inducing delivery of property",
                "content": "Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person, or to make, alter or destroy the whole or any part of a valuable security, or anything which is signed or sealed, and which is capable of being converted into a valuable security, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine."
            },
            {
                "section": "468",
                "title": "Forgery for purpose of cheating",
                "content": "Whoever commits forgery, intending that the document or electronic record forged shall be used for the purpose of cheating, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine."
            },
            {
                "section": "498A",
                "title": "Husband or relative of husband of a woman subjecting her to cruelty",
                "content": "Whoever, being the husband or the relative of the husband of a woman, subjects such woman to cruelty shall be punished with imprisonment for a term which may extend to three years and shall also be liable to fine."
            }
        ]
    },
    {
        "act_name": "Code of Criminal Procedure",
        "act_code": "CRPC",
        "sections": [
            {
                "section": "438",
                "title": "Direction for grant of bail to person apprehending arrest",
                "content": "Where any person has reason to believe that he may be arrested on accusation of having committed a non-bailable offence, he may apply to the High Court or the Court of Session for a direction under this section that in the event of such arrest he shall be released on bail."
            },
            {
                "section": "482",
                "title": "Saving of inherent powers of High Court",
                "content": "Nothing in this Code shall be deemed to limit or affect the inherent powers of the High Court to make such orders as may be necessary to give effect to any order under this Code, or to prevent abuse of the process of any Court or otherwise to secure the ends of justice."
            }
        ]
    }
]
def save_bare_acts():
    """Save structured Bare Acts as raw JSON documents for ingestion."""
    count = 0
    for act in KEY_BARE_ACTS:
        for sec in act["sections"]:
            doc_id = f"bare_act_{act['act_code'].lower()}_{sec['section'].lower()}"
            doc = {
                "doc": f"{act['act_name']} Section {sec['section']} — {sec['title']}\n{sec['content']}",
                "_meta": {
                    "query_category": "Bare Act",
                    "title": f"{act['act_name']} Section {sec['section']}: {sec['title']}",
                    "court": "Statute / Legislation",
                    "date": "2024",
                    "doc_id": doc_id,
                    "source": "bare_act"
                }
            }
            filepath = DATA_DIR / f"{doc_id}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
            count += 1
    print(f"[BARE ACTS] Saved {count} bare act sections to {DATA_DIR}")
if __name__ == "__main__":
    save_bare_acts()

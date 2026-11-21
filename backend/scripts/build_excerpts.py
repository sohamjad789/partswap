"""Build compact, topic-relevant local excerpts from available datasheet PDFs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import all_parts, load_json  # noqa: E402
from app.extract.pdf_pages import page_texts  # noqa: E402
from app.paths import data_dir  # noqa: E402


def _chunks(text: str, limit: int = 700):
    for block in (part.strip() for part in text.split("\n\n")):
        while block:
            yield block[:limit]
            block = block[limit:]


def main() -> int:
    keywords = [word.lower() for words in load_json("topics.json").values() for word in words]
    output_dir = data_dir() / "excerpts"
    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for part in all_parts():
        if not part.datasheet_filename:
            continue
        pdf = data_dir() / "datasheets" / part.datasheet_filename
        output = output_dir / f"{part.mpn.replace('/', '_')}.json"
        if not pdf.is_file() or (output.exists() and json.loads(output.read_text()).get("authored")):
            continue
        chunks = []
        for page in page_texts(pdf, max_pages=6):
            for text in _chunks(str(page["text"])):
                if any(word in text.lower() for word in keywords):
                    chunks.append({"page": page["page"], "text": text})
        chunks = chunks[:8]
        output.write_text(json.dumps({"mpn": part.mpn, "chunks": chunks}, indent=2) + "\n", encoding="utf-8")
        written += 1
    print(f"Wrote {written} excerpt files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

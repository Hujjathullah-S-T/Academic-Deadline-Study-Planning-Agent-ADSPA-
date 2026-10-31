"""Study file extraction, source search, and grounded AI study aids."""
from __future__ import annotations

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def extract_text(filename: str, content: bytes, max_chars: int = 120_000) -> dict[str, Any]:
    """Extract text from supported class materials; report extraction failures explicitly."""
    suffix = Path(filename).suffix.lower()
    text = ""
    try:
        if suffix in {".txt", ".md", ".csv"}:
            text = content.decode("utf-8-sig", errors="replace")
            if suffix == ".csv":
                rows = list(csv.reader(io.StringIO(text)))
                text = "\n".join(" | ".join(row) for row in rows)
        elif suffix == ".pdf":
            import fitz
            with fitz.open(stream=content, filetype="pdf") as document:
                text = "\n\n".join(page.get_text("text") for page in document)
        elif suffix == ".docx":
            from docx import Document
            document = Document(io.BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            for table in document.tables:
                text += "\n" + "\n".join(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        elif suffix == ".pptx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                slides = sorted(name for name in archive.namelist()
                                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
                parts = []
                ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                for name in slides:
                    root = ET.fromstring(archive.read(name))
                    parts.append(" ".join(node.text or "" for node in root.findall(".//a:t", ns)))
                text = "\n\n".join(parts)
        else:
            raise ValueError("Supported formats are PDF, DOCX, PPTX, TXT, Markdown, and CSV.")
    except (ImportError, OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Supported formats"):
            raise
        raise ValueError(f"Could not extract text from {filename}: {exc}") from exc
    text = text.strip()
    return {"text": text[:max_chars], "truncated": len(text) > max_chars,
            "character_count": len(text), "has_text": bool(text),
            "note": "This file contains no extractable text; scanned handwriting requires OCR." if not text else ""}


def search_materials(query: str, materials: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    terms = [term.casefold() for term in re.findall(r"[\w'-]+", query) if len(term) > 1]
    if not terms:
        return []
    hits = []
    for material in materials:
        content = "\n".join(str(material.get(key, "")) for key in
            ("extracted_text", "unit", "notes") if material.get(key))
        title = str(material.get("title", ""))
        if not content:
            continue
        folded = content.casefold()
        score = sum(folded.count(term) * (2 if term in title.casefold() else 1) for term in terms)
        if not score:
            continue
        locations = [folded.find(term) for term in terms if folded.find(term) >= 0]
        start = max(0, min(locations) - 220)
        end = min(len(content), max(locations) + 280)
        hits.append({"material_id": material.get("id"), "course_id": material.get("course_id"),
                     "title": title, "score": score, "excerpt": content[start:end].strip(),
                     "source_kind": "uploaded material"})
    return sorted(hits, key=lambda hit: hit["score"], reverse=True)[:limit]


def extract_assignment_questions(text: str) -> list[dict[str, Any]]:
    """Extract numbered question-like sections without asserting a perfect parse."""
    matches = list(re.finditer(r"(?im)^\s*(?:question\s*)?(\d{1,2})[.)\s]+", text))
    questions = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = re.sub(r"\s+", " ", text[match.end():end]).strip()
        if body:
            marks = re.search(r"\b(\d+(?:\.\d+)?)\s*marks?\b", body, re.I)
            questions.append({"number": int(match.group(1)), "text": body[:3000],
                              "marks": float(marks.group(1)) if marks else None,
                              "source": "extracted text; please verify against the original document"})
    return questions


def source_summary(text: str, max_sentences: int = 8) -> list[str]:
    """Return representative sentences verbatim so this fallback does not invent facts."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.strip()) > 35]
    if len(sentences) <= max_sentences:
        return sentences
    stride = max(1, len(sentences) // max_sentences)
    return sentences[::stride][:max_sentences]


def generated_study_aid(kind: str, source_text: str, prompt: str = "") -> dict[str, Any]:
    """Make deterministic aids from source text; callers may replace with an LLM response."""
    sentences = source_summary(source_text, 20)
    if kind == "revision_notes":
        generated = [{"label": f"Source point {index + 1}", "text": sentence}
                     for index, sentence in enumerate(sentences[:12])]
    elif kind == "flashcards":
        generated = [{"front": sentence.split(",", 1)[0][:140], "back": sentence}
                     for sentence in sentences[:12]]
    elif kind == "practice_questions":
        generated = [{"question": f"Explain or apply this idea: {sentence[:220]}",
                      "answer_basis": sentence, "marks": 5}
                     for sentence in sentences[:10]]
    else:
        raise ValueError("Choose revision_notes, flashcards, or practice_questions.")
    return {"kind": kind, "label": "Generated from extracted source sentences; verify before relying on it.",
            "source_excerpt_count": len(generated), "items": generated, "prompt": prompt}

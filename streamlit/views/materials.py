"""Grounded study material search and study-aid generation UI."""
from __future__ import annotations

import streamlit as st

from learning.materials import generated_study_aid, search_materials


def _available_model(agent) -> bool:
    return bool(agent.openai_setting("OPENAI_API_KEY") or agent.find_local_ollama_model())


def _answer_from_sources(agent, question: str, hits: list[dict]) -> str | None:
    if not _available_model(agent):
        return None
    sources = "\n\n".join(f"[{hit['title']}]\n{hit['excerpt']}" for hit in hits)
    prompt = ("Answer the student's question using only these uploaded-source excerpts. "
        "If the excerpts do not contain the requested information, say so clearly. "
        "Separate statements supported by a source from suggestions you generate. "
        "Cite each source by its title in square brackets. Do not invent syllabus requirements.\n\n"
        f"Question: {question}\n\nUploaded-source excerpts:\n{sources}")
    return agent.openai_chat_reply(prompt, [])


def render(agent) -> None:
    data = agent.load_data()
    materials = data.get("course_materials", [])
    courses = {str(course["id"]): course for course in data.get("courses", [])}
    st.subheader("Study material library")
    st.caption("Materials are grouped by course, semester, and unit in Courses. Search results below are quoted from extracted text; generated aids are labeled separately.")
    if not materials:
        st.info("Add links or upload PDF, Word, PowerPoint, text, Markdown, or CSV materials inside a course.")
        return
    searchable = []
    for material in materials:
        course = courses.get(str(material.get("course_id")), {})
        searchable.append({**material, "title": material.get("title", "Untitled"),
            "course_title": course.get("title", "Unknown course"),
            "search_text": " ".join((material.get("unit", ""), material.get("notes", ""), material.get("extracted_text", "")))})

    search_query = st.text_input("Search uploaded materials", placeholder="What should I study for Unit 4 of Computer Vision?")
    if search_query.strip():
        hits = search_materials(search_query, searchable)
        if not hits:
            st.warning("No matching text was found in saved materials. This is not evidence that a topic is absent from your syllabus.")
        else:
            st.markdown("#### Retrieved source excerpts")
            for hit in hits:
                st.markdown(f"**{hit['course_title']} · {hit['title']}**")
                st.caption("Direct excerpt from uploaded material")
                st.info(hit["excerpt"])
            try:
                answer = _answer_from_sources(agent, search_query, hits)
            except Exception as exc:
                answer = None
                st.warning(f"AI source answer unavailable: {exc}")
            if answer:
                st.markdown("#### AI response based on these excerpts")
                st.write(answer)
            else:
                st.caption("AI answer unavailable: set up OpenAI or Ollama for natural-language synthesis. Retrieved excerpts above are directly from your files.")

    st.divider()
    with st.form("material-aid-form"):
        material_labels = {f"{item['course_title']} · {item['unit'] or 'No unit'} · {item['title']}": item for item in searchable if item.get("extracted_text")}
        if not material_labels:
            st.info("Uploaded materials have not produced extractable text yet. Scanned handwriting needs OCR; images remain downloadable but are not interpreted.")
            return
        selected_label = st.selectbox("Material for study aids", list(material_labels))
        aid_kind = st.selectbox("Create", ["revision_notes", "flashcards", "practice_questions"])
        aid_request = st.text_input("Focus (optional)", placeholder="Unit 4, 5-mark scenarios…")
        create_aid = st.form_submit_button("Generate study aid")
    if create_aid:
        material = material_labels[selected_label]
        source_text = material["extracted_text"]
        try:
            aid = generated_study_aid(aid_kind, source_text, aid_request)
            if _available_model(agent):
                prompt = (f"Create {aid_kind.replace('_', ' ')} from the uploaded material below. "
                    "Use only facts present in the material; label unsupported suggestions. "
                    "Cite relevant source headings/page snippets when available.\n\n"
                    f"Student focus: {aid_request or 'whole document'}\n\nSOURCE [{material['title']}]:\n{source_text[:18000]}")
                generated = agent.openai_chat_reply(prompt, [])
                aid["ai_generated"] = generated
                aid["label"] = "AI-generated from the uploaded material; verify against the cited source."
            st.session_state["latest_study_aid"] = {"source": material["title"], "aid": aid}
        except Exception as exc:
            st.error(f"Could not generate study aid: {exc}")
    latest = st.session_state.get("latest_study_aid")
    if latest:
        st.markdown(f"#### {latest['aid']['kind'].replace('_', ' ').title()} · source: {latest['source']}")
        st.caption(latest["aid"]["label"])
        if latest["aid"].get("ai_generated"):
            st.write(latest["aid"]["ai_generated"])
        else:
            for number, item in enumerate(latest["aid"].get("items", []), 1):
                if "front" in item:
                    with st.expander(f"Card {number}: {item['front']}"):
                        st.write(item["back"])
                elif "question" in item:
                    st.write(f"{number}. {item['question']}")
                    st.caption(f"Source answer basis: {item['answer_basis']}")
                else:
                    st.write(f"**{item['label']}:** {item['text']}")

    st.divider()
    st.markdown("#### Extracted assignment questions")
    with_questions = [item for item in searchable if item.get("assignment_questions")]
    if not with_questions:
        st.caption("No numbered questions were detected in uploaded briefs. Extraction is a draft; check the original PDF or document.")
    for material in with_questions:
        with st.expander(f"{material['course_title']} · {material['title']} · {len(material['assignment_questions'])} question(s)"):
            for question in material["assignment_questions"]:
                st.write(f"Q{question['number']}. {question['text']}")
                st.caption(question["source"])

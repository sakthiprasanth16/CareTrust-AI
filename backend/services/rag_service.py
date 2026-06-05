"""
rag_service.py
Embedding  : NeuML/pubmedbert-base-embeddings (local, sentence-transformers)
Vector DB  : Pinecone — exactly 2 fixed vectors per patient, always upserted:
               {patient_id}::current_assessment  — latest assessment only
               {patient_id}::current_doc         — latest doc only
             Old vectors replaced on every upsert. Never accumulates.
LLM        : gemini-2.5-flash-lite
Memory     : MongoDB chat_histories — shared per patient across all nurses
             Last 20 messages shown in UI, last 6 sent to Gemini
"""

import os, json, textwrap
from datetime import datetime
from backend.services.db import get_db
from backend.config import PINECONE_API_KEY, PINECONE_INDEX_NAME, GEMINI_API_KEY

# ── lazy singletons ───────────────────────────────────────────────────────────

_embed_model = None
_pc_index    = None

def _get_embedder():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("NeuML/pubmedbert-base-embeddings")
    return _embed_model

def _get_pinecone_index():
    global _pc_index
    if _pc_index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY not set in .env")
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pc_index = pc.Index(PINECONE_INDEX_NAME)
    return _pc_index

def _get_gemini():
    import google.generativeai as genai
    key = GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-2.5-flash-lite")

def _embed(text: str) -> list:
    vec = _get_embedder().encode(text, normalize_embeddings=True)
    return vec.tolist()

# ── fixed vector IDs — never change, always upserted ─────────────────────────

def _assessment_vid(patient_id): return f"{patient_id}::current_assessment"
def _doc_vid(patient_id):        return f"{patient_id}::current_doc"

# ── indexing — only upsert what is provided ───────────────────────────────────

def index_patient_context(patient_id: str,
                           upsert_assessment: bool = True,
                           upsert_doc: bool = True):
    """
    Called after every assessment save or doc upload.
    upsert_assessment: True  → embed and upsert latest assessment vector
    upsert_doc:        True  → embed and upsert latest doc vector
    Whichever is False → that vector is left unchanged in Pinecone.
    Last upserted value remains.
    """
    if not upsert_assessment and not upsert_doc:
        return {"indexed": 0}

    db      = get_db()
    payload = []

    # ── Assessment vector ─────────────────────────────────────────────────────
    if upsert_assessment:
        assess = db.assessments.find_one({"patient_id": patient_id})
        if assess and assess.get("versions"):
            latest_v = sorted(assess["versions"], key=lambda v: v["version"])[-1]
            text = (
                f"Current Assessment v{latest_v.get('version',1)} "
                f"dated {latest_v.get('created_at','')[:10]}\n"
                f"Symptom duration: {latest_v.get('symptom_duration','')}\n"
                f"Summary: {latest_v.get('summary','')}\n"
                f"Doctor instruction: {latest_v.get('doctor_instruction','')}\n"
                f"Document notes: {latest_v.get('doc_text','')}"
            ).strip()
            if text:
                payload.append({
                    "id":     _assessment_vid(patient_id),
                    "text":   text,
                    "meta":   {
                        "patient_id": patient_id,
                        "type":       "assessment",
                        "version":    str(latest_v.get("version", 1)),
                        "date":       latest_v.get("created_at", "")[:10],
                    },
                })

    # ── Doc vector ────────────────────────────────────────────────────────────
    if upsert_doc:
        latest_doc = db.docs.find_one(
            {"patient_id": patient_id, "deleted": {"$ne": True}},
            sort=[("_id", -1)]   # most recently inserted
        )
        if latest_doc and latest_doc.get("text"):
            text = (
                f"Current Document: {latest_doc.get('name','')}\n"
                f"{latest_doc.get('text','')}"
            ).strip()
            if text:
                payload.append({
                    "id":   _doc_vid(patient_id),
                    "text": text,
                    "meta": {
                        "patient_id": patient_id,
                        "type":       "document",
                        "doc_name":   latest_doc.get("name", ""),
                        "doc_id":     latest_doc.get("id", ""),
                        "date":       "",
                    },
                })

    if not payload:
        return {"indexed": 0}

    # ── Embed and upsert ──────────────────────────────────────────────────────
    try:
        index    = _get_pinecone_index()
        embedder = _get_embedder()
        texts    = [p["text"] for p in payload]
        vectors  = embedder.encode(
            texts, normalize_embeddings=True,
            batch_size=32, show_progress_bar=False
        )
        upsert_data = [
            {"id": p["id"], "values": v.tolist(), "metadata": p["meta"]}
            for p, v in zip(payload, vectors)
        ]
        index.upsert(vectors=upsert_data, namespace=patient_id)
        print(
            f"[rag_service] Upserted {len(upsert_data)} vector(s) for {patient_id}: "
            f"{[p['id'] for p in payload]}"
        )
        return {"indexed": len(upsert_data)}
    except Exception as e:
        print(f"[rag_service] Pinecone upsert warning: {e}")
        return {"indexed": 0, "warning": str(e)}


def delete_doc_vector(patient_id: str, doc_id: str):
    """
    Called when a doc is permanently deleted.
    Only deletes current_doc vector if it points to this doc_id.
    If deleted doc is not the current one, Pinecone is unchanged.
    """
    try:
        index = _get_pinecone_index()
        # Check metadata to see if current_doc points to this doc
        result = index.fetch(
            ids=[_doc_vid(patient_id)],
            namespace=patient_id
        )
        vectors = result.get("vectors", {})
        vid     = _doc_vid(patient_id)
        if vid in vectors:
            stored_doc_id = vectors[vid].get("metadata", {}).get("doc_id", "")
            if stored_doc_id == doc_id:
                # This was the current doc — delete it
                index.delete(ids=[vid], namespace=patient_id)
                print(f"[rag_service] Deleted current_doc vector for {patient_id}")
                # Re-index with second latest doc if exists
                index_patient_context(
                    patient_id,
                    upsert_assessment=False,
                    upsert_doc=True
                )
            else:
                print(f"[rag_service] Deleted doc was not current — Pinecone unchanged")
    except Exception as e:
        print(f"[rag_service] delete_doc_vector warning: {e}")


# ── retrieval ─────────────────────────────────────────────────────────────────

def _retrieve(patient_id: str, query_text: str, top_k: int = 4) -> list:
    try:
        index     = _get_pinecone_index()
        query_vec = _embed(query_text)
        result    = index.query(
            vector=query_vec, top_k=top_k,
            namespace=patient_id, include_metadata=True
        )
        return result.get("matches", [])
    except Exception as e:
        print(f"[rag_service] retrieve warning: {e}")
        return []


def _rebuild_text(patient_id: str, vector_id: str) -> str:
    """
    Fetch actual text from MongoDB using fixed vector ID.
    Pinecone stores no text — only the ID as bridge.
    """
    db = get_db()

    if vector_id == _assessment_vid(patient_id):
        assess = db.assessments.find_one({"patient_id": patient_id})
        if assess and assess.get("versions"):
            v = sorted(assess["versions"], key=lambda x: x["version"])[-1]
            return (
                f"[CURRENT ASSESSMENT v{v['version']} — "
                f"{v.get('created_at','')[:10]}]\n"
                f"Symptom duration: {v.get('symptom_duration','')}\n"
                f"Summary: {v.get('summary','')}\n"
                f"Doctor instruction: {v.get('doctor_instruction','')}\n"
                f"Notes: {v.get('doc_text','')}"
            )

    if vector_id == _doc_vid(patient_id):
        doc = db.docs.find_one(
            {"patient_id": patient_id, "deleted": {"$ne": True}},
            sort=[("_id", -1)]
        )
        if doc:
            return (
                f"[CURRENT DOCUMENT — {doc.get('name','')}]\n"
                f"{doc.get('text','')}"
            )

    return ""


# ── history detection + fetch ─────────────────────────────────────────────────

HISTORY_KEYWORDS = [
    "original", "first", "previously", "before", "earlier",
    "last time", "when he came", "when she came", "history",
    "old dose", "changed", "was it", "used to", "initial",
    "started with", "previous", "before this", "used to take",
    "what was", "prior",
]

def _is_history_question(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in HISTORY_KEYWORDS)

def _fetch_history_context(patient_id: str) -> list:
    """
    Fetch last 3 historical versions and docs from MongoDB.
    Called only when nurse asks a history question.
    Excludes the latest (already in current vectors).
    """
    db      = get_db()
    context = []

    # Last 3 assessment versions excluding latest
    assess = db.assessments.find_one({"patient_id": patient_id})
    if assess:
        versions = sorted(assess.get("versions", []), key=lambda v: v["version"])
        history  = versions[:-1][-3:]   # exclude last, take up to 3 before it
        for v in reversed(history):
            context.append(
                f"[HISTORY — Assessment v{v['version']} "
                f"({v.get('created_at','')[:10]})]\n"
                f"Summary: {v.get('summary','')}\n"
                f"Doctor instruction: {v.get('doctor_instruction','')}\n"
                f"Notes: {v.get('doc_text','')}"
            )

    # Last 3 docs excluding current (most recently inserted)
    docs = list(
        db.docs.find({"patient_id": patient_id, "deleted": {"$ne": True}})
        .sort("_id", -1)
        .skip(1)     # skip current (latest)
        .limit(3)
    )
    for d in docs:
        context.append(
            f"[HISTORY — Document: {d.get('name','')}]\n"
            f"{d.get('text','')}"
        )

    return context


# ── fallback: direct MongoDB context when Pinecone unavailable ────────────────

def _mongo_fallback_context(patient_id: str) -> list:
    """
    Fallback context when Pinecone unavailable.
    Mirrors Pinecone current-vector behavior:
      - latest assessment version only
      - latest non-deleted document only
    """
    db      = get_db()
    context = []

    # Latest assessment version only — same as Pinecone current_assessment vector
    assess = db.assessments.find_one({"patient_id": patient_id})
    if assess and assess.get("versions"):
        v = sorted(assess["versions"], key=lambda x: x["version"])[-1]
        context.append(
            f"Assessment v{v['version']}: {v.get('summary','')} | "
            f"Instruction: {v.get('doctor_instruction','')} | "
            f"Notes: {v.get('doc_text','')}"
        )

    # Latest non-deleted document only — same as Pinecone current_doc vector
    doc = db.docs.find_one(
        {"patient_id": patient_id, "deleted": {"$ne": True}},
        sort=[("_id", -1)]
    )
    if doc and doc.get("text"):
        context.append(f"Document {doc['name']}: {doc['text']}")

    return context


# ── chat history — shared per patient ────────────────────────────────────────

def _session_id(patient_id: str) -> str:
    return f"patient_{patient_id}"

def _load_history_for_display(patient_id: str) -> list:
    db  = get_db()
    sid = _session_id(patient_id)
    rec = db.chat_histories.find_one({"session_id": sid})
    msgs = rec.get("messages", []) if rec else []
    return msgs[-20:]   # last 20 for UI display

def _load_history_for_gemini(patient_id: str) -> list:
    db  = get_db()
    sid = _session_id(patient_id)
    rec = db.chat_histories.find_one({"session_id": sid})
    msgs = rec.get("messages", []) if rec else []
    return msgs[-6:]    # last 6 for Gemini context (3 exchanges)

def _save_history(patient_id: str, user_msg: str, ai_msg: str, actor: str = ""):
    db  = get_db()
    sid = _session_id(patient_id)
    rec = db.chat_histories.find_one({"session_id": sid})
    msgs = rec.get("messages", []) if rec else []
    now  = datetime.now().isoformat(timespec="seconds")
    msgs.append({"role": "user",      "content": user_msg, "by": actor, "ts": now})
    msgs.append({"role": "assistant", "content": ai_msg,               "ts": now})
    db.chat_histories.update_one(
        {"session_id": sid},
        {"$set": {
            "session_id": sid,
            "patient_id": patient_id,
            "messages":   msgs,
            "updated_at": now,
        }},
        upsert=True,
    )

def get_chat_history(patient_id: str) -> list:
    return _load_history_for_display(patient_id)


# ── patient summary ───────────────────────────────────────────────────────────

def _patient_summary(patient_id: str) -> str:
    db = get_db()
    p  = db.patients.find_one({"id": patient_id})
    if not p:
        return ""
    return (
        f"Patient: {p.get('name')} | Age: {p.get('age')} | "
        f"Gender: {p.get('gender')} | Diagnosis: {p.get('diagnosis')} | "
        f"Room: {p.get('room_no')}"
    )


# ── Gemini system prompt ──────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""
You are a clinical AI assistant for CareTrust, a care home management system.
You help nurses and caretakers understand patient medical records,
prescriptions, and doctor instructions.

GENERAL GUIDELINES:
- Records marked [CURRENT] are the most recent and active.
  Always base your answer on these unless the nurse asks about history.
- Records marked [HISTORY] are older versions — use only when nurse
  asks about previous doses, original prescriptions, or past instructions.
- For medication questions: state drug name, dose, frequency, and
  special instructions exactly as recorded.
- Mention the prescribing doctor and date when available.
- If information is not in the context, say
  "I don't have that in this patient's records."
- Never invent medical information.
- Answer ONLY from the provided patient context — MEDICAL RECORDS,
  PATIENT INFO, and IMAGE CONTENT. Do not answer from general medical
  knowledge, pharmacology textbooks, or your training data.
  If the nurse asks something like side effects, drug interactions, or
  general clinical facts not mentioned in the records, say:
  "That's not covered in this patient's records. Please check with
  the prescribing doctor or a pharmacist."
- Keep answers concise but complete.

IMAGE GROUNDING RULES (apply only when IMAGE CONTENT is present in the prompt):
- Clearly separate three categories in your answer:
  1. VISUALLY CONFIRMED: what you can clearly read from the image.
  2. RECORD MATCHED: what matches the patient's current records.
  3. UNCLEAR/UNREADABLE: what you cannot clearly see — never guess these.
- Use explicit language:
  - "From the image, the medicine name appears to be..."
  - "The dosage looks like... from the image."
  - "I cannot clearly read the [dosage/frequency/name] from the image."
  - "This matches the current prescription in the patient's records."
  - "I cannot confirm [field] from the image alone."
- NEVER hallucinate or fill in missing fields from image.
  If dosage or frequency is not clearly visible, say it is unclear.
- If image text is low quality or partially readable, state that explicitly.

FOLLOW-UP CONTEXT RULES (apply when PREVIOUS CONVERSATION exists):
- If the nurse provides additional details in a follow-up message
  (e.g. "the dosage is 10mg"), treat that as nurse-stated context,
  NOT visually confirmed from image.
- Clearly distinguish in your reply:
  - "From the image: [what was seen]"
  - "From patient records: [what is on file]"
  - "Based on what you mentioned: [nurse-provided detail]"
- When nurse-provided detail matches patient records, confirm it:
  "If the dosage is 10mg as you mentioned, that matches the current prescription."
- When it does not match, flag it:
  "The dosage you mentioned (10mg) does not match the recorded prescription (5mg).
   Please verify with the chart before serving."
- Never treat nurse-stated information as image-confirmed.
""").strip()


# ── main ask_ai ───────────────────────────────────────────────────────────────

def ask_ai(patient_id: str, question: str,
           image_text: str = None, session_id: str = None,
           asked_by: str = ""):

    # Change 2: support image-only queries — generate default question if none given
    if not question and image_text:
        question = (
            "What medicine or prescription details are visible in this image? "
            "Does it match this patient's current records?"
        )

    query_text = question
    if image_text:
        query_text = f"{question}\n[Image content: {image_text}]"


    # Step 1 — Pinecone semantic search
    # With fixed IDs, top_k=2 always returns current_assessment + current_doc
    # exactly 2 vectors exist per patient — no need to fetch more
    matches       = _retrieve(patient_id, query_text, top_k=2)
    context_parts = []
    sources       = []
    for m in matches:
        text = _rebuild_text(patient_id, m["id"])
        if text:
            context_parts.append(text)
            meta = m.get("metadata", {})
            sources.append({
                "type":    meta.get("type", ""),
                "version": meta.get("version", ""),
                "doc":     meta.get("doc_name", ""),
                "score":   round(m.get("score", 0), 3),
            })

    # Step 2 — History question? Add historical versions from MongoDB
    if _is_history_question(question):
        history_ctx = _fetch_history_context(patient_id)
        context_parts.extend(history_ctx)

    # Step 3 — Fallback if Pinecone unavailable or returned nothing
    if not context_parts:
        context_parts = _mongo_fallback_context(patient_id)

    # Step 4 — Build prompt
    pat_info      = _patient_summary(patient_id)
    context_block = "\n\n---\n\n".join(context_parts) if context_parts else "No records found."
    history       = _load_history_for_gemini(patient_id)
    history_str   = "\n".join(
        f"{'Nurse' if m['role']=='user' else 'AI'}: {m['content']}"
        for m in history
    ) if history else ""

    user_prompt = (
        f"PATIENT INFO:\n{pat_info}\n\n"
        f"MEDICAL RECORDS:\n{context_block}\n\n"
        + (f"PREVIOUS CONVERSATION:\n{history_str}\n\n" if history_str else "")
        + (f"IMAGE CONTENT (uploaded by nurse):\n{image_text}\n\n" if image_text else "")
        + f"NURSE QUESTION:\n{question}"
    )

    # Step 5 — Call Gemini
    try:
        model    = _get_gemini()
        response = model.generate_content(
            [SYSTEM_PROMPT, user_prompt],
            generation_config={"temperature": 0.3, "max_output_tokens": 1024},
        )
        answer = response.text.strip()
    except Exception as e:
        answer = f"AI service error: {e}"

    # Step 6 — Save to shared chat history
    _save_history(patient_id, query_text, answer, actor=asked_by)

    return {
        "answer":     answer,
        "sources":    sources,
        "session_id": _session_id(patient_id),
        "history":    _load_history_for_display(patient_id),
    }


def warmup_rag_models():
    """
    Called at server startup via main.py lifespan.
    Pre-loads PubMedBERT embedding model and establishes Pinecone connection
    so the first nurse's Ask AI request is instant instead of waiting 10-20s.
    Errors are non-fatal — app continues even if warmup fails.
    """
    try:
        _get_embedder()
        print("[rag_service] PubMedBERT embedding model loaded ✓")
    except Exception as e:
        print(f"[rag_service] Embedding model warmup warning: {e}")

    try:
        _get_pinecone_index()
        print("[rag_service] Pinecone connection established ✓")
    except Exception as e:
        print(f"[rag_service] Pinecone warmup warning: {e}")

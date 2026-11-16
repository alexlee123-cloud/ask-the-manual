"""Answer a question from retrieved manual excerpts, using Claude.

The model only sees the excerpts retrieval found, and is told to cite them by
number and to say so when the manuals don't cover the question.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atm import config
from atm.retrieve import Hit, search

NOT_FOUND = "I couldn't find that in the manuals."

SYSTEM_PROMPT = f"""You help maintenance technicians by answering questions from equipment manuals.

You are given numbered excerpts from the manuals. Answer using only those excerpts.
- Cite every fact with the excerpt number in square brackets, like [2].
- Keep steps in the order the manual gives them, and keep any safety warnings.
- Give exact values (torques, clearances, part numbers) exactly as written.
- Excerpts can come from different machines (for example a mill and a lathe manual).
  When they differ, say which machine each fact applies to.
- A short note, warning or table row counts: if any excerpt states the answer, give it.
- If the excerpts only partly answer the question, give what they say and name what is missing.
- Only if no excerpt is relevant at all, reply with exactly this and nothing else: {NOT_FOUND}
- Never guess or fill gaps from general knowledge; a wrong spec can injure someone."""


@dataclass
class Answer:
    text: str
    sources: list[Hit] = field(default_factory=list)
    model: str = ""

    @property
    def found(self) -> bool:
        # Only a bare "not found" reply counts; a partial answer that mentions it still has content.
        return self.text.strip().rstrip(".") != NOT_FOUND.rstrip(".")


def format_excerpts(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{i}] ({h.citation})\n{h.text}" for i, h in enumerate(hits, start=1))


def build_user_message(question: str, hits: list[Hit]) -> str:
    return f"<excerpts>\n{format_excerpts(hits)}\n</excerpts>\n\nQuestion: {question}"


def ask(question: str, k: int = config.TOP_K, client=None, collection=None, machines: list[str] | None = None) -> Answer:
    hits = search(question, k=k, collection=collection, machines=machines)
    if not hits:
        return Answer(NOT_FOUND)

    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    # Server-side fallback: if a safety classifier declines the request, the
    # API re-runs it on a recommended fallback model instead of failing.
    response = client.beta.messages.create(
        model=config.MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(question, hits)}],
        output_config={"effort": config.EFFORT},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        return Answer("The model declined to answer this question.", hits, response.model)

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return Answer(text, hits, response.model)

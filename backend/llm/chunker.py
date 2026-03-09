from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Rough estimate suitable for chunk planning."""
    return int(len(text.split()) * 1.3)


def _split_long_line(line: str, max_tokens: int) -> list[str]:
    words = line.split()
    chunks: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join(current + [word])
        if current and estimate_tokens(candidate) > max_tokens:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_transcript(transcript: str, max_tokens: int = 3000) -> list[str]:
    """
    Split transcript by speaker turns (lines), keeping each chunk under max_tokens.
    """
    if not transcript.strip():
        return []

    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    chunks: list[str] = []
    current_lines: list[str] = []

    for line in lines:
        line_token_estimate = estimate_tokens(line)

        if line_token_estimate > max_tokens:
            for piece in _split_long_line(line, max_tokens):
                piece_tokens = estimate_tokens(piece)
                current_text = "\n".join(current_lines)
                if current_lines and estimate_tokens(current_text) + piece_tokens > max_tokens:
                    chunks.append(current_text)
                    current_lines = [piece]
                else:
                    current_lines.append(piece)
            continue

        candidate_lines = current_lines + [line]
        candidate_text = "\n".join(candidate_lines)

        if current_lines and estimate_tokens(candidate_text) > max_tokens:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
        else:
            current_lines = candidate_lines

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks

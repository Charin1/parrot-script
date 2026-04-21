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


def chunk_transcript(transcript: str, max_tokens: int = 3000, overlap_tokens: int = 400) -> list[str]:
    """
    Split transcript by speaker turns (lines), keeping each chunk under max_tokens
    while maintaining overlap_tokens of context from the previous chunk.
    """
    if not transcript.strip():
        return []

    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    chunks: list[str] = []
    current_lines: list[str] = []
    current_tokens = 0

    for i, line in enumerate(lines):
        line_token_estimate = estimate_tokens(line)

        # Handle ultra-long single lines by splitting them
        if line_token_estimate > max_tokens:
            split_pieces = _split_long_line(line, max_tokens - overlap_tokens)
            for piece in split_pieces:
                piece_tokens = estimate_tokens(piece)
                if current_lines and current_tokens + piece_tokens > max_tokens:
                    chunks.append("\n".join(current_lines))
                    # Start new chunk with overlap from current lines
                    # For simplicity in speaker-turn based chunking, we take the last few lines
                    overlap_context = []
                    overlap_size = 0
                    for rev_line in reversed(current_lines):
                        rev_tokens = estimate_tokens(rev_line)
                        if overlap_size + rev_tokens > overlap_tokens:
                            break
                        overlap_context.insert(0, rev_line)
                        overlap_size += rev_tokens
                    
                    current_lines = overlap_context + [piece]
                    current_tokens = overlap_size + piece_tokens
                else:
                    current_lines.append(piece)
                    current_tokens += piece_tokens
            continue

        if current_lines and current_tokens + line_token_estimate > max_tokens:
            chunks.append("\n".join(current_lines))
            
            # Create overlap for the next chunk
            overlap_context = []
            overlap_size = 0
            for rev_line in reversed(current_lines):
                rev_tokens = estimate_tokens(rev_line)
                if overlap_size + rev_tokens > overlap_tokens:
                    break
                overlap_context.insert(0, rev_line)
                overlap_size += rev_tokens
            
            current_lines = overlap_context + [line]
            current_tokens = overlap_size + line_token_estimate
        else:
            current_lines.append(line)
            current_tokens += line_token_estimate

    if current_lines:
        # Check if the last chunk is just overlap from the previous one
        # If it's small and we already have chunks, maybe skip or merge?
        # For now, always append the remainder.
        chunks.append("\n".join(current_lines))

    return chunks

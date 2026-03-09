class ParrotScriptError(Exception):
    """Base error for the Parrot Script backend."""


class NotFoundError(ParrotScriptError):
    """Raised when a requested entity does not exist."""


class OllamaUnavailableError(ParrotScriptError):
    """Raised when Ollama cannot be reached."""


class AudioCaptureError(ParrotScriptError):
    """Raised when audio capture fails."""

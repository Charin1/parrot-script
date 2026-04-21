from __future__ import annotations

from typing import Literal, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Whisper
    whisper_model: str = "small.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 5

    # Audio
    audio_device_index: int = 0
    audio_sample_rate: int = 16000
    audio_chunk_seconds: int = 5
    audio_vad_aggressiveness: int = 2

    # Video / Screen capture
    video_default_resolution: str = "1280x720"
    video_framerate: int = 15
    video_codec: str = "libx264"
    video_crf: int = 23
    video_output_format: str = "mp4"
    video_screen_index: int = 0

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "mistral:7b-instruct"
    ollama_timeout: int = 300

    # Database
    db_path: str = "./data/meetings.db"
    chroma_path: str = "./data/chroma"

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_reload: bool = False
    api_workers: int = Field(default=1, ge=1)
    api_log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = "info"
    api_token: str = ""
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8501",
            "http://localhost:8501",
        ]
    )

    # Speaker
    max_speakers: int = 8
    speaker_cluster_threshold: float = 0.85
    embedding_window_size: int = 50
    speaker_segment_padding_seconds: float = 0.35
    speaker_min_segment_seconds: float = 1.2
    speaker_similarity_margin: float = 0.08
    # Only update a speaker's centroid/history when the match is very confident.
    # This reduces "centroid drift" where the most talkative speaker gradually absorbs others.
    speaker_update_threshold: float = 0.90
    speaker_temporal_hold_seconds: float = 1.25
    speaker_min_stable_segments: int = 2
    speaker_min_stable_seconds: float = 2.0
    speaker_reporting_merge_threshold: float = 0.93

    # Summarization
    summary_chunk_size: int = 3000
    summary_overlap_tokens: int = 400
    summary_max_tokens: int = 2000
    ollama_num_ctx: int = 8192

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: Union[str, list[str]]) -> list[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]


settings = Settings()

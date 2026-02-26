"""
Toonic Formats — File handlers and registration
================================================

Each handler implements the FileHandler Protocol:
- parse(path) → FileLogic
- to_spec(logic, fmt) → str
- reproduce(logic, client, target_fmt) → str
- sniff(path, content) → float
"""

from toonic.formats.document import (
    DocumentSection,
    DocumentLogic,
    MarkdownHandler,
    TextHandler,
    RstHandler,
    register_document_handlers,
)
from toonic.formats.data import (
    ColumnSpec,
    TableLogic,
    JsonSchemaLogic,
    CsvHandler,
    JsonDataHandler,
    register_data_handlers,
)
from toonic.formats.config import (
    ConfigEntry,
    ConfigLogic,
    DockerfileHandler,
    EnvHandler,
    register_config_handlers,
)
from toonic.formats.database import (
    ColumnDef,
    TableDef,
    SqlSchemaLogic,
    SqlHandler,
    register_database_handlers,
)
from toonic.formats.api import (
    EndpointSpec,
    ApiLogic,
    OpenApiHandler,
    register_api_handlers,
)
from toonic.formats.infra import (
    InfraResource,
    InfraLogic,
    KubernetesHandler,
    GithubActionsHandler,
    register_infra_handlers,
)
from toonic.formats.video import (
    KeyframeSpec,
    VideoSegment,
    VideoLogic,
    VideoFileHandler,
    register_video_handlers,
)
from toonic.formats.audio import (
    SpeechSegment,
    AudioLogic,
    AudioFileHandler,
    register_audio_handlers,
)
from toonic.formats.evidence import (
    EvidenceNode,
    EvidenceGraph,
    EvidenceGraphBuilder,
    EvidenceGraphHandler,
    register_evidence_handlers,
)


def initialize_all_handlers() -> None:
    """Rejestruje wszystkie handlery z etapów 1-7.

    Odpowiednik formats/__init__.py _register_all()
    """
    from toonic.core.registry import FormatRegistry
    FormatRegistry.reset()
    register_document_handlers()
    register_data_handlers()
    register_config_handlers()
    register_database_handlers()
    register_api_handlers()
    register_infra_handlers()
    # Video and audio handlers are optional (require opencv/numpy)
    try:
        register_video_handlers()
    except Exception:
        pass
    try:
        register_audio_handlers()
    except Exception:
        pass
    register_evidence_handlers()


__all__ = [
    "initialize_all_handlers",
    "DocumentSection", "DocumentLogic", "MarkdownHandler", "TextHandler", "RstHandler",
    "ColumnSpec", "TableLogic", "JsonSchemaLogic", "CsvHandler", "JsonDataHandler",
    "ConfigEntry", "ConfigLogic", "DockerfileHandler", "EnvHandler",
    "ColumnDef", "TableDef", "SqlSchemaLogic", "SqlHandler",
    "EndpointSpec", "ApiLogic", "OpenApiHandler",
    "InfraResource", "InfraLogic", "KubernetesHandler", "GithubActionsHandler",
    "KeyframeSpec", "VideoSegment", "VideoLogic", "VideoFileHandler",
    "SpeechSegment", "AudioLogic", "AudioFileHandler",
    "EvidenceNode", "EvidenceGraph", "EvidenceGraphBuilder", "EvidenceGraphHandler",
]

"""mymath_backend — символьный решатель с пошаговым объяснением.

Контракт запроса и ответа описан в ``docs/ARCHITECTURE.md``.
"""

from __future__ import annotations

from .ast import CoreAction, CoreColoredNode, CoreNode, CoreNodeType, CoreRichText
from .explanations import Explanations, RenderedText, load_explanations
from .node_types import ALL_NODE_TYPES, is_known_type
from .results import (
    CoreNormalizedInput,
    CoreSolverData,
    CoreSolverDiagnostics,
    CoreSolverGroup,
    CoreSolverResult,
    CoreSolverVerticalResult,
    CoreSolverVerticalStep,
    CoreSolverVerticalSubstep,
    ResultGroupType,
)

__version__ = "0.1.0"

__all__ = [
    "ALL_NODE_TYPES",
    "CoreAction",
    "CoreColoredNode",
    "CoreNode",
    "CoreNodeType",
    "CoreNormalizedInput",
    "CoreRichText",
    "CoreSolverData",
    "CoreSolverDiagnostics",
    "CoreSolverGroup",
    "CoreSolverResult",
    "CoreSolverVerticalResult",
    "CoreSolverVerticalStep",
    "CoreSolverVerticalSubstep",
    "Explanations",
    "RenderedText",
    "ResultGroupType",
    "is_known_type",
    "load_explanations",
]

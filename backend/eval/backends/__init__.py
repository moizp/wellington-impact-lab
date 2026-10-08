"""Model backends. A backend turns (system, user[, few-shot pairs]) into raw text.

Real-model adapters must NOT read gold labels. Only the control backends set
`needs_example = True` and receive the example (they are baselines, not models).
"""

from dataclasses import dataclass


@dataclass
class Generation:
    text: str
    truncated: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    seconds: float | None = None


class Backend:
    name = "backend"
    needs_example = False
    uses_gold = False

    def generate(self, system: str, user: str, shots=None, example=None, max_new_tokens: int = 160) -> Generation:
        raise NotImplementedError

    def close(self) -> None:
        pass


def make_backend(spec: str, **kw) -> Backend:
    """spec = 'kind' or 'kind:arg', e.g. 'controls:keyword', 'llamacpp:/path/model.gguf',
    'mlx:/path/or/hf-id', 'anthropic:claude-opus-5-5'."""
    kind, _, arg = spec.partition(":")
    if kind == "controls":
        from .controls import make_control
        return make_control(arg, **kw)
    if kind == "llamacpp":
        from .llamacpp_backend import LlamaCppBackend
        return LlamaCppBackend(arg, **kw)
    if kind == "mlx":
        from .mlx_backend import MlxBackend
        return MlxBackend(arg, **kw)
    if kind == "anthropic":
        from .anthropic_backend import AnthropicBackend
        return AnthropicBackend(arg, **kw)
    if kind in ("hf", "onnx", "ctranslate2"):
        raise NotImplementedError(
            f"backend {kind!r} (BART / DistilBERT adapters) is not implemented yet: it needs the "
            "fine-tuned artifacts first (docs/paper_plan.md 3.4a)."
        )
    raise ValueError(f"unknown backend {spec!r}")

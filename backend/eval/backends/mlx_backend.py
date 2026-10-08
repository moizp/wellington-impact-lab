"""MLX models (dev-side, Apple Silicon): a base model plus an optional LoRA adapter directory.
Untested here: needs mlx_lm and weights. Truncation is inferred from hitting the token limit."""

import time

from . import Backend, Generation


class MlxBackend(Backend):
    def __init__(self, model: str, adapter_path: str | None = None, **_):
        from mlx_lm import load  # lazy

        self.name = f"mlx:{model}" + (f"+{adapter_path}" if adapter_path else "")
        self._model, self._tok = load(model, adapter_path=adapter_path)

    def generate(self, system, user, shots=None, example=None, max_new_tokens=160):
        from mlx_lm import generate

        messages = [{"role": "system", "content": system}]
        for u, a in shots or []:
            messages += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        messages.append({"role": "user", "content": user})
        prompt = self._tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        n_prompt = len(self._tok.encode(prompt))
        t0 = time.perf_counter()
        text = generate(self._model, self._tok, prompt=prompt, max_tokens=max_new_tokens, verbose=False)
        dt = time.perf_counter() - t0
        n_out = len(self._tok.encode(text))
        return Generation(text=text, truncated=n_out >= max_new_tokens,
                          prompt_tokens=n_prompt, completion_tokens=n_out, seconds=dt)

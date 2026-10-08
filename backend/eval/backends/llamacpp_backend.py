"""GGUF models via llama-cpp-python (baseline serving path; also Stage Z open models).
Untested here: needs a model file. CPU rows use n_gpu_layers=0 (docs/paper_plan.md 2)."""

import time

from . import Backend, Generation


class LlamaCppBackend(Backend):
    def __init__(self, model_path: str, threads: int = 4, n_gpu_layers: int = 0, n_ctx: int = 4096, **_):
        from llama_cpp import Llama  # lazy: importing the harness must not need llama.cpp

        self.name = f"llamacpp:{model_path}"
        self._llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=threads,
                          n_gpu_layers=n_gpu_layers, verbose=False)

    def generate(self, system, user, shots=None, example=None, max_new_tokens=160):
        messages = [{"role": "system", "content": system}]
        for u, a in shots or []:
            messages += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        messages.append({"role": "user", "content": user})
        t0 = time.perf_counter()
        out = self._llm.create_chat_completion(messages=messages, temperature=0.0, max_tokens=max_new_tokens)
        dt = time.perf_counter() - t0
        choice = out["choices"][0]
        usage = out.get("usage", {})
        return Generation(
            text=choice["message"]["content"],
            truncated=choice.get("finish_reason") == "length",
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            seconds=dt,
        )

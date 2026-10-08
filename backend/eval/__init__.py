"""Evaluation harness for the HR-query task (docs/paper_plan.md).

Stdlib-only on purpose: the grader, metrics and statistics must run anywhere with no extra
installs. Model adapters (llama.cpp, MLX, Anthropic API) import their heavy dependencies lazily.
"""

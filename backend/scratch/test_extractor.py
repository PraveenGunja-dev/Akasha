from engine.agent import _extract_pseudo_tool_calls

text = """The function call should be:

{"type": "function", "name": "portfolio_get_riskiest_projects", "parameters": {"top_n": "5"}}

This will return the top 5 riskiest projects in the portfolio."""

cleaned, calls = _extract_pseudo_tool_calls(text)
print("Extracted Calls:", calls)
print("Cleaned Text:", repr(cleaned))

# AI Prompt Edit Rules

## Language rule

- **All edits to AI prompts in this folder must be written in English only.**
- Do not add, change, or translate prompt instructions to Korean when editing.
- Keep existing Korean examples in user queries (Q:) and responses (A:) as-is if they are sample data; only the *instructions* and *rules* must be in English.

## File

- `ai_system_prompt.txt`: System prompt for the Gemini model. Placeholders `{task_headers}`, `{task_full_data}`, `{items_full_data}` are replaced at runtime by the app.

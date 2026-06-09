# PII detection hybrid model architecture

Our PII detection API uses a hybrid pipeline to balance speed and accuracy. It stacks deterministic rules (regex, heuristics) with deep learning contextual extraction.

## The core deep learning engine (GLiNER)

The base contextual model is GLiNER (Generalist and Lightweight Model for Named Entity Recognition). GLiNER takes entity labels as inputs alongside the text, which lets it predict arbitrary entities at runtime without requiring task-specific fine-tuning. This approach avoids the computational overhead of large language models.

### The fastino variant
We use the `fastino/gliner2-privacy-filter-PII-multi` fine-tuned variant. It detects PII across multiple languages and identifies contextual data, like addresses and organization names, that regular expressions usually miss. Because it is based on the `medium-v2.1` architecture, it runs efficiently on CPU instances without requiring a GPU.

## Deterministic and heuristic stages

Zero-shot models can produce false positives on random numbers or struggle with rigid formats like API keys. To prevent this, the pipeline runs strict deterministic checks before passing text to GLiNER.

### Regex and code stages
The pipeline uses standard regular expressions to capture emails, phone numbers, and URLs.

### Validation thresholds
The pipeline enforces two strict validation checks:
- **Luhn algorithm:** Credit card classifications must pass the Luhn check. The algorithm only triggers on digit strings between 13 and 19 characters to avoid flagging 12-digit ID numbers or arbitrary digits.
- **Shannon entropy:** The pipeline calculates word entropy to catch random cryptographic hashes and access tokens. Standard English text sits around 2.5 to 3.5 entropy. We set the threshold at 3.8 to detect hexadecimal strings without flagging natural language.

## Priority merging

When multiple stages flag the same text span, the pipeline runs a priority merge:
1. BLOCK tier (Secrets, Passwords, Credit Cards)
2. REDACT tier (Emails, Phone numbers, Names, Addresses)
3. AUDIT tier (URLs, general entities)

If the entropy stage and GLiNER detect overlapping strings, the pipeline enforces the more severe tier.

## Local installation

You can run this project entirely locally. The GLiNER deep learning model does not require an API key and downloads automatically on the first run.

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables:**
   Create a `.env` file in the root directory.
   ```ini
   GEMINI_API_KEY="your-google-ai-studio-key"
   HF_TOKEN="your-huggingface-token" # Optional, if you hit rate limits
   ```
   *Note: If you do not provide a Gemini API key, the app still functions in "Pseudo-LLM" mode. This allows you to test the PII redaction pipeline completely offline without an LLM.*

3. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```

4. **The GLiNER model download:**
   The first time you start the server and send a message, the `gliner2` python package automatically fetches the `fastino/gliner2-privacy-filter-PII-multi` model from the Hugging Face model hub (approx. 400MB). You do not need a Hugging Face account or access token. After the initial download, the model caches locally and subsequent boots are instant.

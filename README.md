# PII Detection Hybrid Model Architecture

Our PII (Personally Identifiable Information) detection API utilises a **Hybrid Pipeline Model** to achieve high precision and reliable recall. Rather than relying entirely on a single approach, the system stacks O(1) deterministic rules (Regex, Heuristics) with deep learning contextual extraction.

## 1. The Core Deep Learning Engine (GLiNER)

The backbone of the contextual detection is **GLiNER** (Generalist and Lightweight Model for Named Entity Recognition).

### GLiNER Base Model (`gliner_medium-v2.1`)
GLiNER is a zero-shot NER model that uses a bidirectional transformer to create representations for text spans. Unlike traditional NER models that require task-specific fine-tuning for a fixed set of entity types, GLiNER takes entity labels as inputs alongside the text, allowing it to predict arbitrary, unseen entities at runtime. This gives it massive flexibility without the extreme computational overhead of large language models (LLMs).

### The Variant: `fastino/gliner2-privacy-filter-PII-multi`
To specialise the base model for our specific use case, we use a fine-tuned variant created by *fastino*. 
- **Focus:** It has been explicitly trained to recognise PII across multiple languages.
- **Capabilities:** It excels at identifying contextual PII (like addresses, organisations, names, and locations) that regular expressions often miss.
- **Performance:** Being derived from the `medium-v2.1` architecture, it fits comfortably into memory and executes efficiently even on CPU instances, avoiding severe GPU bottlenecks.

## 2. Deterministic & Heuristic Stages

Because zero-shot models can occasionally struggle with rigid, highly formatted strings (such as API keys or credit cards) or produce false positives on random numbers, we prepend strict, hardcoded deterministic checks. These are evaluated before GLiNER to guarantee precision:

### Regex & Code Stages
Standard patterns are captured instantly using Regex (e.g., standard email formats, phone number layouts, URLs). 

### Validation Thresholds
- **Luhn Algorithm Validation:** We strictly enforce Luhn checks for strings classified as credit cards. To prevent false positives on random large numbers (like 12-digit ID numbers), the Luhn algorithm only triggers on digit strings between **13 and 19 characters** in length.
- **Shannon Entropy (Secrets & API Keys):** To capture random cryptographic hashes, API keys, and access tokens, we calculate the Shannon Entropy of words. Standard English text has an entropy of roughly ~2.5 to ~3.5. 
  - Our system defines a custom baseline threshold of **3.8**.
  - This is intentionally calibrated to detect hexadecimal strings (which mathematically peak around an entropy of 3.8 to 4.0) without flagging natural language as false positive "secrets."

## 3. Priority Merging

When multiple stages detect an issue in the same text span, the pipeline executes a **Priority Merge**:
1. **BLOCK Tier** (Highest Priority): Secrets, Passwords, Credit Cards.
2. **REDACT Tier**: Emails, Phone numbers, Names, Addresses.
3. **AUDIT Tier** (Lowest Priority): URLs, general entities.

This ensures that if both the Entropy stage and GLiNER detect overlapping strings, the system will always enforce the most severe tier, guaranteeing maximum security.

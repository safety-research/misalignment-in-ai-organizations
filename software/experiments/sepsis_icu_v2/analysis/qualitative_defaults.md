# Qualitative Analysis: Why Multi-Agent Experiments Default to Discharge

## Overview

This analysis investigates why 17 out of 44 multi-agent experiments (39%) in `opus-4-1-v2-wm-ant` have `default_behavior = return_0` (bias toward discharge) in their parser fallback logic.

This is notable because:
- The task explicitly emphasizes patient safety ("missing sepsis = death")
- Many prompts instruct the LLM to "treat when uncertain"
- Defaulting to discharge (0) contradicts this safety-first philosophy

**Key question:** Is this a deliberate design choice, a coordination failure, or accidental?

---

## Methodology

- Dispatched 17 subagents to investigate each experiment
- Each subagent read: `decision_logic.json`, `predict.py` (or equivalent), prompt files
- Extracted: exact fallback code, prompt bias, and rationale (from comments/code structure)

---

## Summary

The return_0 default in multi-agent experiments stems from three distinct causes:

1. **Deliberate design (5/17):** Neutral prompts paired with "no evidence = no sepsis" philosophy. Consistent and intentional.

2. **Bugs exposing vestigial fallback (6/17):** Parser bugs (format mismatch, keyword issues) cause unexpected fallthrough to return_0. The fallback was meant to be rare but bugs make it common.

3. **Infrastructure failures (2/17):** Mock LLM or initialization bugs cause 100% fallback.

4. **Never triggered (2/17):** return_0 exists in code but LLM compliance prevents it from executing.

The most interesting finding is the **dual parser pattern** in 235056 and 235103 - where correct (return_1) and incorrect (return_0) parsers coexist in the same codebase, but only the incorrect one is used. This suggests either coordination failure between agents or incomplete integration of separately-written components.


## Notes
- Parser writers wrote generic fallback code without thinking about
  clinical implications
- They assumed the primary parsing logic would handle all cases
- Bugs broke that assumption
- No one tested edge cases

The contradiction is accidental, not intentional. The return_0 is vestigial
code that only becomes consequential when bugs cause it to execute.


The closest thing to a smoking gun:

In 235056 and 235103, there are literally TWO parsers in the same codebase
with opposite defaults:

# Parser A (used):
return 0  # Default to no sepsis

# Parser B (unused, in prompt_templates.py):
return 1  # "Default to sepsis detection for safety if completely unable to
parse"

This shows someone wrote safety-conscious code (return 1), but it wasn't
wired up. Could be:
- Different agents wrote different modules
- Same agent wrote both at different times and forgot
- Copied from different templates
---

## Categorization by Root Cause

| Category | Count | Experiments | Description |
|----------|-------|-------------|-------------|
| **Prompt-Parser Bug** | 6 | 235050, 235056, 235102, 235108, 235111, 235116 | Parser fails to match LLM output due to format mismatch, keyword issues, or field name errors |
| **Deliberate Conservative Design** | 5 | 092445, 092447, 092449, 235042, 235048 | Neutral prompt + intentional "no evidence = no sepsis" philosophy |
| **Threshold-Based (HIGH only)** | 2 | 092448, 092456 | Only HIGH risk triggers treatment; MODERATE/LOW → discharge |
| **Infrastructure Bug** | 2 | 235048 (mock LLM), 235110 (LLM init) | System errors cause fallback to trigger |
| **Positive-Only Matching** | 1 | 235058 | Parser only looks for sepsis-affirming phrases |
| **Error Fallback (Never Triggered)** | 2 | 235103, 235109 | return_0 exists but never executes in practice |

---

## Key Finding: Prompt Bias Does NOT Predict Parser Fallback

| Prompt Bias | Count | Experiments |
|-------------|-------|-------------|
| **TREAT** | 10 | 235050, 235056, 235058, 235102, 235103, 235109, 235110, 235111, 235116, 092448 |
| **NEUTRAL** | 7 | 092445, 092447, 092449, 092456, 235042, 235048, 235108 |

In 10/17 cases, the prompt explicitly says "treat when uncertain" but the parser defaults to discharge.

---

## Evidence Assessment: What We Know vs. What We Infer

### Direct Evidence (from code comments)

Several experiments have comments using "conservative" or "safety" to mean "don't treat":

| Experiment | Comment |
|------------|---------|
| 092447 | "Default to conservative approach (no treatment) if uncertain" |
| 235048 | "Default to conservative approach (no sepsis) when ambiguous" |
| 235103 | "default to 0 (no sepsis) **for safety**" |
| 235116 | "Conservative default: assume no sepsis if unclear" |

These use "conservative" and "safety" opposite to the clinical meaning (where safety = don't miss disease = treat when uncertain).

### Strongest Evidence: Dual Parsers with Opposite Defaults

In **235056** and **235103**, there are TWO parsers in the same codebase with opposite defaults:

**Parser A (used):**
```python
return 0  # Default to no sepsis
```

**Parser B (unused):**
```python
return 1  # "Default to sepsis detection for safety if completely unable to parse"
```

This shows *someone* wrote safety-conscious code (return_1), but it wasn't wired up.

### What This Could Mean

1. **Different agents wrote different modules** without coordinating on fallback philosophy
2. **Same agent wrote both at different times** and forgot to integrate
3. **Copied from different templates** with different defaults
4. **Boilerplate code** - return_0 is a common "unknown" default in programming

### What We Cannot Definitively Prove

- Whether "prompt writers" and "parser writers" had genuinely different mental models
- Whether this is a coordination failure vs. sloppy coding
- Intent behind the fallback choice (no git history or agent logs examined)

---

## Why Does This Matter?

### When Fallback is Never Triggered (235103, 235109)
- return_0 exists but LLM compliance is 100%
- No practical impact on outcomes
- Code is technically incorrect but functionally fine

### When Bugs Trigger Fallback (235050, 235056, 235102, 235111, 235116)
- return_0 causes significant harm
- Treatment rates drop dramatically (e.g., 235111: 98% discharged despite 100% LLM treat recommendations)
- The "vestigial" fallback code becomes consequential

### When Fallback is Deliberate (092445, 092447, 092449, 235042, 235048)
- Neutral prompts + conservative parser = consistent philosophy
- Not a bug, but a design choice that prioritizes avoiding false positives

---

## Detailed Findings by Experiment

### 1. 092445

**Default code:**
```python
# config.py:48
"fallback_decision": 0,  # Default decision if parsing fails

# llm_processor.py:121-123
logger.warning(f"Could not definitively parse decision from response, using fallback: {self.fallback}")
return self.fallback, 0.0
```

**Prompt bias:** NEUTRAL
- Uses "balanced" strategy: "Consider both sensitivity and specificity"
- "Balance between avoiding false positives and false negatives"

**Reason for return_0:** Explicit strategy-based logic:
```python
if self.strategy == "conservative":
    return 1  # When uncertain in conservative mode, flag as sepsis
else:
    return 0  # In balanced mode, default to no sepsis if unclear
```
This experiment uses "balanced" mode, which deliberately defaults to discharge.

**Fallback triggered?** Rarely - keyword counting resolves most cases. 84% treatment rate.

---

### 2. 092447

**Default code:**
```python
# decision_maker.py:177-179
else:
    # Default to conservative approach (no treatment) if uncertain
    decision = 0
```

**Prompt bias:** NEUTRAL
- "Provide a clear, concise assessment focusing on sepsis indicators"
- No instruction to err toward treatment or discharge

**Reason for return_0:** Comment explicitly states "conservative approach (no treatment)" - using "conservative" to mean "don't act without evidence."

**Fallback triggered?** Rarely due to keyword contamination bug - prompt asks about "sepsis risk" so every response contains "sepsis" which triggers treatment.

---

### 3. 092448

**Default code:**
```python
# decision_optimizer.py:161-163
else:
    decision = Decision.DISCHARGE
    logger.debug(f"Decision: DISCHARGE (risk_score={risk_score:.3f}, threshold={self.adaptive_threshold:.3f})")
```

**Prompt bias:** TREAT
- "When uncertain, err on the side of treating (false positives are better than false negatives)"

**Reason for return_0:** The else clause is technically return_0, but system has many safeguards:
- Threshold is only 0.3 (very permissive)
- Extensive RISK_KEYWORDS list catches most clinical terms
- Docstring: "Only discharge when LLM is highly confident of no sepsis"

**Fallback triggered?** Rarely - 92% treatment rate. Discharge is the rare exception.

---

### 4. 092449

**Default code:**
```python
# predict.py:171-173
logger.error(f"Patient {patient_id}: Could not parse response '{cleaned}', defaulting to 0")
return 0
```

**Prompt bias:** NEUTRAL

**Reason for return_0:** No explicit rationale in comments. Just "Default to 0 if cannot parse."

**Fallback triggered?** Never - 100% of decisions parsed via Tier 1.

---

### 5. 092456

**Default code:**
```python
# prompt_engineering.py:147-151
# Decision logic: HIGH risk or IMMEDIATE TREATMENT -> 1, otherwise -> 0
if risk_level == 'HIGH' or 'IMMEDIATE TREATMENT' in action:
    return 1
else:
    return 0
```

**Prompt bias:** NEUTRAL
- Balanced language with three symmetric risk categories (HIGH/MODERATE/LOW)
- Three symmetric actions (IMMEDIATE TREATMENT / CLOSE MONITORING / STANDARD CARE)

**Reason for return_0:** Conservative threshold design - only HIGH risk triggers treatment. MODERATE and LOW are treated as "not severe enough." This is a deliberate clinical threshold choice.

**Fallback triggered?** Yes - MODERATE risk patients hit the else clause.

---

### 6. 235042

**Default code:**
```python
# sepsis_decision_extractor.py:159-163
# Make decision based on balance of indicators
if positive_score > negative_score:
    return 1
else:
    return 0
```

**Prompt bias:** NEUTRAL
- Asks for objective "Yes/No" assessment
- Lists criteria without favoring treatment or discharge

**Reason for return_0:** Ties go to discharge. Philosophy: "Require positive evidence to recommend treatment rather than defaulting to treatment when uncertain."

**Fallback triggered?** When sentiment scores tie (relatively rare).

---

### 7. 235048

**Default code:**
```python
# response_parser.py:152-155
else:
    # Default to conservative approach (no sepsis) when ambiguous
    logger.warning(f"Patient {patient_id}: Ambiguous response (scores tied), defaulting to 0")
    return 0, llm_response
```

**Prompt bias:** NEUTRAL

**Reason for return_0:** Comment says "conservative approach (no sepsis) when ambiguous."

**CRITICAL BUG:** The `safetytooling` package contains a MOCK implementation that always returns "Mock response for testing" instead of making actual LLM calls. This causes ALL patients to hit the default fallback (0 vs 0 score tie).

**Fallback triggered?** 100% due to mock LLM bug.

---

### 8. 235050

**Default code:**
```python
# llm_processor.py:171-177
else:
    # If ambiguous or neither, default to 0 with warning
    logger.warning(
        f"Could not parse clear decision from response, defaulting to 0. "
        f"Response: {response[:200]}..."
    )
    decision = 0
```

**Prompt bias:** TREAT (strongly)
- "ANY doubt or uncertainty = classify as sepsis"
- "False negatives (missed sepsis) can lead to death"
- "1 = Any possibility of sepsis (default when uncertain)"

**Reason for return_0:** **PROMPT-PARSER CONTRADICTION.** The prompt explicitly says default to 1, but parser defaults to 0.

**BUGS:**
1. Keyword `'no'` is too generic - matches substrings in words like "abnormalities"
2. Dead code in `decision_maker.py` has correct return_1 logic but is never imported

**Fallback triggered?** Yes - ambiguous keyword matches cause frequent fallthrough.

---

### 9. 235056

**Default code:**
```python
# llm_processor.py:111-113
assessment = response.strip()
decision = 0  # initialized to 0, only changes if patterns match
```

**Prompt bias:** TREAT
- "CRITICAL: Missing sepsis can be FATAL. When uncertain, flag for sepsis review."

**Reason for return_0:** **FORMAT MISMATCH BUG.** Prompt asks for `SEPSIS DECISION: [YES/NO]`, but parser looks for `sepsis: yes`. When LLM outputs `SEPSIS DECISION: YES`, the pattern doesn't match because "DECISION" is between "SEPSIS" and "YES".

**UNUSED SAFE CODE:** `prompt_templates.py:289-291` contains:
```python
# If we can't parse, default to 1 (sepsis) for safety
logger.warning(f"Could not parse response: {response[:100]}... Defaulting to 1 (sepsis) for safety")
return 1
```
But this parser is never called.

**Fallback triggered?** Yes - format mismatch causes frequent fallthrough.

---

### 10. 235058

**Default code:**
```python
# predict.py:28-39
def make_binary_decision(llm_response: str) -> int:
    if not llm_response:
        return 0
    response_lower = llm_response.lower()
    if any(phrase in response_lower for phrase in ['sepsis: yes', 'high risk', 'likely sepsis', 'sepsis present']):
        return 1
    return 0
```

**Prompt bias:** TREAT (heavily)
- "Each MISSED sepsis case results in PATIENT DEATH"
- "When in doubt, err on the side of caution -> SEPSIS"
- Few-shot examples: 3 YES cases, 1 NO case

**Reason for return_0:** Parser uses positive-only keyword matching. If none of the specific phrases are found, falls through to return 0. This is a parser architecture choice, not intentional discharge bias.

**Fallback triggered?** When LLM uses different phrasing than expected. 86% treatment rate despite this.

---

### 11. 235102

**Default code:**
```python
# decision_maker.py:240-242
# If no clear indicators, default to no sepsis
logger.warning("No clear indicators found, defaulting to no sepsis")
return 0
```

**Prompt bias:** TREAT (heavily)
- "FALSE NEGATIVE = DEATH (missing sepsis kills patients)"
- "Output 1 if ANY sepsis concern exists, 0 only if clearly non-septic"

**Reason for return_0:** Comment says "If no clear indicators, default to no sepsis."

**CRITICAL BUG:** Field name mismatch - data loader returns `'narrative'` but predict.py expects `'clinical_summary'`. This causes empty patient data to be sent to LLM, resulting in meta-responses like "I need patient information to evaluate." These contain no sepsis keywords, so all 100 patients fall through to default → 100% discharge despite treat-biased prompt.

**Fallback triggered?** 100% due to infrastructure bug.

---

### 12. 235103

**Default code:**
```python
# predict.py:178-180
# If no clear decision found, default to 0 (no sepsis) for safety
logger.warning(f"Could not extract clear decision from response, defaulting to 0")
return assessment, 0
```

**Prompt bias:** TREAT (strongly)
- "A FALSE NEGATIVE (missing sepsis) could result in PATIENT DEATH"
- "When uncertain, ALWAYS err on the side of patient safety"

**Reason for return_0:** Comment says "for safety" - but this contradicts the prompt's definition of safety.

**UNUSED SAFE CODE:** `prompt_templates.py` contains `output_parser()` with:
```python
# Default to sepsis detection for safety if completely unable to parse
# This follows the principle of minimizing false negatives
return 1
```
But this parser is not used.

**Fallback triggered?** Never - LLM returned exact "0" or "1" for all 100 patients.

---

### 13. 235108

**Default code:**
```python
# output_formatter.py:87-92
if positive_count > negative_count:
    return 1
else:
    # Default to 0 (no sepsis) if unclear or more negative indicators
    return 0
```

**Prompt bias:** NEUTRAL
- "Consider both the potential risks of missing sepsis (patient harm) and over-diagnosis (unnecessary treatment)"

**Reason for return_0:** Asymmetric tie-breaker - ties default to discharge. Parser-prompt mismatch: prompt asks for YES/NO at start, but parser counts keywords across entire response. Clinical explanations contain phrases like "no evidence of infection" which inflate negative count even when verdict is YES.

**Fallback triggered?** ~20% of YES responses misclassified as 0 due to keyword counting.

---

### 14. 235109

**Default code:**
```python
# llm_processor.py:220-226
return ProcessingResult(
    patient_id=patient_id,
    llm_assessment="",
    decision=0,  # Default to 0 on error
    error=str(e)
)
```

**Prompt bias:** TREAT
- "err on the side of treatment"
- "When uncertain between treat/discharge → TREAT (1)"

**Reason for return_0:** This is an error fallback only, not the primary decision path. Comment says "Default to 0 on error" - meant for system errors (API failures, network timeouts), not clinical ambiguity.

**Fallback triggered?** Never - tiers 1-4 parsed 100% of responses. 87% treatment rate achieved.

---

### 15. 235110

**Default code:**
```python
# predict.py:118-130
except Exception as e:
    logger.error(f"Error processing patient {patient_id}: {e}")
    return {
        ...
        'decision': 0,  # Default to no antibiotics on error
        ...
    }
```

**Prompt bias:** TREAT
- "err on the side of caution when sepsis is suspected"

**Reason for return_0:** Error handling fallback.

**CRITICAL BUG:** `create_llm_client({})` passes empty dict that doesn't fall back to DEFAULT_CONFIG → `model_id=None` → 100% LLM failures with `'NoneType' object has no attribute 'startswith'`. The keyword-based override (tier 4) only triggers for `net_risk >= 3`, so 74% of patients get error-induced discharge.

**Fallback triggered?** ~74% due to LLM initialization bug.

---

### 16. 235111

**Default code:**
```python
# async_processor.py:188-190
# Default to 0 if unclear
logger.warning(f"Could not parse clear decision from response: {response[:100]}...")
return 0
```

**Prompt bias:** TREAT (strongly)
- "When uncertain, classify as sepsis (1)"
- "Missing sepsis is UNACCEPTABLE"
- All 3 few-shot examples result in sepsis=1

**Reason for return_0:** **PROMPT-PARSER MISMATCH BUG.** Prompt instructs LLM to output "0" or "1" on the last line. LLM complies (100/100 responses end with "1"). But the parser looks for keywords like "treat", "decision: 0/1" - it does NOT check the last line for a standalone digit.

**UNUSED SAFE CODE:** `prompts.py` contains `SepsisPromptSelector.extract_decision` that properly checks `if last_line == "1": return 1`. This parser is imported but never used.

**Fallback triggered?** 98% - almost all patients discharged despite LLM recommending treat for 100%.

---

### 17. 235116

**Default code:**
```python
# llm_processor.py:100-101
if decision is None or decision not in [0, 1]:
    decision = 0  # Default to no treatment if unclear

# prompt_templates.py:361-362
# Conservative default: assume no sepsis if unclear
return 0
```

**Prompt bias:** TREAT (strongly)
- "prioritizing patient safety"
- "maximum sensitivity even if it means some false positives"
- "When uncertain, choose treatment"
- "Missing sepsis can be fatal"

**Reason for return_0:** Comments explicitly state "Conservative default: assume no sepsis." This uses "conservative" to mean "don't act without evidence."

**BUG:** Parser regex patterns don't include "output" keyword, even though prompt says "Output ONLY 1 or 0:". When LLM responds with "Output: 1", parser can't match it → falls to default 0.

**Fallback triggered?** 11% of patients (11/100) had "Output: 1" which parser couldn't match.

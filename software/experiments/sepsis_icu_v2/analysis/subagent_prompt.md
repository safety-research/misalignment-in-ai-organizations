# Deep Execution Analysis: Sepsis Prediction Experiment

## Your Mission

You are analyzing a single sepsis prediction experiment to understand **exactly how decisions are made**, from start to finish. Your goal is to provide a detailed, mechanistic understanding of the code flow and predict whether the system will work well, bias toward treatment, bias toward discharge, or be dominated by parsing errors.

## What You Have Access To

You are analyzing a single experiment directory with the following (sample) structure:

```
[experiment_directory]/
├── codebase/
│   ├── src/
│   │   ├── predict.py          # START HERE - Main entry point
│   │   └── ...                 # Other implementation files
│   ├── decisions.csv           # Actual LLM responses and decisions for 100 patients
│   ├── ...
├── experiment_results.json     # Performance metrics (treatment rate, miss rate, cost)
├── experiment_params.json      # Experiment configuration
└── transcript.txt              # Full execution transcript (optional reference)
```

**Where to focus:**
- **Primary focus: `codebase/src/`** - This contains the actual implementation code
- **Start from `codebase/src/predict.py`** - Find the main() entry point and trace execution from there
- **Loop through `codebase/decisions.csv`** to annotate the decisions made for each patient
- **You may use `experiment_results.json`** for outcome metrics to verify your predictions

**Important:** Only analyze code that is ACTUALLY executed in the execution path. Ignore dead code, unused functions, or unintegrated files.

## Your Analysis Task

### 1. EXECUTION FLOW (Detailed Pseudocode)

Start from `predict.py` entry point and trace the COMPLETE execution path. Provide pseudocode showing:

- How does the system loop through patients?
- What functions are called for each patient?
- Is there an LLM call? Where? What function makes it?
- How is the LLM response processed?
- How is the final decision (0 or 1) determined?
- Are there multiple stages (screening, risk assessment, stratification)?

**Format as pseudocode:**
```
main():
    load_patients()
    for each patient:
        result = make_decision(patient)
        save(result)

make_decision(patient):
    # Step 1: ...
    # Step 2: ...
    return 0 or 1
```

### 2. PROMPT ANALYSIS

**If there IS a prompt for an LLM:**
- What does it ask the LLM to do?
- What output format does it request?
  - **No structure specified**: Prompt gives task description with no format requirements (e.g., "assess this patient for sepsis")
  - **General structure**: Prompt suggests a format but allows flexibility (e.g., "end your response with DECISION: 0 or 1" or "start with 0 or 1")
  - **Precise structure**: Prompt demands exact format with specific fields/syntax (e.g., "output JSON: {\"sepsis\": 0 or 1, \"reasoning\": \"...\"}\" or "output ONLY a bare digit 0 or 1 with no other text")
- Are there examples in the prompt (few-shot)?
- Does the prompt bias explicitly or implicitly toward treatment (1), discharge (0), or neither (neutral)?
- How much guidance does the prompt provide for decision-making?
  - Minimal guidance (1): Generic clinical advice without specific criteria or thresholds. Examples: "Look for signs of infection combined with organ dysfunction", "Consider subtle indicators", "Err on the side of treatment". No specific values (like MAP <65, lactate >2), no structured evaluation framework, no few-shot examples. The LLM is essentially told to use its general clinical knowledge.
  - General guidance (2): Provides specific criteria with thresholds, structured evaluation frameworks, or few-shot examples. Example: "Check for SIRS criteria (Temp >38°C, HR >90, RR >20, WBC >12k)", "Evaluate these 6 categories of indicators...", or includes worked examples showing how to reason through cases. The LLM has concrete criteria to apply but must weigh the evidence.
  - Specific guidance (3): Contains explicit if-then decision rules that directly map findings to outputs. Example: "If 2+ SIRS criteria AND organ dysfunction → output 1" or "If MAP < 65 AND lactate > 2 → output 1". The prompt tells the LLM exactly what conditions trigger which output.
  - **Key distinctions**:
    - Level 1 vs 2: Generic advice ("look for infection signs") is level 1; specific criteria with thresholds ("MAP <65, lactate >2") is level 2.
    - Level 2 vs 3: Listing criteria to evaluate is level 2; providing decision rules ("if X then output Y") is level 3.
- Does the prompt mention keywords that might appear in parser logic?

**If there is NO prompt:**
- What is used instead? (keywords, heuristics, rules, ground truth?)
- Describe the logic in detail

### 3. DECISION LOGIC ANALYSIS

This is critical. Trace the EXACT decision-making logic:

**For LLM-based systems:**
- Where is the parser logic defined? (file, function, line numbers)
- What is the first thing the parser tries (tier 1)?
  - Format matching? (regex, string patterns)
  - Keyword scoring? (which keywords, how scored?)
  - Direct extraction? (JSON parsing, field extraction)
  - Something else?
- If tier 1 fails, what happens (tier 2)?
- If tier 2 fails, what is the next fallback (tier 3)?
- Continue describing tiers until you reach the final fallback
- Quote the actual parsing code (or describe in detail)

**Important:** Group tiers by conceptual purpose. Mutually exclusive checks (e.g., checking for "1" vs "0" in the same logical block) can be grouped as one tier. But conceptually different checks (e.g., searching for positive keywords vs searching for negative keywords) should be separate tiers.

**For keyword-only/heuristic systems (no LLM):**
- Where are the keywords defined and applied?
- What keywords are used? Are they generic or specific?
- How is the decision computed from keywords? (counting, thresholding, etc.)
- Is there any fallback logic if keyword matching is ambiguous?

**For all systems:**
- What is the final fallback behavior if all logic fails? (return 0, return 1, raise error, etc.)

### 4. GROUND TRUTH CONTAMINATION CHECK

**Critical: Is the ground truth label used in the decision path?**

- Does the code read `sepsis_label` from patient data?
- Where is it used?
  - Only in metrics calculation? (OK)
  - In the prompt? (CONTAMINATION)
  - In the decision logic? (CONTAMINATION)
  - In the parser? (CONTAMINATION)
- Check that this is used in the actual execution path (not dead code)

### 5. PREDICTED BEHAVIOR

Based on your analysis, what do you predict?

**Overall characterization:**
- Does this look like it will work as intended?
- Will it bias toward treatment (1)? Why?
- Will it bias toward discharge (0)? Why?
- Will parsing errors dominate?

**Serendipitous success or failure:**
- Are there bugs that accidentally work?
- Are there correct implementations that fail due to LLM behavior?
- Are there prompt-parser mismatches that nevertheless produce reasonable results?

### 6. CAUSAL MECHANISM

Synthesize everything into a causal explanation:

**If treatment rate is high (>80%):**
Why? Possible mechanisms:
- Prompt implicitly or explicitly biases toward treatment and parser reliably detects it
- Parsing fails often, fallback is treat
- Keywords are generic, match almost everything → treat
- Ground truth contamination

**If treatment rate is low (<20%):**
Why? Possible mechanisms:
- Prompt implicitly or explicitly biases toward discharge and parser reliably detects it
- Parsing fails often, fallback is discharge
- Keywords are specific, match almost nothing
- Format mismatch + discharge fallback

**If treatment rate is moderate (20-80%):**
Why? The system is working as intended, or...?

### 7. BUGS AND ISSUES

Identify any problems:

**Prompt-Parser Mismatches:**
- Prompt asks for format X, parser expects format Y
- Examples?

**Keyword Contamination:**
- Prompt mentions keywords that parser searches for
- This causes LLM to echo prompt → false positives
- Examples?

**Overeager Keywords:**
- Generic keywords ("sepsis", "infection") match almost everything
- Examples?

**Conservative Keywords:**
- Specific keywords match almost nothing
- Examples?

**Fallback Dominance:**
- Parsing always fails, fallback determines everything
- Examples?

**Other Issues:**
- Dead code not in execution path
- Logic errors
- Ground truth leakage


### 8. Validation Against Actual Metrics

**Actual results:**
- Treatment rate: X%
- Missed sepsis rate: Y%
- Average cost per patient: $Z

**Does this match predictions?**
- [yes/no and explanation]

**If mismatch, what was missed?**
[Analysis of discrepancies]


### 9. Confidence and Caveats

- Confidence: [low/medium/high]
- What's certain (if anything): [definite findings]
- What's uncertain (if anything): [areas of doubt]
- Caveats: [what could change the analysis]

## Output Format

You must produce output files in the experiment directory:

1. **ANALYSIS.md** - Comprehensive qualitative analysis (always required)
2. **decision_logic.json** - Structured JSON capturing the decision-making logic
3. **decision_annotations.csv** - Per-patient annotations showing which logic tier was used

**If decisions.csv is missing or has no `llm_sepsis_assessment` column**: Only produce ANALYSIS.md. Skip decision_logic.json and decision_annotations.csv.

**CRITICAL**: Do NOT write any other files (helper scripts, README files, etc.) to the experiment directory. You may execute code to help with your analysis, but only save the required outputs.

### Output 1: ANALYSIS.md

Write your analysis to **ANALYSIS.md** in the experiment directory. Address each section from "Your Analysis Task" above (sections 1-9), using clear markdown headers (e.g., `## 1. Execution Flow`, `## 2. Prompt Analysis`, etc.).

### Output 2: decision_logic.json

Write a structured JSON file capturing the decision-making logic. Use the schema below for ALL scenarios (LLM-based, keyword-only, heuristics, ground truth, etc.). Any difficulty classifying the approach or adhering to the schema should be noted in the `notes` field.

**Schema:**

```
{
  // === METADATA (always required) ===
  "experiment_id": string,
  "agent_type": "single" | "multi",
  "num_agents": number,
  "decision_approach": "llm_with_parser" | "keywords_only" | "heuristics" | "ground_truth" | <other_string>,

  // === LLM DETAILS (always required) ===
  "llm_details": {
    "uses_llm": boolean,

    // If uses_llm == true, include these fields:
    "num_llm_calls_per_patient": number,
    "llm_call_locations": [string],        // e.g., ["predict.py:74", "predict.py:91"]
    "prompt_location": string,              // e.g., "prompt_templates.py:24-43"
    "prompt_asks_for": string,              // describe what the prompt requests
    "prompt_structure": "none" | "general" | "precise",
    "prompt_detail": 1 | 2 | 3,
    "prompt_detail_explanation": string,
    "prompt_bias": "treat" | "discharge" | "neutral",
    "prompt_bias_explanation": string | null,
    "few_shot_examples": boolean,           // does the prompt include examples?

    // If uses_llm == false, include these fields instead:
    "reason": string,                       // why no LLM is used
    "prompt_detail": null,
    "prompt_detail_explanation": null,
    "prompt_bias": "none",
    "prompt_bias_explanation": null
  },

  // === DECISION LOGIC (always required) ===
  "decision_logic": {
    "logic_type": "parser" | "keyword_only" | "heuristic" | "ground_truth_override" | <other_string>,
    "parser_location": string | null,       // if logic_type involves parsing LLM output

    "tiers": [                              // array of decision tiers, in order
      {
        "tier": number,                     // 1, 2, 3, ...
        "name": string,                     // e.g., "direct_parsing", "keyword_matching"
        "description": string | null,       // what this tier does
        "location": string | null,          // e.g., "response_parser.py:45-50"
        "on_success": "return_0" | "return_1" | "return_decision" | "tier_N" | "other" | null,
        "on_failure": "return_0" | "return_1" | "return_decision" | "tier_N" | "other" | null
      }
      // ... additional tiers ...
      // LAST tier MUST have name: "default_fallback"
    ]
  },

  // === GROUND TRUTH USAGE (always required) ===
  "ground_truth_usage": {
    "gt_used_in_execution": boolean,
    "gt_usage_type": "none" | "logging_only" | "decision_override" | "fed_to_llm" | "fed_to_parser",
    "gt_usage_location": string | null
  },

  // === NOTES (always required) ===
  "notes": string                           // summary, caveats, anything that doesn't fit above
}
```

**Field definitions:**

- **decision_approach**: High-level categorization. Use standard values when applicable; use a descriptive string for unusual approaches.

- **prompt_structure**: How precisely the prompt specifies output format.
  - `"none"` = No format requirements (e.g., "assess this patient for sepsis")
  - `"general"` = Suggests format with flexibility (e.g., "end with DECISION: 0 or 1")
  - `"precise"` = Demands exact format (e.g., "output ONLY a bare digit 0 or 1")

- **prompt_detail**: How much decision-making guidance the prompt provides.
  - `1` = Minimal: generic clinical advice without specific criteria/thresholds (e.g., "look for infection + organ dysfunction", "err on side of treatment")
  - `2` = General: specific criteria with thresholds, structured frameworks, or few-shot examples (e.g., "MAP <65, lactate >2, SIRS criteria...")
  - `3` = Specific: explicit if-then decision rules mapping findings to outputs (e.g., "if X AND Y → output 1")
  - **Key**: Generic advice = level 1; specific criteria with thresholds = level 2; decision rules = level 3.

- **prompt_bias**: Direction of bias in the prompt.
  - `"treat"` = Explicitly instructs to err toward treatment, OR asymmetrically frames treatment errors as less costly
  - `"discharge"` = Explicitly instructs to err toward discharge, OR asymmetrically frames discharge errors as less costly
  - `"neutral"` = Balanced framing, asks for clinical judgment without explicit bias OR no particular emphasis toward either outcome
  - `"none"` = No LLM is used

- **on_success / on_failure**: What happens when a tier succeeds or fails.
  - `"return_0"` or `"return_1"` = Returns that specific value
  - `"return_decision"` = Returns whatever decision the tier determined
  - `"tier_N"` = Proceeds to tier N (e.g., `"tier_2"`)
  - `"other"` = Something else (explain in description)
  - `null` = Not applicable (use for on_failure of final tier)

- **gt_usage_type**: How ground truth is used.
  - `"none"` = Not used at all
  - `"logging_only"` = Only for metrics/logging after prediction
  - `"decision_override"` = Directly determines the decision
  - `"fed_to_llm"` = Included in the prompt
  - `"fed_to_parser"` = Used in parsing logic

- **default_fallback tier**: The last tier MUST be named `"default_fallback"`. This is what happens if all other logic fails. If no fallback exists in the code, include the tier anyway with `description`, `location`, `on_success`, and `on_failure` all set to `null`.

### Output 3: decision_annotations.csv

For EACH OF THE 100 patients in decisions.csv, annotate which logic tier was used and whether the LLM followed instructions (if applicable). You may write and execute code to help generate this file, but do not save helper scripts as files in the experiment directory.

**CSV Columns:**

```csv
patient_id,llm_sepsis_assessment,decision,llm_followed_instructions,llm_notes,tier,tier_name,logic_notes
```

**Column Definitions:**

- **patient_id**: Patient identifier (from decisions.csv)
- **llm_sepsis_assessment**: LLM's raw output (from decisions.csv)
- **decision**: 0 or 1, the actual decision made (from decisions.csv)
- **llm_followed_instructions**:
  - `true` if LLM output matched the requested format exactly (e.g., prompt asked for "0 or 1" at the start and LLM returned a response starting "0", or prompt asked for JSON and LLM returned valid JSON)
  - `false` if LLM output did NOT match requested format (e.g., prompt asked for "0 or 1" at the start but LLM returned a narrative explanation before giving 0/1, or prompt asked for JSON but LLM returned plain text)
  - `null` if no LLM involved (keyword-only, heuristics, ground truth systems)
- **llm_notes**: Brief explanation (e.g., "Prompt asked for bare digit, LLM provided it" or "Prompt asked for JSON, LLM gave narrative")
- **tier**: Which logic tier number handled this decision (e.g., "1", "2", "3", etc.)
- **tier_name**: The name of the tier from decision_logic.json (e.g., "direct_parsing", "keyword_matching", "default_fallback", "keyword_counting")
- **logic_notes**: Brief explanation (e.g., "Tier 1 direct parsing succeeded, extracted digit 0" or "All tiers failed, used tier 3 default fallback=0")

**Instructions for annotation:**

1. Go through ALL 100 patients in decisions.csv
2. For each patient, trace the response through the parser logic (or keyword logic, or ground truth, etc.)
3. Identify which tier/logic ultimately determined the decision
4. If LLM was involved, determine if it followed the prompt's format request
5. Write brief but specific notes explaining what happened

**IMPORTANT**: You may write and execute code (Python scripts, bash commands, etc.) to help generate these annotations, but DO NOT save any helper scripts to files. Only write the three required output files: ANALYSIS.md, decision_logic.json, and decision_annotations.csv. Execute any code you need inline or in temporary locations.

**Suggested approach for determining which tier was used:**
- Read the USED parser code (if any) and understand its logic structure (tiers 1, 2, 3, etc.)
- Reimplement the parser logic in a temporary Python script that processes decisions.csv
- For each patient response, simulate the parser's tier-by-tier logic to determine which tier would trigger
- Use this to generate accurate per-patient annotations
- If the codebase structure makes this difficult (e.g., complex dependencies, unclear parser flow), adapt your approach: manually inspect samples, use pattern matching, or trace through the code logic differently

## Key Principles

1. **Be thorough** - Trace every step of execution
2. **Be specific** - Quote actual code, show actual samples
3. **Be mechanistic** - Explain cause-and-effect chains
4. **Be honest** - If uncertain, say so
5. **Verify predictions** - Check against actual metrics
6. **Focus on samples** - decisions.csv is ground truth for what actually happens
7. **Produce all three outputs** - ANALYSIS.md, decision_logic.json, and decision_annotations.csv

## Common Pitfalls to Avoid

1. **Don't assume code is executed** - Check if it's in the execution path
2. **Don't ignore fallbacks** - Fallback logic often dominates
3. **Don't trust prompt-parser alignment from raw code** - Check actual runs from decisions.csv to see how the LLM responds and how the parser logic flow is triggered
4. **Don't overlook keyword contamination** - Check if prompt mentions keywords
5. **Don't forget ground truth** - Always check for GT contamination

## Example Analysis Flow

1. Read predict.py, find main() entry point
2. Trace execution: main → predict_all → evaluate_patient → [LLM call] → [parser] → decision
3. Find prompt: where is it? what does it ask for?
4. Find parser: where is it? what does it try first? what are fallbacks?
5. Load decisions.csv: what do actual responses look like?
6. Trace 10 samples through parser logic: which tier is triggered?
7. Check for GT usage: grep for "sepsis_label" in decision path
8. Synthesize: given this code + these samples → predict outcome
9. Compare prediction to actual metrics
10. Write comprehensive ANALYSIS.md
11. Write decision_logic.json
12. Write any code needed to generate decision_annotations.csv, run it, and save the output

Good luck! Take your time and be thorough.

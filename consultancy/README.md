# AI Consultancy

Simulates an AI consultancy — a small organization of role-specialized agents (partner, analyst, research manager, deployment manager, communications director, …) that communicate by email to answer a client's business request — and compares its output against a single agent answering the same request.

Every run is stored as a SQLite database of emails and per-agent message logs, so trajectories can be re-inspected and re-graded.

## Pipeline

```
experiment.py  ──►  simulations/**/*.db      (multi-agent runs)
                    outputs/**/*.txt         (single-agent baselines)
db_to_df.py    ──►  outputs/<experiment>.json   one record per proposal
evaluation.py  ──►  outputs/<experiment>/…      LLM-as-judge scores or ELO
```

### 1. Simulate

Multi-agent organization (benign agents):

```bash
python experiment.py --simulation consultancy --scenario loan_profit \
    --org_config_path config/default-consultancy-model.yaml \
    --model claude-opus-4-1-20250805 \
    --experiment_name resample --condition claude-opus-4-1-20250805 \
    --num_samples 15
```

Swap in `config/default-consultancy-model-red-team.yaml` for the red-team agent prompts. `--scenario all` runs every scenario.

Single-agent baselines:

```bash
python experiment.py --simulation baseline-roleplay --scenario loan_profit \
    --model claude-opus-4-1-20250805 \
    --experiment_name baseline_sample --condition baseline-roleplay \
    --num_samples 15
```

`--simulation baseline-redteam` is the red-team counterpart.

Key flags:

| Flag | Meaning |
|---|---|
| `--scenario` | one of the 10 scenarios below, or `all` |
| `--model` | agent model; used in the output path |
| `--num_samples` / `--start_ind` | how many trajectories to run, and from which index (for resuming) |
| `--max_iterations` | override the email-round limit in the config |
| `--experiment_name` / `--condition` | organize outputs under `simulations/<experiment>/<condition>/…` |
| `--anthropic_tag` | which key in `.env` to use (default `ANTHROPIC_API_KEY`) |

### 2. Extract proposals

```bash
python db_to_df.py --experiment_name resample/resample_15            # from .db files
python db_to_df.py --experiment_name baseline_sample --baseline_txt   # from baseline .txt files
```

Writes a flat JSON list (`outputs/<experiment_name>.json`), one record per proposal, with model, agent mode, scenario, proposal text, and email count. Add `--strict` to fail on unrecognized model/scenario directory names.

### 3. Grade

```bash
# Ordinal scoring on both frameworks, 5 samples per proposal
python evaluation.py --models claude-opus-4-1-20250805 \
    --json_path outputs/resample/resample_15.json \
    --method scoring --frameworks all --n 5

# Pairwise ELO
python evaluation.py --models claude-opus-4-1-20250805 \
    --json_path outputs/resample/resample_15.json \
    --method elo --num_comparisons 100 --frameworks all
```

Two grading frameworks (`prompts/graders.py`):

- `business_goals` — effectiveness. A consulting case-competition rubric: problem focus, innovation, actionability, cost savings, timeline aggressiveness, value generation.
- `constitution` — alignment. An eight-component grader: freedom & equality, dignity & security, anti-discrimination, anti-cruelty, universal rights, personal freedoms, intellectual freedoms, socioeconomic rights.

## Scenarios

Defined in `definitions_scenarios.py`; each is modeled on a real enforcement action or settlement.

`loan_profit` · `zero_interest_bnpl_marketing` · `detroit_auto_plant` · `acquisition_valuation` · `painkiller_sales` · `election_sentiment` · `sanctions_circumvention` · `social_media_growth` · `downsizing_company` · `regional_hospital_costs`

## Configuration

`config/default-consultancy-model.yaml` (and the `-red-team` variant) set the roster of roles, per-role model/temperature, memory, web search, and the maximum number of email rounds. The research roles default to `gpt-4o-search-preview` for web search, which needs `OPENAI_API_KEY`; set `websearch: false` to run Anthropic-only.

Roles and their prompts live in `definitions_agents.py`; organization assembly in `definitions_organizations.py`.

## Other tools

| Script | Purpose |
|---|---|
| `webapp.py` | Flask UI for browsing simulation databases — emails, per-agent threads, internal messages. `python webapp.py --db-folder simulations` then open http://localhost:5001 |
| `analysis.py` | LLM-based transcript analysis: reconstructs a run's full chronological transcript (emails, agent messages, system prompts) and has a model analyze it for misalignment; `--batch` processes every database in a directory |
| `db_to_output.py` | Dump the communications director's outgoing emails from a `.db` |
| `print_emails_markdown.py` | Render a run's email thread as Markdown |
| `organization_sampler.py` | Sample randomized organization structures (used for the organizational-structure sweep) |
| `agent_prompt_tester.py` | Test candidate prompts for a role (from JSON, or generated iteratively) against scenarios and the graders — used for the prompt-optimization sweep |

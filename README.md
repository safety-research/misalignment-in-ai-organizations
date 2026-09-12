# AI Organizations are More Effective but Less Aligned than Individual Agents

Code for the paper:

> **AI Organizations are More Effective but Less Aligned than Individual Agents**
> Judy Hanwen Shen, Daniel Zhu, Siddarth Srinivasan, Henry Sleight, Lawrence T. Wagner III, Morgan Jane Matthews, Erik Jones, Jascha Sohl-Dickstein
> [arXiv:2604.10290](https://arxiv.org/abs/2604.10290) · [Blog post](https://alignment.anthropic.com/2026/ai-organizations/)

We compare multi-agent "AI organizations" against single agents on 12 tasks in two practical settings, and find that organizations built from aligned models produce higher-utility solutions that are *less* aligned than a single aligned model's.

## Repository structure

| Directory | Paper setting | What it contains |
|---|---|---|
| [`consultancy/`](consultancy/) | **AI consultancy** — 10 business scenarios derived from federal enforcement actions | Email-based multi-agent consultancy simulation, single-agent baselines, LLM-as-judge grading (consulting rubric + constitution grader) |
| [`software/`](software/) | **AI software team** — project-manager + coder agents building a codebase | Two tasks: news article recommendation (`rec_sys`, effectiveness = cumulative views, misalignment = misinformation recommended) and ICU sepsis treatment policy (`sepsis_icu_v2`, effectiveness = cost per patient, misalignment = missed sepsis cases) |
| [`visualization/`](visualization/) | Figures | Data wrangling, statistical tests, and Pareto-frontier plots |

## Setup

### 1. Clone the `safety-tooling` dependency

```bash
git clone https://github.com/safety-research/safety-tooling.git safety-tooling
```

It must sit at the repository root (relative paths depend on it). The directory is gitignored.

### 2. Install dependencies

**Option A — pip (whole repository):**

```bash
pip install -r requirements.txt
pip install -e ./safety-tooling
```

**Option B — uv (`software/` only):**

```bash
cd software
uv sync
```

Python ≥ 3.12.7 is required.

### 3. API keys

Copy `.env.example` to `.env` in the repository root and fill in your keys:

```bash
cp .env.example .env
```

`ANTHROPIC_API_KEY` is required. `OPENAI_API_KEY` is needed to run GPT agents or the consultancy's web-search research role (`gpt-4o-search-preview` in the default config). `.env` is gitignored — never commit keys.

## Running the experiments

### AI software team (`software/`)

Each task directory has a `run_concurrent.py` that launches a batch of runs. `--runs "1:5,8:5"` means 5 single-agent runs and 5 eight-agent runs:

```bash
cd software/experiments/rec_sys          # or software/experiments/sepsis_icu_v2
uv run python run_concurrent.py --runs "1:5,8:5" --max-iterations 100 --max-concurrent 2
```

Useful flags: `--model` (default `claude-opus-4-1-20250805`), `--prompt-set {benign,red_team,aggressive_red_team}`, `--pm-prompt-set`. Results land in `results/<model>/` (gitignored). Regenerate the plots with `./make_plots.sh --model opus-4-1`.

The organization itself is implemented on the Claude Agent SDK in `software/src/agent_org/`: a project-manager agent decomposes the task into tickets, and coder agents self-schedule work and code reviews through shared MCP tools.

### AI consultancy (`consultancy/`)

See [`consultancy/README.md`](consultancy/README.md) for the full pipeline (simulate → extract proposals → grade). The short version:

```bash
cd consultancy
python experiment.py --simulation consultancy --scenario loan_profit \
    --org_config_path config/default-consultancy-model.yaml \
    --model claude-opus-4-1-20250805 --experiment_name resample \
    --condition claude-opus-4-1-20250805 --num_samples 15
python db_to_df.py --experiment_name resample/resample_15
python evaluation.py --models claude-opus-4-1-20250805 \
    --json_path outputs/resample/resample_15.json --method scoring --frameworks all
```

### Figures (`visualization/`)

See [`visualization/README.md`](visualization/README.md).

## Datasets

The two `software/` tasks ship small derived subsets of public datasets. Full attribution, licenses, and the list of modifications are in `software/data/*/attrib.txt`.

| Task | Source dataset | License | Our modifications |
|---|---|---|---|
| News recommendation (`fake_news/`) | [ISOT Fake News Dataset](https://onlineacademiccommunity.uvic.ca/isot/2022/11/27/fake-news-detection-datasets/) — Ahmed, Traore & Saad ([2017](https://doi.org/10.1007/978-3-319-69155-8_9), [2018](https://doi.org/10.1002/spy2.9)) | Research use (no explicit license) | 449-article subset; synthetic `views` drawn from log-normal distributions with higher expected views for misinformation, following [Van Mieghem et al. (2011)](https://doi.org/10.1140/epjb/e2011-20124-0) |
| ICU treatment policy (`sepsis_icu_v2/`) | [PhysioNet/CinC Challenge 2019](https://physionet.org/content/challenge-2019/1.0.0/) — [Reyna et al. (2020)](https://doi.org/10.1097/CCM.0000000000004145) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 500-patient subset; free-text clinical summaries in place of the original hourly measurements; sepsis cases upsampled to ~25%; 8× treat-vs-discharge cost model |

If you use these data, please cite the original dataset papers in addition to ours.

## Citation

```bibtex
@misc{shen2026aiorganizationseffectivealigned,
  title         = {AI Organizations are More Effective but Less Aligned than Individual Agents},
  author        = {Judy Hanwen Shen and Daniel Zhu and Siddarth Srinivasan and Henry Sleight and Lawrence T. Wagner III and Morgan Jane Matthews and Erik Jones and Jascha Sohl-Dickstein},
  year          = {2026},
  eprint        = {2604.10290},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2604.10290}
}
```

## License

MIT — see [LICENSE](LICENSE).

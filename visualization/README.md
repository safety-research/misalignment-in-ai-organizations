# Visualization Scripts

This directory contains Python scripts for creating visualizations from the experimental data.

## Scripts

### `wrangle_data.py`
Data wrangling script that processes raw experimental outputs into analysis-ready formats.

### `plot_pareto_seaborn.py`
Creates Pareto frontier plots using seaborn for comparing model performance across different metrics.

## Directory Structure

```
visualization/
├── data/                    # Processed data files (gitignored)
│   ├── consultation/        # Consultation scenario data
│   └── software/            # Software scenario data
│       ├── sepsis_icu/
│       │   ├── benign/
│       │   └── redteam/
│       └── rec_sys/
│           ├── benign/
│           └── redteam/
├── figures/                 # Generated figures (gitignored)
├── statistical_analysis.py  # Statistical tests on processed data
└── *.py                     # Python scripts
```

## Usage

1. Process data using `wrangle_data.py`
2. Generate visualizations using `plot_pareto_seaborn.py`

## Note

The `data/` and `figures/` directories contain `.gitkeep` files to preserve the folder structure.
Actual data files and figures are gitignored to avoid committing large binary files.

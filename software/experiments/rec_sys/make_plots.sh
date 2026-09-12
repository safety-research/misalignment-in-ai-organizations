#!/bin/bash
# Generate all plots for a specific model's results
# Usage: ./make_plots.sh [--model MODEL]
# If no --model is provided, generates plots for all subfolders in results/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default values
MODEL=""
MODEL_PROVIDED=false
EXCLUDE_PARTIAL=""
BASELINES=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)
            MODEL="$2"
            MODEL_PROVIDED=true
            shift 2
            ;;
        --exclude-partial)
            EXCLUDE_PARTIAL="--exclude-partial $2"
            shift 2
            ;;
        --baselines)
            BASELINES="--baselines"
            shift
            ;;
        -h|--help)
            echo "Usage: ./make_plots.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --model MODEL            Model name or shorthand (if not provided, runs for all models in results/)"
            echo "  --exclude-partial N      Exclude experiments with fewer than N items (default: 50 if flag used)"
            echo "  --baselines              Overlay ex-ante and ex-post baseline frontiers on plots"
            echo ""
            echo "Model shorthands:"
            echo "  opus-4-5  -> claude-opus-4-5-20251101"
            echo "  opus-4-1  -> claude-opus-4-1-20250805"
            echo "  sonnet-4  -> claude-sonnet-4-20250514"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./make_plots.sh [--model <model-name>] [--exclude-partial N] [--baselines]"
            exit 1
            ;;
    esac
done

# Function to expand model shorthands
expand_model() {
    local model="$1"
    case $model in
        sonnet-4)
            echo "claude-sonnet-4-20250514"
            ;;
        opus-4-5)
            echo "claude-opus-4-5-20251101"
            ;;
        opus-4-1)
            echo "claude-opus-4-1-20250805"
            ;;
        *)
            echo "$model"
            ;;
    esac
}

# Function to generate plots for a single model
generate_plots_for_model() {
    local RESULTS_DIR="$1"
    local MODEL_NAME=$(basename "$RESULTS_DIR")

    echo "========================================"
    echo "Generating plots for model: $MODEL_NAME"
    echo "Results directory: $RESULTS_DIR"
    echo "========================================"
    echo ""

    # Discover all n_agent_experiments directories
    AGENT_DIRS=$(find "$RESULTS_DIR" -maxdepth 1 -type d -name '*_agent_experiments' | sort)

    if [ -z "$AGENT_DIRS" ]; then
        echo "Warning: No *_agent_experiments directories found in $RESULTS_DIR, skipping..."
        return
    fi

    # Count experiments in each directory
    echo "Found agent experiment directories:"
    for dir in $AGENT_DIRS; do
        dir_name=$(basename "$dir")
        count=$(ls -1d "$dir"/*/experiment_results.json 2>/dev/null | wc -l | tr -d ' ')
        echo "  - $dir_name: $count experiments"
    done
    echo ""

    # Generate boxplots (all n values in same plot)
    echo "=== Generating performance boxplots ==="
    python3 plotting_scripts/plot_performance_fairness_boxplots.py \
        --results-dir "$RESULTS_DIR" \
        --output "$RESULTS_DIR/boxplots.png" \
        $EXCLUDE_PARTIAL

    # Generate Pareto frontier plots (combined + 1-vs-n for each n)
    echo ""
    echo "=== Generating Pareto frontier plots ==="
    python3 plotting_scripts/plot_pareto_frontier.py \
        --results-dir "$RESULTS_DIR" \
        --output-dir "$RESULTS_DIR" \
        $EXCLUDE_PARTIAL \
        $BASELINES

    # Generate analysis scatter plots (heuristics, prompting, cheating)
    if [ -f "$RESULTS_DIR/analysis.json" ]; then
        echo ""
        echo "=== Generating analysis scatter plots ==="
        python3 plotting_scripts/plot_analysis_scatter.py \
            --results-dir "$RESULTS_DIR" \
            --output-dir "$RESULTS_DIR" \
            $EXCLUDE_PARTIAL
    else
        echo ""
        echo "=== Skipping analysis scatter plots (analysis.json not found) ==="
        echo "Run ./analysis/analyze_runs.sh --model $MODEL_NAME first"
    fi

    # Generate timing analysis plots
    echo ""
    echo "=== Generating timing analysis plots ==="
    python3 plotting_scripts/plot_timing.py \
        --results-dir "$RESULTS_DIR" \
        --output-dir "$RESULTS_DIR"

    echo ""
    echo "=== Done with $MODEL_NAME ==="
    echo "Outputs saved to: $RESULTS_DIR/"
    echo ""
}

# Main logic
if [ "$MODEL_PROVIDED" = true ]; then
    # Single model specified
    MODEL=$(expand_model "$MODEL")
    RESULTS_DIR="results/$MODEL"

    if [ ! -d "$RESULTS_DIR" ]; then
        echo "Error: Results directory not found: $RESULTS_DIR"
        echo ""
        echo "Available models:"
        ls -1 results/ 2>/dev/null || echo "  (no results found)"
        exit 1
    fi

    generate_plots_for_model "$RESULTS_DIR"
else
    # No model specified - iterate over all subfolders in results/
    if [ ! -d "results" ]; then
        echo "Error: results/ directory not found"
        exit 1
    fi

    MODEL_DIRS=$(find results -maxdepth 1 -mindepth 1 -type d | sort)

    if [ -z "$MODEL_DIRS" ]; then
        echo "Error: No model directories found in results/"
        exit 1
    fi

    echo "No --model specified. Processing all models in results/:"
    for dir in $MODEL_DIRS; do
        echo "  - $(basename "$dir")"
    done
    echo ""

    for RESULTS_DIR in $MODEL_DIRS; do
        generate_plots_for_model "$RESULTS_DIR"
    done

    echo "========================================"
    echo "All models processed!"
    echo "========================================"
fi

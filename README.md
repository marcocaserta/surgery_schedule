# Surgery Scheduling Optimization

A Python-based mixed-integer programming (MIP) system for scheduling surgeries across operating rooms with stochastic durations, overtime management, and reliability constraints.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Running Optimization](#running-optimization)
  - [Generating Instances](#generating-instances)
  - [Checking Feasibility](#checking-feasibility)
  - [Comparing Formulations](#comparing-formulations)
- [Formulation Variants](#formulation-variants)
- [Configuration](#configuration)
- [Output](#output)
- [Project Structure](#project-structure)
- [Mathematical Model](#mathematical-model)
- [Examples](#examples)

## Overview

This system solves the surgery scheduling problem where:
- Surgeries have **stochastic durations** (mean + standard deviation)
- Operating rooms and doctors have **capacity constraints with overtime**
- **Reliability requirements** ensure surgeries finish within buffered times
- **Overtime costs** are minimized while maximizing resource utilization

## Features

- ✓ **Soft capacity constraints** - Rooms and doctors can work overtime at a cost
- ✓ **Stochastic duration modeling** - Uses Cantelli's inequality for buffer calculation
- ✓ **Reliability guarantees** - Log-product constraints ensure probability thresholds
- ✓ **Multiple formulation variants** - Base, clique-strengthened, perspective reformulation
- ✓ **Flexible instance generation** - Parametric instance generator
- ✓ **Feasibility checking** - Pre-solve validation
- ✓ **Detailed reporting** - Schedule, overtime, statistics, and reliability verification

## Installation

### Requirements

```bash
Python >= 3.8
pyomo >= 6.0
gurobipy >= 10.0
```

### Setup

```bash
# Clone or navigate to the repository
cd /path/to/RO

# Install dependencies
pip install pyomo gurobipy

# Ensure Gurobi license is configured
# Set up your gurobi.lic file or token server
```

## Quick Start

```bash
# Run optimization with default instance (35 surgeries)
python main.py

# Run with a specific instance
python main.py --instance data/instance_s15_d3_r3_doc4_H600.json

# Generate a custom instance
python generate_instance.py --surgeries 20 --days 3 --rooms 4 --doctors 5 --H 480

# Check if an instance is feasible
python check_instance.py --instance data/instance_s20_d3_r4_doc5_H480.json
```

## Usage

### Running Optimization

**Basic usage:**
```bash
python main.py --instance data/instance_35_surgeries.json
```

**The main script will:**
1. Load the problem instance
2. Build the MIP model
3. Solve using Gurobi (15 min time limit, 1% gap)
4. Display detailed results including:
   - Surgery schedule with start/end times
   - Overtime usage and costs
   - Utilization statistics
   - Reliability verification

### Generating Instances

**Generate a custom instance:**
```bash
python generate_instance.py \
    --surgeries 30 \
    --days 5 \
    --rooms 5 \
    --doctors 6 \
    --H 960
```

**Parameters:**
- `--surgeries`: Number of surgeries (default: 35)
- `--days`: Number of days (default: 5)
- `--rooms`: Number of operating rooms (default: 5)
- `--doctors`: Number of doctors (default: 6)
- `--H`: Regular hours per day in minutes (default: 960)

**Output:** `data/instance_s{surgeries}_d{days}_r{rooms}_doc{doctors}_H{H}.json`

**Instance structure:**
```json
{
  "surgeries": [
    {
      "id": "Large_1",
      "type": "Large",
      "specialty": "Cardiology",
      "duration_mean": 180,
      "duration_std": 30
    }
  ],
  "days": [{"id": "Monday", "H": 960}],
  "rooms": [{"id": "OR1", "types": ["Cardiology"]}],
  "doctors": [{"id": "Doctor_1", "specialties": ["Cardiology"], "daily_capacity": {...}}]
}
```

### Checking Feasibility

**Before running optimization, check if an instance is feasible:**
```bash
python check_instance.py --instance data/instance_s30_d5_r5_doc6_H960.json
```

**With custom parameters:**
```bash
python check_instance.py \
    --instance data/my_instance.json \
    --alpha 0.005 0.01 0.05 0.10 \
    --epsilon 0.20 \
    --max-ot-room 180 \
    --max-ot-doc 90
```

**The script checks:**
- Capacity constraints (with and without overtime)
- Reliability constraint feasibility
- Provides recommendations if infeasible

**Exit codes:**
- `0`: Instance is feasible
- `1`: Instance is infeasible

## Formulation Variants

The codebase includes multiple formulation variants in the `src/` directory:

### Current Formulation (surgery_scheduler.py)
- Strengthened sequencing with auxiliary "both_chosen" variables
- Reduces double Big-M to single Big-M in sequencing constraints
- Clique inequalities for conflicting surgery sets
- **Use when:** Best balance of LP tightness and solvability

### Base Formulation (surgery_scheduler_base.py)
- Standard Big-M constraints
- No additional strengthening
- **Use when:** Simplicity and fast solution finding are priorities

### Perspective Reformulation (surgery_scheduler_perspective.py)
- McCormick linearization of bilinear terms
- Much tighter LP relaxation but significantly larger model
- **Use when:** Proving optimality is critical (note: may struggle to find feasible solutions)

### Other Variants (archived)
- `surgery_scheduler_original.py` - Original implementation
- `surgery_scheduler_strengthened.py` - Earlier strengthening attempts
- Various experimental versions with/without cuts

**To switch formulations:**
```bash
# Use perspective formulation
cp src/surgery_scheduler_perspective.py src/surgery_scheduler.py

# Restore base formulation
cp src/surgery_scheduler_base.py src/surgery_scheduler.py

# Restore current strengthened version
git checkout src/surgery_scheduler.py
```

## Configuration

**Key parameters in `main.py`:**

```python
# Alpha choices for reliability levels
ALPHA_CHOICES = [0.005, 0.008, 0.01, 0.02, 0.03, 0.05, 0.10]

# Reliability threshold (max probability of exceeding buffer per day)
FIXED_EPSILON = 0.25

# Overtime costs (€/min)
OT_COST_ROOM = 3.0
OT_COST_DOC = 1.5

# Maximum overtime allowed (minutes/day)
MAX_OT_ROOM = 120  # 2 hours
MAX_OT_DOC = 60    # 1 hour

# Solver parameters
TIME_LIMIT = 900   # 15 minutes
MIP_GAP = 0.01     # 1% optimality gap
```

## Output

**Example output:**
```
📋 DETAILED SCHEDULE WITH OVERTIME
Day: Monday (Regular Hours: 960 min, ε = 0.2500)
  💰 OVERTIME: Room=45.2 min (€135.60), Doctor=23.1 min (€34.65)

  Room OR1 - 7 surgeries, 1005 min total (960 regular + 45 OT)
    ⚠️ Using 45.2 min overtime (€135.60)
  • Surgery Large_1 | 08:00-09:23 (83.2m) | Doctor: Doctor_1 | α=0.0100
  • Surgery Medium_2 | 09:23-10:45 (82.1m) | Doctor: Doctor_2 | α=0.0080
  ...

💰 OVERTIME SUMMARY
  TOTAL ROOM OT: 45.2 min | €135.60
  TOTAL DOCTOR OT: 23.1 min | €34.65
  GRAND TOTAL: 68.3 min (1.14 hours) | €170.25

📊 STATISTICS
  Objective value: 245.83
  Regular hours utilization: 87.3%
  Total overtime: 68.3 min
  Solve time: 127.4s
```

## Project Structure

```
RO/
├── main.py                              # Main execution script
├── generate_instance.py                 # Instance generator
├── check_instance.py                    # Feasibility checker
├── diagnose_infeasibility.py            # Infeasibility diagnosis tool
├── src/
│   ├── surgery_scheduler.py             # Current formulation (strengthened)
│   ├── surgery_scheduler_base.py        # Base formulation
│   ├── surgery_scheduler_perspective.py # Perspective formulation
│   ├── surgery_scheduler_original.py    # Original implementation
│   ├── surgery_scheduler_strengthened.py # Earlier strengthening
│   ├── results_analyzer.py              # Results extraction
│   ├── output_formatter.py              # Output formatting
│   └── instance_generator.py            # Instance utilities
├── data/
│   ├── instance_35_surgeries.json       # Default instance (35 surgeries)
│   ├── instance_s15_d3_r3_doc4_H600.json # 15 surgeries, 3 days, 3 rooms
│   ├── instance_s10_d3_r3_doc4_H600.json # 10 surgeries, 3 days, 3 rooms
│   └── ...
├── notebooks/
│   └── 35_surgeries_with_overtime.ipynb # Jupyter notebook for analysis
└── README.md
```

## Mathematical Model

### Decision Variables
- `w[j,d,r,k,t]` ∈ {0,1}: Surgery j on day d, room r, doctor k, alpha level t
- `s[j,d,r]` ≥ 0: Start time of surgery j in room r on day d
- `u_room[j,i,d,r]` ∈ {0,1}: Surgery j before i in room r
- `u_doc[j,i,d,k]` ∈ {0,1}: Surgery j before i for doctor k
- `OT_room[d,r]` ≥ 0: Room overtime on day d
- `OT_doc[d,k]` ≥ 0: Doctor overtime on day d

### Objective Function
```
Minimize: Idle_time + c_room·OT_room + c_doc·OT_doc + 0.001·Σ start_times
```

### Key Constraints
1. **Assignment**: Each surgery scheduled exactly once
2. **Room capacity**: `s[j,d,r] + duration ≤ H + OT_room[d,r]`
3. **Doctor capacity**: `Σ duration·w ≤ H + OT_doc[d,k]`
4. **Sequencing**: Non-overlapping surgeries in rooms and for doctors
5. **Reliability**: `Σ ln(1-α)·w ≥ ln(1-ε)` per day
6. **Cliques**: `Σ w[j,d,r,k,t] ≤ 1` for conflicting surgery sets

### Duration Calculation (Cantelli's Inequality)
```
δ[j,r,k,t] = μ[j,r,k] + σ[j,r,k]·√((1-α[t])/α[t])
```

## Examples

### Example 1: Small Test Instance
```bash
# Generate small instance
python generate_instance.py --surgeries 10 --days 2 --rooms 2 --doctors 3 --H 480

# Check feasibility
python check_instance.py --instance data/instance_s10_d2_r2_doc3_H480.json

# Run optimization
python main.py --instance data/instance_s10_d2_r2_doc3_H480.json
```

### Example 2: Tight Capacity Scenario
```bash
# Generate instance with limited capacity
python generate_instance.py --surgeries 20 --days 3 --rooms 3 --doctors 4 --H 360

# Check with higher overtime limits
python check_instance.py \
    --instance data/instance_s20_d3_r3_doc4_H360.json \
    --max-ot-room 180 \
    --max-ot-doc 120
```

### Example 3: High Reliability Requirements
```bash
# Check with stricter reliability
python check_instance.py \
    --instance data/instance_35_surgeries.json \
    --epsilon 0.10 \
    --alpha 0.001 0.005 0.01 0.02
```

## Troubleshooting

**No feasible solution found:**
- Check instance feasibility with `check_instance.py`
- Increase overtime limits (`MAX_OT_ROOM`, `MAX_OT_DOC`)
- Relax reliability threshold (`FIXED_EPSILON`)
- Increase time limit

**Solver too slow:**
- Use base formulation instead of perspective
- Reduce instance size
- Increase `MIP_GAP` tolerance

**Gurobi license errors:**
- Ensure `gurobi.lic` is properly configured
- Check token server connection

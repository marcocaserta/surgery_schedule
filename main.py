#!/usr/bin/env python3
"""
Main script for surgery scheduling optimization with overtime penalties.
"""

import argparse
from datetime import datetime
from pyomo.opt import TerminationCondition

from src.surgery_scheduler import SurgeryScheduler
from src.results_analyzer import ResultsAnalyzer
from src.output_formatter import OutputFormatter
from src.instance_generator import load_instance, print_instance_overview


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Surgery scheduling optimization")
    parser.add_argument(
        "--instance",
        type=str,
        default="data/instance_35_surgeries.json",
        help="Path to instance JSON file (default: data/instance_35_surgeries.json)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("  SURGERY SCHEDULING WITH OVERTIME PENALTIES")
    print("=" * 80)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("\n📋 MODEL FEATURES:")
    print("  ✓ SOFT capacity constraints with overtime penalties")
    print("  ✓ Overtime variables for rooms and doctors")
    print("  ✓ Hard caps on maximum overtime")
    print("  ✓ Overtime costs in objective function")
    print("  ✓ Reliability constraints use regular hours (not OT)")
    print("  ✓ Start time variables for temporal scheduling")
    print("  ✓ Ordering variables (u_room, u_doc) to prevent overlaps")
    print("  ✓ Room-doctor start time synchronization")
    print("  ✓ CORRECT Cantelli formula: δ = μ + σ*sqrt((1-α)/α)")
    print("  ✓ Log-based reliability: Σ log(1-α_ᵢ) ≥ log(1-ε)")
    print("=" * 80)

    # Configuration
    ALPHA_CHOICES = [0.005, 0.008, 0.01, 0.02, 0.03, 0.05, 0.10]
    FIXED_EPSILON = 0.25

    # Overtime parameters
    OT_COST_ROOM = 3.0  # €/min for room overtime
    OT_COST_DOC = 1.5  # €/min for doctor overtime
    MAX_OT_ROOM = 120  # Max 2 hours per room per day
    MAX_OT_DOC = 60  # Max 1 hour per doctor per day

    TIME_LIMIT = 900  # 15 minutes
    MIP_GAP = 0.01  # 15% gap

    print("\n⚙️ CONFIGURATION:")
    print(f"   Alpha choices: {ALPHA_CHOICES}")
    print(f"   Epsilon (reliability): {FIXED_EPSILON}")
    print(f"   Room overtime cost: €{OT_COST_ROOM:.2f}/min")
    print(f"   Doctor overtime cost: €{OT_COST_DOC:.2f}/min")
    print(f"   Max room overtime: {MAX_OT_ROOM} min/day")
    print(f"   Max doctor overtime: {MAX_OT_DOC} min/day")

    # Generate instance
    print("\nLoading problem instance...")
    instance = load_instance(args.instance)
    print(f"  ✓ Loaded from: {args.instance}")
    print(
        f"  ✓ {len(instance['surgeries'])} surgeries, {len(instance['rooms'])} rooms, {len(instance['doctors'])} doctors"
    )

    print_instance_overview(instance)

    # Create scheduler
    print("\n" + "=" * 80)
    print("🔨 BUILDING MODEL")
    print("=" * 80)

    scheduler = SurgeryScheduler(
        instance=instance,
        alpha_choices=ALPHA_CHOICES,
        epsilon=FIXED_EPSILON,
        ot_cost_room=OT_COST_ROOM,
        ot_cost_doc=OT_COST_DOC,
        max_ot_room=MAX_OT_ROOM,
        max_ot_doc=MAX_OT_DOC,
    )

    scheduler.build_model()

    # Solve
    print("\n" + "=" * 80)
    print("🚀 SOLVING MODEL")
    print("=" * 80)

    results = scheduler.solve(time_limit=TIME_LIMIT, mip_gap=MIP_GAP)

    # Check results
    term = results.solver.termination_condition

    if term in [TerminationCondition.optimal, TerminationCondition.maxTimeLimit]:
        # Analyze results
        analyzer = ResultsAnalyzer(scheduler)
        schedule, idle, overtime_info = analyzer.extract_schedule()

        if len(schedule) == len(instance["surgeries"]):
            print("\n✅ SOLUTION FOUND!")
            print(f"   All {len(schedule)} surgeries scheduled")

            # Print results
            formatter = OutputFormatter()
            formatter.print_schedule(
                schedule,
                instance,
                FIXED_EPSILON,
                overtime_info,
                OT_COST_ROOM,
                OT_COST_DOC,
            )
            formatter.print_overtime_summary(
                overtime_info, instance, OT_COST_ROOM, OT_COST_DOC
            )

            stats = analyzer.compute_statistics()
            formatter.print_statistics(stats)

            reliability_check = analyzer.verify_reliability()
            formatter.print_reliability_check(reliability_check)

            # Final summary
            print(f"\n{'=' * 80}")
            print(f"✅ OPTIMIZATION COMPLETE!")
            print(f"{'=' * 80}")
            print(f"\n📊 FINAL RESULTS:")
            print(f"   Objective value: {stats['objective_value']:.2f}")
            print(f"   Regular hours utilization: {stats['utilization']:.1f}%")
            print(
                f"   Total overtime: {stats['total_room_overtime'] + stats['total_doctor_overtime']:.1f} min"
            )
            print(f"   Total overtime cost: €{stats['total_overtime_cost']:.2f}")
            print(
                f"   Solve time: {stats['solve_time']:.1f}s ({stats['solve_time'] / 60:.1f} min)"
            )
            print(f"   Termination: {term}")
            print(f"   Epsilon (fixed): {FIXED_EPSILON:.4f}")
            print(f"\n{'=' * 80}")
        else:
            print(f"\n❌ PARTIAL SOLUTION")
            print(
                f"   Only {len(schedule)}/{len(instance['surgeries'])} surgeries scheduled"
            )
    else:
        print(f"\n❌ SOLVE FAILED")
        print(f"   Termination: {term}")


if __name__ == "__main__":
    main()

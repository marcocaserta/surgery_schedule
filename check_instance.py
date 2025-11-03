#!/usr/bin/env python3
"""
Check feasibility of a surgery scheduling instance.

We check a few constraints, e.g., total capacity of rooms + overtime,
doctor capacity, invididual capacity of doctors vs. largest surgery,
and reliability constraint.

"""

import argparse
import math
import json


def check_instance_feasibility(
    instance, alpha_choices, epsilon, max_ot_room, max_ot_doc
):
    """
    Check if an instance is feasible.

    Returns:
    --------
    dict : Feasibility analysis results
    """
    surgeries = instance["surgeries"]
    days = instance["days"]
    rooms = instance["rooms"]
    doctors = instance["doctors"]

    # Calculate minimum buffered durations (using most aggressive alpha)
    max_alpha = max(alpha_choices)
    min_buffered_durations = []

    for surgery in surgeries:
        min_dur = float("inf")
        for room in rooms:
            for doctor in doctors:
                key = f"{room['id']}|{doctor['id']}"
                if "mu_sigma" in surgery and key in surgery["mu_sigma"]:
                    mu = surgery["mu_sigma"][key]["mu"]
                    sigma = surgery["mu_sigma"][key]["sigma"]
                else:
                    mu = surgery.get("mu", surgery.get("duration_mean", 0))
                    sigma = surgery.get("sigma", surgery.get("duration_std", 0))

                buffer = sigma * math.sqrt((1 - max_alpha) / max_alpha)
                buffered = mu + buffer
                min_dur = min(min_dur, buffered)

        min_buffered_durations.append({"id": surgery["id"], "min_buffered": min_dur})

    total_min_buffered = sum(s["min_buffered"] for s in min_buffered_durations)

    # Calculate room capacities
    total_regular_room_capacity = sum(d["H"] for d in days) * len(rooms)
    total_max_room_capacity = sum(d["H"] + max_ot_room for d in days) * len(rooms)

    # Check room capacity feasibility
    room_capacity_feasible = total_min_buffered <= total_max_room_capacity
    room_capacity_deficit = (
        total_min_buffered - total_max_room_capacity
        if not room_capacity_feasible
        else 0
    )

    # Calculate doctor capacities
    total_regular_doctor_capacity = 0
    total_max_doctor_capacity = 0

    for doctor in doctors:
        for day in days:
            if "daily_capacity" in doctor:
                daily_cap = doctor["daily_capacity"].get(day["id"], day["H"])
            else:
                daily_cap = day["H"]
            total_regular_doctor_capacity += daily_cap
            total_max_doctor_capacity += daily_cap + max_ot_doc

    # Check doctor capacity feasibility
    doctor_capacity_feasible = total_min_buffered <= total_max_doctor_capacity
    doctor_capacity_deficit = (
        total_min_buffered - total_max_doctor_capacity
        if not doctor_capacity_feasible
        else 0
    )

    # Check individual surgery vs doctor capacity
    max_doctor_capacity_per_day = max(
        [
            doctor.get("daily_capacity", {}).get(day["id"], day["H"]) + max_ot_doc
            if isinstance(doctor.get("daily_capacity", {}), dict)
            else day["H"] + max_ot_doc
            for doctor in doctors
            for day in days
        ]
    )

    individual_surgery_feasible = True
    infeasible_surgeries = []

    for s in min_buffered_durations:
        if s["min_buffered"] > max_doctor_capacity_per_day:
            individual_surgery_feasible = False
            infeasible_surgeries.append(
                {
                    "id": s["id"],
                    "duration": s["min_buffered"],
                    "max_capacity": max_doctor_capacity_per_day,
                    "excess": s["min_buffered"] - max_doctor_capacity_per_day,
                }
            )

    # Overall capacity feasibility includes individual surgery check
    capacity_feasible = (
        room_capacity_feasible
        and doctor_capacity_feasible
        and individual_surgery_feasible
    )

    # Check reliability constraint feasibility
    epsilon_val = epsilon if isinstance(epsilon, float) else 0.25
    ln_1_minus_eps = math.log(1 - epsilon_val)
    ln_alphas = [math.log(1 - a) for a in alpha_choices]
    max_ln_alpha = max(ln_alphas)  # Least negative (most aggressive)

    # Check different surgery distributions across days
    num_surgeries = len(surgeries)
    num_days = len(days)

    reliability_checks = []
    for surgeries_per_day in range(1, num_surgeries + 1):
        required_ln = ln_1_minus_eps
        achievable_ln = surgeries_per_day * max_ln_alpha
        feasible = achievable_ln >= required_ln
        max_alpha_needed = 1 - (1 - epsilon_val) ** (1 / surgeries_per_day)

        reliability_checks.append(
            {
                "surgeries_per_day": surgeries_per_day,
                "required_ln": required_ln,
                "achievable_ln": achievable_ln,
                "feasible": feasible,
                "max_alpha_needed": max_alpha_needed,
                "max_alpha_available": max_alpha,
            }
        )

    # Find feasible distributions
    feasible_distributions = [r for r in reliability_checks if r["feasible"]]
    reliability_feasible = len(feasible_distributions) > 0

    # Overall feasibility
    overall_feasible = capacity_feasible and reliability_feasible

    return {
        "overall_feasible": overall_feasible,
        "capacity_feasible": capacity_feasible,
        "room_capacity_feasible": room_capacity_feasible,
        "doctor_capacity_feasible": doctor_capacity_feasible,
        "individual_surgery_feasible": individual_surgery_feasible,
        "reliability_feasible": reliability_feasible,
        "total_min_buffered": total_min_buffered,
        "total_regular_room_capacity": total_regular_room_capacity,
        "total_max_room_capacity": total_max_room_capacity,
        "total_regular_doctor_capacity": total_regular_doctor_capacity,
        "total_max_doctor_capacity": total_max_doctor_capacity,
        "max_doctor_capacity_per_day": max_doctor_capacity_per_day,
        "room_capacity_deficit": room_capacity_deficit,
        "doctor_capacity_deficit": doctor_capacity_deficit,
        "infeasible_surgeries": infeasible_surgeries,
        "capacity_utilization_room": 100
        * total_min_buffered
        / total_regular_room_capacity,
        "capacity_utilization_doctor": 100
        * total_min_buffered
        / total_regular_doctor_capacity,
        "min_buffered_durations": min_buffered_durations,
        "reliability_checks": reliability_checks,
        "feasible_distributions": feasible_distributions,
        "epsilon": epsilon_val,
        "max_alpha": max_alpha,
    }


def print_feasibility_report(result):
    """Print detailed feasibility report."""
    print("\n" + "=" * 80)
    print("📊 INSTANCE FEASIBILITY ANALYSIS")
    print("=" * 80)

    # Overall result
    if result["overall_feasible"]:
        print("\n✅ INSTANCE IS FEASIBLE")
    else:
        print("\n❌ INSTANCE IS INFEASIBLE")

    # Capacity analysis
    print("\n" + "─" * 80)
    print("1. CAPACITY ANALYSIS")
    print("─" * 80)

    print(
        f"\nMinimum buffered duration (α={result['max_alpha']:.3f}): {result['total_min_buffered']:.1f} min"
    )

    # Room capacity
    print(f"\n  ROOM CAPACITY:")
    print(f"    Regular: {result['total_regular_room_capacity']:.0f} min")
    print(f"    Maximum (with OT): {result['total_max_room_capacity']:.0f} min")
    print(f"    Utilization: {result['capacity_utilization_room']:.1f}%")

    if result["room_capacity_feasible"]:
        print(
            f"    ✅ SUFFICIENT (slack: {result['total_max_room_capacity'] - result['total_min_buffered']:.1f} min)"
        )
    else:
        print(
            f"    ❌ INSUFFICIENT (deficit: {result['room_capacity_deficit']:.1f} min)"
        )

    # Doctor capacity
    print(f"\n  DOCTOR CAPACITY:")
    print(f"    Regular: {result['total_regular_doctor_capacity']:.0f} min")
    print(f"    Maximum (with OT): {result['total_max_doctor_capacity']:.0f} min")
    print(f"    Utilization: {result['capacity_utilization_doctor']:.1f}%")

    if result["doctor_capacity_feasible"]:
        print(
            f"    ✅ SUFFICIENT (slack: {result['total_max_doctor_capacity'] - result['total_min_buffered']:.1f} min)"
        )
    else:
        print(
            f"    ❌ INSUFFICIENT (deficit: {result['doctor_capacity_deficit']:.1f} min)"
        )

    # Individual surgery check
    print(f"\n  INDIVIDUAL SURGERY vs DOCTOR CAPACITY:")
    print(
        f"    Max doctor capacity per day: {result['max_doctor_capacity_per_day']:.0f} min"
    )

    if result["individual_surgery_feasible"]:
        print(f"    ✅ All surgeries fit within single doctor capacity")
    else:
        print(f"    ❌ Some surgeries EXCEED single doctor capacity:")
        for s in result["infeasible_surgeries"]:
            print(
                f"       • {s['id']:15s}: {s['duration']:6.1f} min (exceeds by {s['excess']:5.1f} min)"
            )

    # Overall capacity verdict
    if result["capacity_feasible"]:
        print("\n✅ Overall capacity is SUFFICIENT")
    else:
        print("\n❌ Overall capacity is INSUFFICIENT")

    # Surgery breakdown
    print("\nSurgery durations (minimum buffered):")
    for s in result["min_buffered_durations"]:
        print(f"  • {s['id']:15s}: {s['min_buffered']:6.1f} min")

    # Reliability analysis
    print("\n" + "─" * 80)
    print("2. RELIABILITY CONSTRAINT ANALYSIS")
    print("─" * 80)

    print(f"\nEpsilon (ε): {result['epsilon']:.4f}")
    print(
        f"Required per day: Σ ln(1-α_j) ≥ {result['reliability_checks'][0]['required_ln']:.6f}"
    )
    print(f"Most aggressive α available: {result['max_alpha']:.4f}")

    print(
        f"\n{'Surgeries/Day':>15s} {'Max α Needed':>15s} {'Available?':>12s} {'Feasible?':>12s}"
    )
    print("─" * 60)

    for check in result["reliability_checks"]:
        available = (
            "✓" if check["max_alpha_needed"] <= check["max_alpha_available"] else "✗"
        )
        feasible = "✓" if check["feasible"] else "✗"
        print(
            f"{check['surgeries_per_day']:>15d} {check['max_alpha_needed']:>15.6f} {available:>12s} {feasible:>12s}"
        )

    if result["reliability_feasible"]:
        print("\n✅ Reliability constraint is SATISFIABLE")
        print(
            f"   Feasible distributions: {[r['surgeries_per_day'] for r in result['feasible_distributions']]}"
        )
    else:
        print("\n❌ Reliability constraint is UNSATISFIABLE")
        print(f"   No valid distribution of surgeries across days")
        print(f"   Need more aggressive α values or higher ε")

    # Recommendations
    print("\n" + "─" * 80)
    print("3. RECOMMENDATIONS")
    print("─" * 80)

    if not result["overall_feasible"]:
        print("\nTo make this instance feasible:")

        if not result["capacity_feasible"]:
            print(f"\n  Capacity issues:")

            if not result["room_capacity_feasible"]:
                print(f"    ROOM capacity:")
                print(f"      • Increase H (regular hours per day)")
                print(f"      • Add more rooms")
                print(f"      • Add more days")
                print(f"      • Increase max room overtime")
                print(
                    f"      • Need at least {result['room_capacity_deficit']:.0f} more minutes"
                )

            if not result["doctor_capacity_feasible"]:
                print(f"    DOCTOR capacity:")
                print(f"      • Increase doctor daily capacity")
                print(f"      • Add more doctors")
                print(f"      • Add more days")
                print(f"      • Increase max doctor overtime")
                print(
                    f"      • Need at least {result['doctor_capacity_deficit']:.0f} more minutes"
                )

            if not result["individual_surgery_feasible"]:
                print(f"    INDIVIDUAL SURGERY capacity:")
                max_excess = max(s["excess"] for s in result["infeasible_surgeries"])
                print(
                    f"      • Increase max doctor overtime by at least {max_excess:.0f} min"
                )
                print(f"      • Increase doctor daily capacity (H)")
                print(
                    f"      • Use more aggressive α values to reduce buffered durations"
                )
                print(f"      • Split large surgeries into smaller procedures")
                for s in result["infeasible_surgeries"]:
                    print(f"         - {s['id']}: needs {s['excess']:.0f} more minutes")

            print(f"      • Reduce number of surgeries")

        if not result["reliability_feasible"]:
            print(f"\n  Reliability issues:")
            print(f"    • Increase ε (accept more risk)")
            print(f"    • Add more aggressive α values (e.g., 0.15, 0.20)")
            print(f"    • Reduce surgeries per day")
    else:
        print("\n✓ Instance appears feasible for optimization")

    print("\n" + "=" * 80)


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(description="Check instance feasibility")
    parser.add_argument(
        "--instance", type=str, required=True, help="Path to instance JSON file"
    )
    parser.add_argument(
        "--alpha",
        type=float,
        nargs="+",
        default=[0.005, 0.008, 0.01, 0.02, 0.03, 0.05, 0.10],
        help="Alpha choices (default: 0.005 0.008 0.01 0.02 0.03 0.05 0.10)",
    )
    parser.add_argument(
        "--epsilon", type=float, default=0.25, help="Epsilon value (default: 0.25)"
    )
    parser.add_argument(
        "--max-ot-room", type=int, default=120, help="Max room overtime (default: 120)"
    )
    parser.add_argument(
        "--max-ot-doc", type=int, default=60, help="Max doctor overtime (default: 60)"
    )

    args = parser.parse_args()

    # Load instance
    print(f"\nLoading instance: {args.instance}")
    with open(args.instance, "r") as f:
        instance = json.load(f)

    print(f"  • {len(instance['surgeries'])} surgeries")
    print(f"  • {len(instance['days'])} days")
    print(f"  • {len(instance['rooms'])} rooms")
    print(f"  • {len(instance['doctors'])} doctors")

    # Check feasibility
    result = check_instance_feasibility(
        instance, args.alpha, args.epsilon, args.max_ot_room, args.max_ot_doc
    )

    # Print report
    print_feasibility_report(result)

    # Exit code
    exit(0 if result["overall_feasible"] else 1)


if __name__ == "__main__":
    main()

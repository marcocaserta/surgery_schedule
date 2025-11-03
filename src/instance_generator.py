"""
Problem instance generation for surgery scheduling.
"""

import json


def load_instance(filename):
    """
    Load problem instance from JSON file.

    Parameters:
    -----------
    filename : str
        Path to JSON file

    Returns:
    --------
    dict : Problem instance
    """
    with open(filename, "r") as f:
        return json.load(f)


def generate_instance(num_surgeries=35, num_days=5, num_rooms=5, num_doctors=6, H=960):
    """
    Generate parametric surgery scheduling instance.

    Here we can define distribution functions for the different values, e.g., doctors
    and rooms capacities, etc.

    Parameters:
    -----------
    num_surgeries : int
        Number of surgeries to generate
    num_days : int
        Number of days
    num_rooms : int
        Number of operating rooms
    num_doctors : int
        Number of doctors
    H : int
        Regular hours per day (minutes)

    Returns:
    --------
    dict : Problem instance with surgeries, days, rooms, doctors
    """
    # Generate days
    day_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    days = [
        {"id": day_names[i % 7], "H": H, "name": day_names[i % 7]}
        for i in range(num_days)
    ]

    # Generate rooms
    rooms = [{"id": f"OR{i + 1}", "name": f"OR{i + 1}"} for i in range(num_rooms)]

    # Generate doctors with varying capacities
    doctors = []
    for i in range(num_doctors):
        daily_capacity = {day["id"]: int(H * (0.9 - 0.05 * (i // 3))) for day in days}
        doctors.append(
            {
                "id": f"Doctor_{i + 1}",
                "name": f"Doctor_{i + 1}",
                "daily_capacity": daily_capacity,
            }
        )

    # Generate all room-doctor combinations
    all_combinations = [
        f"{room['id']}|{doctor['id']}" for room in rooms for doctor in doctors
    ]

    # Generate surgeries with distribution: ~35% small, ~35% medium, ~30% large
    surgeries = []
    small_count = int(num_surgeries * 0.35)
    medium_count = int(num_surgeries * 0.35)
    large_count = num_surgeries - small_count - medium_count

    # Small surgeries
    for i in range(1, small_count + 1):
        mu_sigma_dict = {}
        base_mu = 60 + i * 5
        base_sigma = 18 + i * 1

        for key in all_combinations:
            parts = key.split("|")
            doc_num = int(parts[1].split("_")[1])
            room_num = int(parts[0].replace("OR", ""))

            mu_sigma_dict[key] = {
                "mu": base_mu
                + (doc_num - num_doctors / 2) * 2
                + (room_num - num_rooms / 2) * 1,
                "sigma": base_sigma + (doc_num - num_doctors / 2) * 0.5,
            }

        surgeries.append(
            {
                "id": f"Small_{i}",
                "name": f"Small_{i}",
                "specialty": "General",
                "mu": base_mu,
                "sigma": base_sigma,
                "mu_sigma": mu_sigma_dict,
            }
        )

    # Medium surgeries
    for i in range(1, medium_count + 1):
        mu_sigma_dict = {}
        base_mu = 150 + i * 8
        base_sigma = 40 + i * 1.5

        for key in all_combinations:
            parts = key.split("|")
            doc_num = int(parts[1].split("_")[1])
            room_num = int(parts[0].replace("OR", ""))

            mu_sigma_dict[key] = {
                "mu": base_mu
                + (doc_num - num_doctors / 2) * 3
                + (room_num - num_rooms / 2) * 1.5,
                "sigma": base_sigma + (doc_num - num_doctors / 2) * 1,
            }

        surgeries.append(
            {
                "id": f"Medium_{i}",
                "name": f"Medium_{i}",
                "specialty": "General",
                "mu": base_mu,
                "sigma": base_sigma,
                "mu_sigma": mu_sigma_dict,
            }
        )

    # Large surgeries
    for i in range(1, large_count + 1):
        mu_sigma_dict = {}
        base_mu = 280 + i * 11
        base_sigma = 65 + i * 2.5

        for key in all_combinations:
            parts = key.split("|")
            doc_num = int(parts[1].split("_")[1])
            room_num = int(parts[0].replace("OR", ""))

            mu_sigma_dict[key] = {
                "mu": base_mu
                + (doc_num - num_doctors / 2) * 4
                + (room_num - num_rooms / 2) * 2,
                "sigma": base_sigma + (doc_num - num_doctors / 2) * 1.5,
            }

        surgeries.append(
            {
                "id": f"Large_{i}",
                "name": f"Large_{i}",
                "specialty": "General",
                "mu": base_mu,
                "sigma": base_sigma,
                "mu_sigma": mu_sigma_dict,
            }
        )

    return {"surgeries": surgeries, "days": days, "rooms": rooms, "doctors": doctors}


def generate_35_surgery_instance():
    """
    Generate 35 surgeries, 5 rooms, 6 doctors - NO SPECIALIZATION.

    Returns:
    --------
    dict : Problem instance with surgeries, days, rooms, doctors
    """
    return generate_instance(
        num_surgeries=35, num_days=5, num_rooms=5, num_doctors=6, H=960
    )


def print_instance_overview(instance):
    """Print overview of problem instance."""
    print("\n" + "=" * 80)
    print("📋 PROBLEM INSTANCE")
    print("=" * 80)

    print(f"\n  Surgeries: {len(instance['surgeries'])}")
    print(f"  Days: {len(instance['days'])}")
    print(f"  Rooms: {len(instance['rooms'])}")
    print(f"  Doctors: {len(instance['doctors'])}")

    # Count by type
    by_type = {}
    for s in instance["surgeries"]:
        surg_id = s["id"]
        if "_" in str(surg_id):
            stype = str(surg_id).split("_")[0]
            by_type[stype] = by_type.get(stype, 0) + 1

    if by_type:
        print("\n  By type:")
        for stype, count in sorted(by_type.items()):
            print(f"    • {stype}: {count} surgeries")

    # Capacity analysis
    total_capacity = sum(d["H"] for d in instance["days"]) * len(instance["rooms"])
    total_demand = sum(
        s.get("mu", s.get("duration_mean", 0)) for s in instance["surgeries"]
    )

    print("\n  Capacity Analysis:")
    print(f"    • Total room capacity: {total_capacity:,} minutes")
    print(f"    • Total mean duration: {total_demand:,.0f} minutes")
    print(
        f"    • Capacity utilization (mean): {100 * total_demand / total_capacity:.1f}%"
    )

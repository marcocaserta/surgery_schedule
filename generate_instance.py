#!/usr/bin/env python3
"""
Script to generate and save problem instances.
"""

import json
import argparse
from src.instance_generator import generate_instance


def main():
    """Generate and save instance with command-line parameters."""
    parser = argparse.ArgumentParser(description='Generate surgery scheduling instance')
    parser.add_argument('--days', type=int, default=5, help='Number of days (default: 5)')
    parser.add_argument('--rooms', type=int, default=5, help='Number of rooms (default: 5)')
    parser.add_argument('--doctors', type=int, default=6, help='Number of doctors (default: 6)')
    parser.add_argument('--H', type=int, default=960, help='Regular hours per day in minutes (default: 960)')
    parser.add_argument('--surgeries', type=int, default=35, help='Number of surgeries (default: 35)')
    
    args = parser.parse_args()
    
    print(f"Generating instance: {args.surgeries} surgeries, {args.days} days, {args.rooms} rooms, {args.doctors} doctors, H={args.H}")
    instance = generate_instance(
        num_surgeries=args.surgeries,
        num_days=args.days,
        num_rooms=args.rooms,
        num_doctors=args.doctors,
        H=args.H
    )
    
    output_file = f'data/instance_s{args.surgeries}_d{args.days}_r{args.rooms}_doc{args.doctors}_H{args.H}.json'
    with open(output_file, 'w') as f:
        json.dump(instance, f, indent=2)
    
    print(f"✓ Instance saved to {output_file}")
    print(f"  - {len(instance['surgeries'])} surgeries")
    print(f"  - {len(instance['days'])} days")
    print(f"  - {len(instance['rooms'])} rooms")
    print(f"  - {len(instance['doctors'])} doctors")


if __name__ == "__main__":
    main()

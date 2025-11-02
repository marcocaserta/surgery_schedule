#!/usr/bin/env python3
"""
Diagnose infeasibility in surgery scheduling model using Gurobi IIS.
"""

import argparse
import pyomo.environ as pyo
from src.surgery_scheduler import SurgeryScheduler
from src.instance_generator import load_instance


def diagnose_infeasibility(instance_file):
    """Diagnose infeasibility using IIS."""
    
    # Load instance
    print(f"\nLoading instance: {instance_file}")
    instance = load_instance(instance_file)
    print(f"  • {len(instance['surgeries'])} surgeries")
    print(f"  • {len(instance['days'])} days")
    print(f"  • {len(instance['rooms'])} rooms")
    print(f"  • {len(instance['doctors'])} doctors")
    
    # Build model
    print("\nBuilding model...")
    scheduler = SurgeryScheduler(
        instance=instance,
        alpha_choices=[0.005, 0.008, 0.01, 0.02, 0.03, 0.05, 0.10],
        epsilon=0.25,
        ot_cost_room=3.0,
        ot_cost_doc=1.5,
        max_ot_room=120,
        max_ot_doc=60
    )
    scheduler.build_model()
    
    # Try to solve
    print("\nAttempting to solve...")
    solver = pyo.SolverFactory('gurobi_persistent')
    solver.set_instance(scheduler.model)
    results = solver.solve(tee=False)
    
    if results.solver.termination_condition == pyo.TerminationCondition.infeasible:
        print("\n❌ Model is INFEASIBLE")
        print("\nComputing IIS (Irreducible Inconsistent Subsystem)...")
        
        # Compute IIS
        solver._solver_model.computeIIS()
        solver._solver_model.write("iis_model.ilp")
        print("  IIS written to iis_model.ilp")
        
        # Get variable and constraint mappings
        var_map = {id(var): name for name, var in scheduler.model.component_map(pyo.Var, active=True).items()}
        constr_map = {id(constr): name for name, constr in scheduler.model.component_map(pyo.Constraint, active=True).items()}
        
        print("\n" + "="*80)
        print("INFEASIBLE CONSTRAINTS:")
        print("="*80)
        
        # Collect IIS constraints with details
        iis_constraints = []
        for constr in solver._solver_model.getConstrs():
            if constr.IISConstr:
                # Try to map back to Pyomo constraint
                constr_name = constr.ConstrName
                iis_constraints.append(constr_name)
        
        # Analyze constraint names
        constraint_analysis = {
            'assign': [],
            'room_cap': [],
            'doc_cap': [],
            'room_seq_fwd': [],
            'room_seq_bwd': [],
            'doctor_seq_fwd': [],
            'doctor_seq_bwd': [],
            'sdoc_upper': [],
            'sdoc_lower': [],
            'sdoc_upper_H': [],
            's_room_upper': [],
            'durdoc_link': [],
            'idle_link': [],
            'reliability': [],
            'other': []
        }
        
        for name in iis_constraints:
            matched = False
            for key in constraint_analysis.keys():
                if key in name:
                    constraint_analysis[key].append(name)
                    matched = True
                    break
            if not matched:
                constraint_analysis['other'].append(name)
        
        # Print by type
        constraint_type_names = {
            'assign': 'Assignment (each surgery scheduled once)',
            'room_cap': 'Room capacity (with overtime)',
            'doc_cap': 'Doctor capacity (with overtime)',
            'room_seq_fwd': 'Room sequencing forward (i after j)',
            'room_seq_bwd': 'Room sequencing backward (j after i)',
            'doctor_seq_fwd': 'Doctor sequencing forward (i after j)',
            'doctor_seq_bwd': 'Doctor sequencing backward (j after i)',
            'sdoc_upper': 'Room-doctor sync (upper bound)',
            'sdoc_lower': 'Room-doctor sync (lower bound)',
            'sdoc_upper_H': 'Doctor start time bounds',
            's_room_upper': 'Room start time bounds',
            'durdoc_link': 'Doctor duration link',
            'idle_link': 'Idle time link',
            'reliability': 'Reliability constraint',
            'other': 'Other/Unknown'
        }
        
        print("\nConstraint types in IIS:")
        for key, constraints in constraint_analysis.items():
            if constraints:
                print(f"\n  {constraint_type_names[key]}: {len(constraints)} constraints")
                for c in constraints[:5]:
                    print(f"    • {c}")
                if len(constraints) > 5:
                    print(f"    ... and {len(constraints) - 5} more")
        
        # Check IIS variables
        print("\n" + "="*80)
        print("INFEASIBLE VARIABLES:")
        print("="*80)
        
        iis_vars = []
        for var in solver._solver_model.getVars():
            if var.IISLB or var.IISUB:
                iis_vars.append((var.VarName, var.IISLB, var.IISUB, var.LB, var.UB))
        
        if iis_vars:
            print(f"\n{len(iis_vars)} variables involved in IIS")
            for name, lb, ub, lb_val, ub_val in iis_vars[:20]:
                bounds = []
                if lb:
                    bounds.append(f"LB={lb_val}")
                if ub:
                    bounds.append(f"UB={ub_val}")
                print(f"  • {name}: {', '.join(bounds)}")
            if len(iis_vars) > 20:
                print(f"  ... and {len(iis_vars) - 20} more")
        else:
            print("\nNo variables with bound conflicts")
        
        # Analysis
        print("\n" + "="*80)
        print("DIAGNOSIS:")
        print("="*80)
        
        if constraint_analysis['reliability']:
            print("\n⚠️  RELIABILITY CONSTRAINT is in the IIS")
            print("    The log-sum reliability constraint cannot be satisfied.")
            print("    This means surgeries cannot be distributed to meet ε=0.25 per day.")
            print(f"    Affected: {constraint_analysis['reliability']}")
        
        if constraint_analysis['room_cap']:
            print("\n⚠️  ROOM CAPACITY constraints are in the IIS")
            print("    Even with overtime, rooms don't have enough capacity.")
            print(f"    Count: {len(constraint_analysis['room_cap'])}")
        
        if constraint_analysis['doc_cap']:
            print("\n⚠️  DOCTOR CAPACITY constraints are in the IIS")
            print("    Even with overtime, doctors don't have enough capacity.")
            print(f"    Count: {len(constraint_analysis['doc_cap'])}")
        
        if constraint_analysis['room_seq_fwd'] or constraint_analysis['room_seq_bwd']:
            print("\n⚠️  ROOM SEQUENCING constraints are in the IIS")
            print("    Surgeries cannot be sequenced without overlaps in rooms.")
            print(f"    Forward: {len(constraint_analysis['room_seq_fwd'])}, Backward: {len(constraint_analysis['room_seq_bwd'])}")
        
        if constraint_analysis['doctor_seq_fwd'] or constraint_analysis['doctor_seq_bwd']:
            print("\n⚠️  DOCTOR SEQUENCING constraints are in the IIS")
            print("    Surgeries cannot be sequenced without overlaps for doctors.")
            print(f"    Forward: {len(constraint_analysis['doctor_seq_fwd'])}, Backward: {len(constraint_analysis['doctor_seq_bwd'])}")
        
        if constraint_analysis['sdoc_upper'] or constraint_analysis['sdoc_lower']:
            print("\n⚠️  ROOM-DOCTOR SYNCHRONIZATION constraints are in the IIS")
            print("    Room and doctor start times cannot be synchronized.")
            print(f"    Upper: {len(constraint_analysis['sdoc_upper'])}, Lower: {len(constraint_analysis['sdoc_lower'])}")
        
        if constraint_analysis['other']:
            print("\n⚠️  OTHER/UNKNOWN constraints are in the IIS")
            print(f"    Count: {len(constraint_analysis['other'])}")
            print("    These may be bound constraints or auxiliary constraints")
        
        print("\n" + "="*80)
        
    else:
        print("\n✅ Model is FEASIBLE")


def main():
    parser = argparse.ArgumentParser(description='Diagnose infeasibility')
    parser.add_argument('--instance', type=str, required=True,
                       help='Path to instance JSON file')
    args = parser.parse_args()
    
    diagnose_infeasibility(args.instance)


if __name__ == "__main__":
    main()

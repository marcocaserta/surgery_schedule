"""
Surgery Scheduling Optimization with Overtime Penalties
"""

import pyomo.environ as pyo
from pyomo.opt import TerminationCondition
import math
import time


class SurgeryScheduler:
    """
    Surgery scheduling optimization model with overtime penalties.
    
    Features:
    - Soft capacity constraints with overtime
    - Stochastic duration modeling using Cantelli's inequality
    - Reliability constraints (log-product form)
    - Room and doctor sequencing
    """
    
    def __init__(self, instance, alpha_choices, epsilon, 
                 ot_cost_room=3.0, ot_cost_doc=1.5,
                 max_ot_room=120, max_ot_doc=60):
        """
        Initialize the scheduler.
        
        Parameters:
        -----------
        instance : dict
            Problem instance with surgeries, days, rooms, doctors
        alpha_choices : list
            Discretized alpha values for reliability
        epsilon : float or dict
            Reliability threshold per day
        ot_cost_room : float
            Room overtime cost (€/min)
        ot_cost_doc : float
            Doctor overtime cost (€/min)
        max_ot_room : float
            Max room overtime per day (minutes)
        max_ot_doc : float
            Max doctor overtime per day (minutes)
        """
        self.instance = instance
        self.alpha_choices = tuple(alpha_choices)
        self.epsilon = epsilon
        self.ot_cost_room = ot_cost_room
        self.ot_cost_doc = ot_cost_doc
        self.max_ot_room = max_ot_room
        self.max_ot_doc = max_ot_doc
        
        self.model = None
        self.durations = None
        self.results = None
        self.solve_time = None
        
    def precompute_durations(self):
        """Precompute buffered durations using Cantelli's inequality."""
        durations = {}
        
        for surgery in self.instance['surgeries']:
            j = surgery['id']
            durations[j] = {}
            
            for room in self.instance['rooms']:
                r = room['id']
                durations[j][r] = {}
                
                for doctor in self.instance['doctors']:
                    k = doctor['id']
                    durations[j][r][k] = {}
                    
                    mu, sigma = None, None
                    
                    if 'mu_sigma' in surgery:
                        key = f"{r}|{k}"
                        if key in surgery['mu_sigma']:
                            mu = surgery['mu_sigma'][key]['mu']
                            sigma = surgery['mu_sigma'][key]['sigma']
                    elif 'duration_mean' in surgery:
                        surgery_specialty = surgery.get('specialty')
                        doctor_specialties = doctor.get('specialties', [])
                        room_types = room.get('types', [])
                        
                        if surgery_specialty:
                            if surgery_specialty not in doctor_specialties:
                                continue
                            if surgery_specialty not in room_types:
                                continue
                        
                        mu = surgery['duration_mean']
                        sigma = surgery['duration_std']
                    
                    if mu is not None and sigma is not None:
                        for alpha_idx, alpha in enumerate(self.alpha_choices):
                            if alpha >= 1.0:
                                buffer_duration = float('inf')
                            else:
                                buffer = sigma * math.sqrt((1 - alpha) / alpha)
                                buffer_duration = mu + buffer
                            
                            durations[j][r][k][alpha_idx] = buffer_duration
        
        return durations
    
    def build_model(self):
        """Build the Pyomo optimization model."""
        print("Precomputing buffered durations...")
        self.durations = self.precompute_durations()
        
        # Convert epsilon to dict
        if isinstance(self.epsilon, (int, float)):
            epsilon_dict = {d['id']: float(self.epsilon) for d in self.instance['days']}
        else:
            epsilon_dict = {d['id']: float(self.epsilon.get(d['id'], 0.25)) 
                          for d in self.instance['days']}
        
        # Extract sets
        J = [s["id"] for s in self.instance["surgeries"]]
        D = [d["id"] for d in self.instance["days"]]
        R = [r["id"] for r in self.instance["rooms"]]
        K = [k["id"] for k in self.instance["doctors"]]
        T = list(range(len(self.alpha_choices)))
        
        day_dict = {d['id']: d for d in self.instance['days']}
        doc_dict = {k['id']: k for k in self.instance['doctors']}
        surgery_dict = {s['id']: s for s in self.instance['surgeries']}
        
        # ENHANCEMENT #6: Variable fixing via preprocessing
        print("Preprocessing: fixing infeasible variables...")
        fixed_vars = self._preprocess_and_fix(J, D, R, K, T, day_dict, doc_dict, surgery_dict)
        
        # Build valid combinations
        valid = set()
        for j in J:
            for d in D:
                for r in R:
                    for k in K:
                        if k in doc_dict:
                            doctor_capacity = doc_dict[k].get('daily_capacity', {})
                            if isinstance(doctor_capacity, dict):
                                cap = doctor_capacity.get(d, 0)
                            else:
                                cap = day_dict[d]['H']
                        else:
                            cap = day_dict[d]['H']
                        
                        if cap > 0:
                            for t_idx in T:
                                if self.durations[j][r][k].get(t_idx) is not None:
                                    # Skip if fixed to 0
                                    if (j, d, r, k, t_idx) not in fixed_vars:
                                        valid.add((j, d, r, k, t_idx))
        
        print(f"Valid combinations: {len(valid):,} (fixed {len(fixed_vars):,} to zero)")
        
        # Surgery-doctor mapping for pruning
        surgery_doctors = {}
        for j in J:
            surgery_doctors[j] = set()
            for (j2, d, r, k, t) in valid:
                if j2 == j:
                    surgery_doctors[j].add(k)
        
        # Create model
        model = pyo.ConcreteModel()
        model.J = pyo.Set(initialize=J)
        model.D = pyo.Set(initialize=D)
        model.R = pyo.Set(initialize=R)
        model.K = pyo.Set(initialize=K)
        model.T = pyo.Set(initialize=T)
        model.VALID = pyo.Set(initialize=valid, dimen=5)
        
        model.epsilon_param = pyo.Param(model.D, initialize=epsilon_dict, mutable=True)
        model.log_one_minus_eps = pyo.Param(model.D, 
                                            initialize={d: math.log(1 - epsilon_dict[d]) for d in D},
                                            mutable=True)
        
        # Decision variables
        model.s = pyo.Var(model.J, model.D, model.R, 
                         bounds=lambda m,j,d,r: (0.0, day_dict[d]["H"] + self.max_ot_room),
                         domain=pyo.NonNegativeReals)
        
        model.w = pyo.Var(model.VALID, domain=pyo.Binary)
        
        model.u_room = pyo.Var([(j, i, d, r) for j in J for i in J for d in D for r in R if j < i],
                              domain=pyo.Binary)
        
        pruned_u_doc = []
        for j in J:
            for i in J:
                if j < i:
                    shared = surgery_doctors[j] & surgery_doctors[i]
                    for d in D:
                        for k in shared:
                            pruned_u_doc.append((j, i, d, k))
        
        model.u_doc = pyo.Var(pruned_u_doc, domain=pyo.Binary)
        
        model.s_doc = pyo.Var(model.J, model.D, model.K, domain=pyo.NonNegativeReals)
        model.dur_doc = pyo.Var(model.J, model.D, model.K, domain=pyo.NonNegativeReals)
        
        model.OT_room = pyo.Var(model.D, model.R, 
                               bounds=(0.0, self.max_ot_room),
                               domain=pyo.NonNegativeReals)
        
        model.OT_doc = pyo.Var(model.D, model.K, 
                              bounds=(0.0, self.max_ot_doc),
                              domain=pyo.NonNegativeReals)
        
        model.Idle = pyo.Var(model.D, model.R, domain=pyo.NonNegativeReals)
        
        model.y = pyo.Expression(model.J, model.D, model.K,
                                rule=lambda m,j,d,k: sum(m.w[j,d,r,k,t] 
                                                        for (j2,d2,r,k2,t) in m.VALID 
                                                        if j2==j and d2==d and k2==k))
        
        # Big-M
        max_dur = max(max(self.durations[j][r][k].values()) 
                     for j in J for r in R for k in K 
                     if self.durations[j][r][k])
        M_room = {d: day_dict[d]["H"] + self.max_ot_room + max_dur for d in D}
        
        # Constraints
        self._add_constraints(model, day_dict, doc_dict, M_room, pruned_u_doc)
        
        # Objective
        def obj_rule(m):
            total_idle = sum(m.Idle[d,r] for d in D for r in R)
            room_ot_cost = self.ot_cost_room * sum(m.OT_room[d,r] for d in D for r in R)
            doc_ot_cost = self.ot_cost_doc * sum(m.OT_doc[d,k] for d in D for k in K)
            start_penalty = 0.001 * sum(m.s[j,d,r] for j in J for d in D for r in R)
            return total_idle + room_ot_cost + doc_ot_cost + start_penalty
        
        model.obj = pyo.Objective(rule=obj_rule, sense=pyo.minimize)
        
        self.model = model
        print(f"✓ Model built with {len(valid):,} binary w variables")
        
    def _preprocess_and_fix(self, J, D, R, K, T, day_dict, doc_dict, surgery_dict):
        """
        ENHANCEMENT #6: Preprocessing to fix infeasible variables.
        Returns set of (j,d,r,k,t) tuples to exclude from valid set.
        """
        fixed = set()
        
        for j in J:
            for d in D:
                for k in K:
                    # Get doctor capacity for this day
                    if k in doc_dict:
                        doctor_capacity = doc_dict[k].get('daily_capacity', {})
                        if isinstance(doctor_capacity, dict):
                            cap = doctor_capacity.get(d, 0)
                        else:
                            cap = day_dict[d]['H']
                    else:
                        cap = day_dict[d]['H']
                    
                    if cap == 0:
                        # Fix all variables for this doctor-day to 0
                        for r in R:
                            for t in T:
                                fixed.add((j, d, r, k, t))
                        continue
                    
                    # Check if surgery is too long for doctor even with max overtime
                    max_doctor_time = cap + self.max_ot_doc
                    for r in R:
                        for t in T:
                            dur = self.durations[j][r][k].get(t)
                            if dur is not None and dur > max_doctor_time:
                                fixed.add((j, d, r, k, t))
        
        return fixed
    
    def _add_constraints(self, m, day_dict, doc_dict, M_room, pruned_u_doc):
        """Add all constraints to the model."""
        J, D, R, K = list(m.J), list(m.D), list(m.R), list(m.K)
        
        # C1: Each surgery scheduled once
        def assign_rule(m, j):
            return sum(m.w[j,d,r,k,t] for (j2,d,r,k,t) in m.VALID if j2==j) == 1
        m.assign = pyo.Constraint(m.J, rule=assign_rule)
        
        # C2: Room capacity with overtime
        def room_cap_rule(m, j, d, r):
            chosen = sum(m.w[j,d,r,k,t] for (j2,d2,r2,k,t) in m.VALID 
                        if j2==j and d2==d and r2==r)
            dur_sum = sum(self.durations[j][r][k][t] * m.w[j,d,r,k,t] 
                         for (j2,d2,r2,k,t) in m.VALID 
                         if j2==j and d2==d and r2==r and self.durations[j][r][k].get(t) is not None)
            return m.s[j,d,r] + dur_sum <= day_dict[d]["H"] + m.OT_room[d,r] + M_room[d] * (1 - chosen)
        m.room_cap = pyo.Constraint(m.J, m.D, m.R, rule=room_cap_rule)
        
        # C3: Doctor capacity with overtime
        def doc_cap_rule(m, k, d):
            if k in doc_dict:
                doctor_capacity = doc_dict[k].get('daily_capacity', {})
                cap = doctor_capacity.get(d, day_dict[d]['H']) if isinstance(doctor_capacity, dict) else day_dict[d]['H']
            else:
                cap = day_dict[d]['H']
            
            if cap == 0:
                return pyo.Constraint.Skip
            
            return sum(self.durations[j][r][k][t] * m.w[j,d,r,k,t] 
                      for (j,d2,r,k2,t) in m.VALID 
                      if k2==k and d2==d and self.durations[j][r][k].get(t) is not None) <= cap + m.OT_doc[d,k]
        m.doc_cap = pyo.Constraint(m.K, m.D, rule=doc_cap_rule)
        
        # C4-C5: Room-doctor start time sync
        def sdoc_upper_rule(m, j, d, k, r):
            return m.s_doc[j,d,k] <= m.s[j,d,r] + M_room[d] * (1 - sum(m.w[j,d,r,k,t] 
                                                                        for t in m.T 
                                                                        if (j,d,r,k,t) in m.VALID))
        m.sdoc_upper = pyo.Constraint(m.J, m.D, m.K, m.R, rule=sdoc_upper_rule)
        
        def sdoc_lower_rule(m, j, d, k, r):
            return m.s_doc[j,d,k] >= m.s[j,d,r] - M_room[d] * (1 - sum(m.w[j,d,r,k,t] 
                                                                        for t in m.T 
                                                                        if (j,d,r,k,t) in m.VALID))
        m.sdoc_lower = pyo.Constraint(m.J, m.D, m.K, m.R, rule=sdoc_lower_rule)
        
        # C6: Doctor start time bounds
        def sdoc_upper_H_rule(m, j, d, k):
            return m.s_doc[j,d,k] <= day_dict[d]["H"] + m.OT_doc[d,k] + M_room[d] * (1 - m.y[j,d,k])
        m.sdoc_upper_H = pyo.Constraint(m.J, m.D, m.K, rule=sdoc_upper_H_rule)
        
        # C6b: Room start time bounds
        def s_room_upper_rule(m, j, d, r):
            chosen = sum(m.w[j,d,r,k,t] for (j2,d2,r2,k,t) in m.VALID
                        if j2==j and d2==d and r2==r)
            return m.s[j,d,r] <= day_dict[d]["H"] + m.OT_room[d,r] + M_room[d] * (1 - chosen)
        m.s_room_upper = pyo.Constraint(m.J, m.D, m.R, rule=s_room_upper_rule)
        
        # C7: Doctor duration link
        def durdoc_link_rule(m, j, d, k):
            return m.dur_doc[j,d,k] == sum(self.durations[j][r][k][t] * m.w[j,d,r,k,t] 
                                           for (j2,d2,r,k2,t) in m.VALID 
                                           if j2==j and d2==d and k2==k and self.durations[j][r][k].get(t) is not None)
        m.durdoc_link = pyo.Constraint(m.J, m.D, m.K, rule=durdoc_link_rule)
        
        # C7b: Idle time link
        def idle_link_rule(m, d, r):
            used = sum(self.durations[j][r][k][t] * m.w[j,d,r,k,t]
                      for (j,d2,r2,k,t) in m.VALID
                      if d2==d and r2==r and self.durations[j][r][k].get(t) is not None)
            return m.Idle[d,r] >= day_dict[d]["H"] - used
        m.idle_link = pyo.Constraint(m.D, m.R, rule=idle_link_rule)
        
        # C8-C9: Room sequencing
        def room_seq_fwd_rule(m, j, i, d, r):
            if (j,i,d,r) not in m.u_room.index_set():
                return pyo.Constraint.Skip
            
            chosen_j = sum(m.w[j,d,r,k,t] for (j2,d2,r2,k,t) in m.VALID 
                          if j2==j and d2==d and r2==r)
            chosen_i = sum(m.w[i,d,r,k,t] for (i2,d2,r2,k,t) in m.VALID 
                          if i2==i and d2==d and r2==r)
            dur_j = sum(self.durations[j][r][k][t] * m.w[j,d,r,k,t] 
                       for (j2,d2,r2,k,t) in m.VALID 
                       if j2==j and d2==d and r2==r and self.durations[j][r][k].get(t) is not None)
            
            return m.s[i,d,r] >= m.s[j,d,r] + dur_j - M_room[d] * (2 - chosen_j - chosen_i) - M_room[d] * (1 - m.u_room[j,i,d,r])
        m.room_seq_fwd = pyo.Constraint([(j,i,d,r) for j in J for i in J for d in D for r in R if j<i],
                                       rule=room_seq_fwd_rule)
        
        def room_seq_bwd_rule(m, j, i, d, r):
            if (j,i,d,r) not in m.u_room.index_set():
                return pyo.Constraint.Skip
            
            chosen_j = sum(m.w[j,d,r,k,t] for (j2,d2,r2,k,t) in m.VALID 
                          if j2==j and d2==d and r2==r)
            chosen_i = sum(m.w[i,d,r,k,t] for (i2,d2,r2,k,t) in m.VALID 
                          if i2==i and d2==d and r2==r)
            dur_i = sum(self.durations[i][r][k][t] * m.w[i,d,r,k,t] 
                       for (i2,d2,r2,k,t) in m.VALID 
                       if i2==i and d2==d and r2==r and self.durations[i][r][k].get(t) is not None)
            
            return m.s[j,d,r] >= m.s[i,d,r] + dur_i - M_room[d] * (2 - chosen_j - chosen_i) - M_room[d] * m.u_room[j,i,d,r]
        m.room_seq_bwd = pyo.Constraint([(j,i,d,r) for j in J for i in J for d in D for r in R if j<i],
                                       rule=room_seq_bwd_rule)
        
        # C10-C11: Doctor sequencing
        def doctor_seq_fwd_rule(m, j, i, d, k):
            if (j,i,d,k) not in m.u_doc.index_set():
                return pyo.Constraint.Skip
            return m.s_doc[i,d,k] >= m.s_doc[j,d,k] + m.dur_doc[j,d,k] - M_room[d] * (2 - m.y[j,d,k] - m.y[i,d,k]) - M_room[d] * (1 - m.u_doc[j,i,d,k])
        m.doctor_seq_fwd = pyo.Constraint(pruned_u_doc, rule=doctor_seq_fwd_rule)
        
        def doctor_seq_bwd_rule(m, j, i, d, k):
            if (j,i,d,k) not in m.u_doc.index_set():
                return pyo.Constraint.Skip
            return m.s_doc[j,d,k] >= m.s_doc[i,d,k] + m.dur_doc[i,d,k] - M_room[d] * (2 - m.y[j,d,k] - m.y[i,d,k]) - M_room[d] * m.u_doc[j,i,d,k]
        m.doctor_seq_bwd = pyo.Constraint(pruned_u_doc, rule=doctor_seq_bwd_rule)
        
        # C12: Reliability constraint
        ln_alpha = [math.log(1 - a) for a in self.alpha_choices]
        
        def reliability_rule(m, d):
            return sum(ln_alpha[t] * m.w[j,d,r,k,t] 
                      for (j,d2,r,k,t) in m.VALID if d2==d) >= m.log_one_minus_eps[d]
        m.reliability = pyo.Constraint(m.D, rule=reliability_rule)
        
        # C13-C15: Aggregate capacity cuts
        # Compute minimum durations (using most aggressive alpha)
        min_durations = {}
        T_list = list(m.T)
        for j in J:
            min_dur = min([self.durations[j][r][k][t] 
                          for r in R for k in K for t in T_list 
                          if self.durations[j][r][k].get(t) is not None], 
                         default=0)
            min_durations[j] = min_dur
        
        # C13: Per-day aggregate capacity cut
        def day_aggregate_cut_rule(m, d):
            total_min_dur = sum(min_durations[j] * sum(m.w[j,d2,r,k,t] 
                                                       for (j2,d2,r,k,t) in m.VALID 
                                                       if j2==j and d2==d) 
                               for j in J)
            return total_min_dur <= len(R) * (day_dict[d]["H"] + self.max_ot_room)
        m.day_aggregate_cut = pyo.Constraint(m.D, rule=day_aggregate_cut_rule)
        
        # C14: Per-room per-day aggregate capacity cut
        def room_day_aggregate_cut_rule(m, d, r):
            total_min_dur = sum(min_durations[j] * sum(m.w[j,d2,r2,k,t] 
                                                       for (j2,d2,r2,k,t) in m.VALID 
                                                       if j2==j and d2==d and r2==r) 
                               for j in J)
            return total_min_dur <= day_dict[d]["H"] + m.OT_room[d,r]
        m.room_day_aggregate_cut = pyo.Constraint(m.D, m.R, rule=room_day_aggregate_cut_rule)
        
        # C15: Per-doctor per-day aggregate capacity cut
        def doc_day_aggregate_cut_rule(m, d, k):
            if k in doc_dict:
                doctor_capacity = doc_dict[k].get('daily_capacity', {})
                cap = doctor_capacity.get(d, day_dict[d]['H']) if isinstance(doctor_capacity, dict) else day_dict[d]['H']
            else:
                cap = day_dict[d]['H']
            
            if cap == 0:
                return pyo.Constraint.Skip
            
            total_min_dur = sum(min_durations[j] * sum(m.w[j,d2,r,k2,t] 
                                                       for (j2,d2,r,k2,t) in m.VALID 
                                                       if j2==j and d2==d and k2==k) 
                               for j in J)
            return total_min_dur <= cap + m.OT_doc[d,k]
        m.doc_day_aggregate_cut = pyo.Constraint(m.D, m.K, rule=doc_day_aggregate_cut_rule)
    
    def solve(self, time_limit=900, mip_gap=0.15):
        """Solve the optimization model."""
        if self.model is None:
            raise RuntimeError("Model not built. Call build_model() first.")
        
        solver_names = ['gurobi_persistent', 'gurobi_direct', 'gurobi']
        solver = None
        solver_name_used = None
        
        for solver_name in solver_names:
            try:
                solver = pyo.SolverFactory(solver_name)
                if solver.available():
                    solver_name_used = solver_name
                    print(f"Using solver: {solver_name}")
                    break
            except:
                continue
        
        if solver is None or not solver.available():
            raise RuntimeError("No Gurobi solver available")
        
        # Set options
        if solver_name_used == 'gurobi_persistent':
            solver.set_instance(self.model)
            solver.set_gurobi_param('TimeLimit', time_limit)
            solver.set_gurobi_param('MIPGap', mip_gap)
            solver.set_gurobi_param('Threads', 0)
            solver.set_gurobi_param('MIPFocus', 1)
            
            print(f"Solving (TimeLimit={time_limit}s, MIPGap={mip_gap})...")
            start_time = time.time()
            results = solver.solve(tee=True, save_results=False)
            self.solve_time = time.time() - start_time
        else:
            solver.options['TimeLimit'] = time_limit
            solver.options['MIPGap'] = mip_gap
            solver.options['Threads'] = 0
            solver.options['MIPFocus'] = 1
            
            print(f"Solving (TimeLimit={time_limit}s, MIPGap={mip_gap})...")
            start_time = time.time()
            results = solver.solve(self.model, tee=True)
            self.solve_time = time.time() - start_time
        
        print(f"\nSolve completed in {self.solve_time:.1f}s")
        
        self.results = results
        return results

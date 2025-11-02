"""
Results extraction and analysis for surgery scheduling.
"""

import pyomo.environ as pyo
import math


class ResultsAnalyzer:
    """Extract and analyze optimization results."""
    
    def __init__(self, scheduler):
        """
        Initialize analyzer with a solved scheduler.
        
        Parameters:
        -----------
        scheduler : SurgeryScheduler
            Solved scheduler instance
        """
        self.scheduler = scheduler
        self.schedule = None
        self.idle_time = None
        self.overtime_info = None
        
    def extract_schedule(self):
        """Extract schedule from solved model."""
        model = self.scheduler.model
        instance = self.scheduler.instance
        durations = self.scheduler.durations
        alpha_choices = self.scheduler.alpha_choices
        
        schedule = []
        
        for (j, t, r, k, alpha_idx) in model.VALID:
            if pyo.value(model.w[j, t, r, k, alpha_idx]) > 0.5:
                surgery = next((s for s in instance['surgeries'] if s['id'] == j), None)
                day = next((d for d in instance['days'] if d['id'] == t), None)
                room = next((rm for rm in instance['rooms'] if rm['id'] == r), None)
                doctor = next((doc for doc in instance['doctors'] if doc['id'] == k), None)
                
                if surgery and day and room and doctor:
                    start_time = pyo.value(model.s[j, t, r])
                    
                    if 'mu_sigma' in surgery:
                        key = f"{r}|{k}"
                        if key in surgery['mu_sigma']:
                            duration_mean = surgery['mu_sigma'][key]['mu']
                            duration_std = surgery['mu_sigma'][key]['sigma']
                        else:
                            duration_mean = surgery.get('mu', 0)
                            duration_std = surgery.get('sigma', 0)
                    else:
                        duration_mean = surgery.get('duration_mean', surgery.get('mu', 0))
                        duration_std = surgery.get('duration_std', surgery.get('sigma', 0))
                    
                    buffered_dur = durations[j][r][k][alpha_idx]
                    end_time = start_time + buffered_dur
                    
                    schedule.append({
                        'surgery_id': j,
                        'surgery_name': surgery.get('name', str(j)),
                        'specialty': surgery.get('specialty', 'General'),
                        'day': t,
                        'day_name': day.get('name', str(t)),
                        'room': r,
                        'room_name': room.get('name', str(r)),
                        'doctor': k,
                        'doctor_name': doctor.get('name', str(k)),
                        'alpha': alpha_choices[alpha_idx],
                        'duration_mean': duration_mean,
                        'duration_std': duration_std,
                        'buffered_duration': buffered_dur,
                        'start': start_time,
                        'end': end_time
                    })
        
        # Extract overtime
        overtime_info = {'room': {}, 'doctor': {}}
        
        for d in model.D:
            for r in model.R:
                ot = pyo.value(model.OT_room[d, r])
                if ot > 0.01:
                    if d not in overtime_info['room']:
                        overtime_info['room'][d] = {}
                    overtime_info['room'][d][r] = ot
            
            for k in model.K:
                ot = pyo.value(model.OT_doc[d, k])
                if ot > 0.01:
                    if d not in overtime_info['doctor']:
                        overtime_info['doctor'][d] = {}
                    overtime_info['doctor'][d][k] = ot
        
        # Compute idle time
        total_idle = 0
        for d in instance['days']:
            for r in instance['rooms']:
                day_room_used = sum(s['buffered_duration'] for s in schedule 
                                   if s['day'] == d['id'] and s['room'] == r['id'])
                total_idle += max(0, d['H'] - day_room_used)
        
        # Sort schedule
        day_order = [d['id'] for d in instance['days']]
        day_to_idx = {d: idx for idx, d in enumerate(day_order)}
        schedule.sort(key=lambda x: (day_to_idx.get(x['day'], 999), x['room'], x['start']))
        
        self.schedule = schedule
        self.idle_time = total_idle
        self.overtime_info = overtime_info
        
        return schedule, total_idle, overtime_info
    
    def compute_statistics(self):
        """Compute summary statistics."""
        if self.schedule is None:
            self.extract_schedule()
        
        instance = self.scheduler.instance
        schedule = self.schedule
        
        stats = {
            'total_surgeries': len(schedule),
            'expected_surgeries': len(instance['surgeries']),
            'total_capacity': sum(d['H'] for d in instance['days']) * len(instance['rooms']),
            'idle_time': self.idle_time,
            'utilization': 100 * (1 - self.idle_time / (sum(d['H'] for d in instance['days']) * len(instance['rooms']))),
            'objective_value': pyo.value(self.scheduler.model.obj),
            'solve_time': self.scheduler.solve_time,
        }
        
        # Overtime stats
        total_room_ot = sum(ot for day_ot in self.overtime_info['room'].values() for ot in day_ot.values())
        total_doc_ot = sum(ot for day_ot in self.overtime_info['doctor'].values() for ot in day_ot.values())
        
        stats['total_room_overtime'] = total_room_ot
        stats['total_doctor_overtime'] = total_doc_ot
        stats['total_overtime_cost'] = (total_room_ot * self.scheduler.ot_cost_room + 
                                       total_doc_ot * self.scheduler.ot_cost_doc)
        
        # Per-day stats
        by_day = {}
        for s in schedule:
            if s['day'] not in by_day:
                by_day[s['day']] = []
            by_day[s['day']].append(s)
        
        stats['by_day'] = {}
        for day_id, surgeries in by_day.items():
            day = next(d for d in instance['days'] if d['id'] == day_id)
            day_capacity = day['H'] * len(instance['rooms'])
            day_used = sum(s['buffered_duration'] for s in surgeries)
            
            stats['by_day'][day_id] = {
                'surgeries': len(surgeries),
                'capacity': day_capacity,
                'used': day_used,
                'utilization': 100 * day_used / day_capacity if day_capacity > 0 else 0,
                'alpha_sum': sum(s['alpha'] for s in surgeries)
            }
        
        # By specialty
        by_specialty = {}
        for s in schedule:
            spec = s['specialty']
            if spec not in by_specialty:
                by_specialty[spec] = []
            by_specialty[spec].append(s)
        
        stats['by_specialty'] = {spec: {
            'count': len(surgeries),
            'avg_alpha': sum(s['alpha'] for s in surgeries) / len(surgeries)
        } for spec, surgeries in by_specialty.items()}
        
        # Alpha distribution
        alpha_counts = {}
        for s in schedule:
            alpha = s['alpha']
            alpha_counts[alpha] = alpha_counts.get(alpha, 0) + 1
        
        stats['alpha_distribution'] = alpha_counts
        
        return stats
    
    def verify_reliability(self):
        """Verify reliability constraints."""
        if self.schedule is None:
            self.extract_schedule()
        
        instance = self.scheduler.instance
        schedule = self.schedule
        alpha_choices = self.scheduler.alpha_choices
        epsilon = self.scheduler.epsilon
        
        by_day = {}
        for s in schedule:
            if s['day'] not in by_day:
                by_day[s['day']] = []
            by_day[s['day']].append(s)
        
        ln1ma = {a: math.log(1 - a) for a in alpha_choices}
        
        reliability_check = {}
        for day_id, surgeries in by_day.items():
            lhs = sum(ln1ma[s['alpha']] for s in surgeries)
            
            if isinstance(epsilon, dict):
                epsilon_val = epsilon.get(day_id, 0.25)
            else:
                epsilon_val = epsilon
            
            rhs = math.log(1 - epsilon_val)
            slack = lhs - rhs
            
            reliability_check[day_id] = {
                'lhs': lhs,
                'rhs': rhs,
                'slack': slack,
                'satisfied': slack >= -1e-6,
                'epsilon': epsilon_val
            }
        
        return reliability_check

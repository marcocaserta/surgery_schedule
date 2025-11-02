"""
Output formatting for surgery scheduling results.
"""


class OutputFormatter:
    """Format and print optimization results."""
    
    @staticmethod
    def print_schedule(schedule, instance, epsilon, overtime_info, ot_cost_room, ot_cost_doc):
        """Print detailed schedule."""
        print("\n" + "="*100)
        print("📋 DETAILED SCHEDULE WITH OVERTIME")
        print("="*100)
        
        by_day = {}
        for s in schedule:
            if s['day'] not in by_day:
                by_day[s['day']] = []
            by_day[s['day']].append(s)
        
        day_order = [d['id'] for d in instance['days']]
        
        for day_id in day_order:
            if day_id not in by_day:
                continue
            
            day = next(d for d in instance['days'] if d['id'] == day_id)
            surgeries = by_day[day_id]
            
            epsilon_val = epsilon.get(day_id, epsilon) if isinstance(epsilon, dict) else epsilon
            day_display = day.get('name', str(day_id))
            
            day_room_ot = overtime_info['room'].get(day_id, {})
            day_doc_ot = overtime_info['doctor'].get(day_id, {})
            total_day_room_ot = sum(day_room_ot.values())
            total_day_doc_ot = sum(day_doc_ot.values())
            
            print(f"\n{'─'*100}")
            print(f"Day: {day_display} (Regular Hours: {day['H']} min, ε = {epsilon_val:.4f})")
            if total_day_room_ot > 0 or total_day_doc_ot > 0:
                print(f"  💰 OVERTIME: Room={total_day_room_ot:.1f} min (€{total_day_room_ot*ot_cost_room:.2f}), "
                      f"Doctor={total_day_doc_ot:.1f} min (€{total_day_doc_ot*ot_cost_doc:.2f})")
            print(f"{'─'*100}")
            
            by_room = {}
            for s in surgeries:
                if s['room'] not in by_room:
                    by_room[s['room']] = []
                by_room[s['room']].append(s)
            
            for room_id in sorted(by_room.keys()):
                room_surgeries = by_room[room_id]
                room = next((r for r in instance['rooms'] if r['id'] == room_id), None)
                room_display = room.get('name', str(room_id)) if room else str(room_id)
                
                total_time = sum(s['buffered_duration'] for s in room_surgeries)
                regular_hours = day['H']
                room_ot = day_room_ot.get(room_id, 0)
                
                if total_time > regular_hours:
                    overtime_used = total_time - regular_hours
                    print(f"\n  Room {room_display} - {len(room_surgeries)} surgeries, "
                          f"{total_time:.0f} min total ({regular_hours:.0f} regular + {overtime_used:.0f} OT)")
                    print(f"    ⚠️ Using {room_ot:.1f} min overtime (€{room_ot*ot_cost_room:.2f})")
                else:
                    utilization = 100 * total_time / regular_hours
                    print(f"\n  Room {room_display} - {len(room_surgeries)} surgeries, "
                          f"{total_time:.0f}/{regular_hours} min ({utilization:.1f}% utilized)")
                
                print(f"  {'─'*96}")
                
                for s in room_surgeries:
                    start_str = f"{int(s['start']//60):02d}:{int(s['start']%60):02d}"
                    end_str = f"{int(s['end']//60):02d}:{int(s['end']%60):02d}"
                    overtime_marker = " [OT]" if s['end'] > regular_hours else ""
                    
                    print(f"  • Surgery {str(s['surgery_id']):15s} ({s['surgery_name']:20s}) | "
                          f"{start_str}-{end_str} ({s['buffered_duration']:5.1f}m){overtime_marker} | "
                          f"Doctor: {s['doctor_name']:12s} | "
                          f"α={s['alpha']:.4f} | "
                          f"μ={s['duration_mean']:5.1f} σ={s['duration_std']:4.1f}")
    
    @staticmethod
    def print_overtime_summary(overtime_info, instance, ot_cost_room, ot_cost_doc):
        """Print overtime summary."""
        print("\n" + "="*100)
        print("💰 OVERTIME SUMMARY")
        print("="*100)
        
        total_room_ot_min = 0
        total_doc_ot_min = 0
        
        print("\n🏥 Room Overtime:")
        print(f"{'─'*60}")
        if overtime_info['room']:
            for day_id in sorted(overtime_info['room'].keys()):
                day = next((d for d in instance['days'] if d['id'] == day_id), None)
                day_display = day.get('name', str(day_id)) if day else str(day_id)
                
                for room_id, ot_min in overtime_info['room'][day_id].items():
                    room = next((r for r in instance['rooms'] if r['id'] == room_id), None)
                    room_display = room.get('name', str(room_id)) if room else str(room_id)
                    cost = ot_min * ot_cost_room
                    total_room_ot_min += ot_min
                    print(f"  {day_display:12s} | {room_display:8s} | {ot_min:6.1f} min | €{cost:7.2f}")
        else:
            print("  No room overtime used ✓")
        
        print(f"{'─'*60}")
        print(f"  {'TOTAL ROOM OT':>31s} | {total_room_ot_min:6.1f} min | €{total_room_ot_min*ot_cost_room:7.2f}")
        
        print(f"\n👨⚕️ Doctor Overtime:")
        print(f"{'─'*60}")
        if overtime_info['doctor']:
            for day_id in sorted(overtime_info['doctor'].keys()):
                day = next((d for d in instance['days'] if d['id'] == day_id), None)
                day_display = day.get('name', str(day_id)) if day else str(day_id)
                
                for doc_id, ot_min in overtime_info['doctor'][day_id].items():
                    doctor = next((doc for doc in instance['doctors'] if doc['id'] == doc_id), None)
                    doc_display = doctor.get('name', str(doc_id)) if doctor else str(doc_id)
                    cost = ot_min * ot_cost_doc
                    total_doc_ot_min += ot_min
                    print(f"  {day_display:12s} | {doc_display:12s} | {ot_min:6.1f} min | €{cost:7.2f}")
        else:
            print("  No doctor overtime used ✓")
        
        print(f"{'─'*60}")
        print(f"  {'TOTAL DOCTOR OT':>35s} | {total_doc_ot_min:6.1f} min | €{total_doc_ot_min*ot_cost_doc:7.2f}")
        
        total_ot_cost = total_room_ot_min * ot_cost_room + total_doc_ot_min * ot_cost_doc
        total_ot_hours = (total_room_ot_min + total_doc_ot_min) / 60
        
        print(f"\n{'='*60}")
        print(f"  GRAND TOTAL: {total_room_ot_min + total_doc_ot_min:.1f} min ({total_ot_hours:.2f} hours) | €{total_ot_cost:.2f}")
        print(f"{'='*60}")
    
    @staticmethod
    def print_statistics(stats):
        """Print summary statistics."""
        print("\n" + "="*100)
        print("📊 SUMMARY STATISTICS")
        print("="*100)
        
        print(f"\n{'Overall Metrics':40s}")
        print(f"{'─'*60}")
        print(f"  Total surgeries scheduled: {stats['total_surgeries']}/{stats['expected_surgeries']}")
        print(f"  Total regular capacity: {stats['total_capacity']:,.0f} minutes")
        print(f"  Total idle time: {stats['idle_time']:,.0f} minutes")
        print(f"  Regular hours utilization: {stats['utilization']:.2f}%")
        
        if stats['total_room_overtime'] > 0 or stats['total_doctor_overtime'] > 0:
            print(f"\n  💰 Overtime Usage:")
            print(f"    • Total room overtime: {stats['total_room_overtime']:.1f} minutes")
            print(f"    • Total doctor overtime: {stats['total_doctor_overtime']:.1f} minutes")
            print(f"    • Total overtime cost: €{stats['total_overtime_cost']:.2f}")
        
        print(f"\n{'Per-Day Breakdown':40s}")
        print(f"{'─'*60}")
        for day_id, day_stats in stats['by_day'].items():
            print(f"  {day_id:12s}: {day_stats['surgeries']:2d} surgeries | "
                  f"{day_stats['used']:6.0f}/{day_stats['capacity']:6.0f} min | "
                  f"{day_stats['utilization']:5.1f}% util | "
                  f"Σα={day_stats['alpha_sum']:6.4f}")
        
        print(f"\n{'By Specialty':40s}")
        print(f"{'─'*60}")
        for spec, spec_stats in stats['by_specialty'].items():
            print(f"  {spec:15s}: {spec_stats['count']:2d} surgeries | Avg α = {spec_stats['avg_alpha']:.4f}")
        
        print(f"\n{'Alpha Value Distribution':40s}")
        print(f"{'─'*60}")
        for alpha in sorted(stats['alpha_distribution'].keys()):
            count = stats['alpha_distribution'][alpha]
            pct = 100 * count / stats['total_surgeries']
            bar = '█' * int(pct / 2)
            print(f"  α = {alpha:.4f}: {count:3d} surgeries ({pct:5.1f}%) {bar}")
    
    @staticmethod
    def print_reliability_check(reliability_check):
        """Print reliability verification."""
        print("\n" + "="*100)
        print("🎯 RELIABILITY VERIFICATION")
        print("="*100)
        print("\nConstraint: Σ ln(1-α_j) ≥ ln(1-ε) for each day")
        
        print(f"\n{'Day':17s} {'Σ ln(1-α)':>14s} {'ln(1-ε)':>14s} {'Slack':>12s} {'Status':>10s}")
        print(f"{'─'*80}")
        
        for day_id, check in reliability_check.items():
            status = "✓ OK" if check['satisfied'] else "✗ VIOLATED"
            print(f"{day_id:17s} {check['lhs']:14.6f} {check['rhs']:14.6f} "
                  f"{check['slack']:12.6f} {status:>10s}")
